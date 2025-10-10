# app_calculadora_ganhos.py — versão final (corrigida TX_UU_CPF via Subcanal1)
import io, base64
from pathlib import Path
import numpy as np, pandas as pd, plotly.graph_objects as go, streamlit as st

# ====================== CONFIG ======================
st.set_page_config(page_title="🖩 Calculadora de Ganhos", page_icon="📶", layout="wide")

# ====================== LOGIN ======================
def check_password():
    def password_entered():
        st.session_state["authenticated"] = (st.session_state.get("password") == "claro@123")
        if not st.session_state["authenticated"]:
            st.error("Senha incorreta. Tente novamente.")
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.text_input("🔐 Insira a senha:", type="password",
                      on_change=password_entered, key="password")
        st.stop()
check_password()

# ====================== LOGO / TÍTULO ======================
def _find_asset_bytes(name_candidates):
    for d in [Path.cwd(), Path.cwd()/ "assets", Path.cwd()/ "static"]:
        for base in name_candidates:
            for ext in [".png",".jpg",".jpeg",".webp"]:
                p = d / f"{base}{ext}"
                if p.exists():
                    return p.read_bytes()
    return None

logo_bytes = _find_asset_bytes(["claro_logo","logo_claro","claro"])
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(f"""
        <h1 style='text-align:center;color:#8B0000;font-size:54px;'>
        <img src='data:image/png;base64,{img_b64}' style='height:70px;vertical-align:middle;margin-right:10px'>
        Calculadora de Ganhos</h1>""", unsafe_allow_html=True)
else:
    st.markdown("<h1 style='text-align:center;color:#8B0000;'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

# ====================== PARÂMETROS FIXOS ======================
RETIDO_DICT = {"App":0.9169,"Bot":0.8835,"Web":0.9027}
CR_SEGMENTO = {"Móvel":0.4947,"Residencial":0.4989}
DEFAULT_TX_UU_CPF = 12.28

# ====================== BASE ======================
URL = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL, sheet_name="Tabela Performance")
    if "TP_META" in df.columns:
        df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce")
    df["ANOMES"] = df["ANOMES"].astype(int)
    return df
df = carregar_dados()

# ====================== FUNÇÕES ======================
def fmt_int(x):
    try:
        return f"{np.floor(float(x)+1e-9):,.0f}".replace(",",".")
    except Exception:
        return "0"

def sum_kpi(df_scope, patterns):
    if df_scope.empty or "NM_KPI" not in df_scope.columns:
        return 0.0
    m = False
    for p in patterns:
        m = m | df_scope["NM_KPI"].str.contains(p,case=False,na=False,regex=True)
    return float(df_scope.loc[m,"VOL_KPI"].sum())

def tx_trn_por_acesso(df_scope):
    vt = sum_kpi(df_scope,[r"7\.1","Transa"])
    va = sum_kpi(df_scope,[r"6","Acesso"])
    if va<=0: return 1.0
    return max(vt/va,1.0)

def regra_retido_por_tribo(tribo):
    if str(tribo).strip().lower()=="dma": return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo,RETIDO_DICT["Web"])

def tx_uu_cpf_dyn(df_all, segmento, subcanal, anomes):
    """
    Calcula TX_UU/CPF (Transações ÷ Usuários Únicos)
    Priorizando Subcanal1 -> NM_SUBCANAL -> Segmento -> Fallback.
    """
    df_mes = df_all[(df_all["SEGMENTO"]==segmento) & (df_all["ANOMES"]==anomes)]

    # 1️⃣ - Subcanal1 (prioritário)
    if "Subcanal1" in df_mes.columns:
        df_sub1 = df_mes[df_mes["Subcanal1"]==subcanal]
        vt = sum_kpi(df_sub1,[r"7\.1","Transa"])
        vu = sum_kpi(df_sub1,[r"4\.1","Usuár","Únic","CPF"])
        if vt>0 and vu>0:
            return (vt/vu, vt, vu, "Subcanal1", anomes)

    # 2️⃣ - NM_SUBCANAL
    df_sub = df_mes[df_mes["NM_SUBCANAL"]==subcanal]
    vt = sum_kpi(df_sub,[r"7\.1","Transa"])
    vu = sum_kpi(df_sub,[r"4\.1","Usuár","Únic","CPF"])
    if vt>0 and vu>0:
        return (vt/vu, vt, vu, "NM_SUBCANAL", anomes)

    # 3️⃣ - Segmento
    vt = sum_kpi(df_mes,[r"7\.1","Transa"])
    vu = sum_kpi(df_mes,[r"4\.1","Usuár","Únic","CPF"])
    if vt>0 and vu>0:
        return (vt/vu, vt, vu, "Segmento", anomes)

    # 4️⃣ - Fallback
    return (DEFAULT_TX_UU_CPF, 0, 0, "Fallback", anomes)

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
c1,c2,c3 = st.columns(3)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 Segmento", segmentos)

# ANOMES formatado
anomes_unicos = sorted(df["ANOMES"].unique())
meses_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
mes_legivel = [f"{meses_map[int(str(a)[4:]) ]}/{str(a)[:4]}" for a in anomes_unicos]
map_anomes_legivel = dict(zip(mes_legivel, anomes_unicos))
anomes_legivel = c2.selectbox("🗓️ Mês", mes_legivel, index=len(mes_legivel)-1)
anomes_escolhido = map_anomes_legivel[anomes_legivel]

subcanais = sorted(df.loc[df["SEGMENTO"]==segmento,"Subcanal1"].dropna().unique())
subcanal = c3.selectbox("📌 Subcanal", subcanais)

df_sub = df[(df["SEGMENTO"]==segmento)&(df["Subcanal1"]==subcanal)&(df["ANOMES"]==anomes_escolhido)]
tribo = df_sub["NM_TORRE"].dropna().unique().tolist()[0] if not df_sub.empty else "Indefinido"

k1,k2,k3,k4 = st.columns(4)
k1.metric("Tribo",tribo)
k2.metric("Canal",tribo)
k3.metric("Segmento",segmento)
k4.metric("Subcanal",subcanal)

# ====================== INPUT ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros de Simulação")
volume_trans = st.number_input("📥 Volume de Transações",min_value=0,value=10_000,step=1000)

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    if df_sub.empty:
        st.warning("❌ Nenhum dado encontrado para o mês selecionado.")
        st.stop()

    tx_trn_acc = tx_trn_por_acesso(df_sub)
    cr_segmento = CR_SEGMENTO.get(segmento,0.50)
    retido = regra_retido_por_tribo(tribo)
    vol_acessos = volume_trans/tx_trn_acc

    tx_uu_cpf, vol_trn_real, vol_user_real, origem_tx, anomes_usado = tx_uu_cpf_dyn(df,segmento,subcanal,anomes_escolhido)
    mau_cpf = volume_trans/(tx_uu_cpf if tx_uu_cpf>0 else DEFAULT_TX_UU_CPF)
    vol_lig_ev_hum = (volume_trans/tx_trn_acc)*cr_segmento*retido

    # =================== RESULTADOS ===================
    st.markdown("---")
    st.markdown("### 📊 Resultados Detalhados (Fórmulas)")
    c1,c2,c3 = st.columns(3)
    c1.metric("Volume de Transações", fmt_int(volume_trans))
    c2.metric("Taxa de Transação × Acesso", f"{tx_trn_acc:.2f}")
    c3.metric("% Ligação Direcionada Humano", f"{cr_segmento*100:.2f}%")
    c4,c5,c6 = st.columns(3)
    c4.metric("Retido Digital 72h", f"{retido*100:.2f}%")
    c5.metric("Volume de Acessos", fmt_int(vol_acessos))
    c6.metric("Volume de MAU (CPF)", fmt_int(mau_cpf))

    # =================== EXPANDER DIAGNÓSTICO ===================
    with st.expander("🔍 Diagnóstico de Premissas", expanded=False):
        st.markdown(f"""
        **Segmento:** {segmento}  
        **Subcanal:** {subcanal}  
        **Tribo:** {tribo}  
        **ANOMES usado:** {anomes_usado}

        | Item | Valor |
        |------|-------:|
        | Volume Transações (7.1) | {fmt_int(vol_trn_real)} |
        | Volume Usuários Únicos (4.1) | {fmt_int(vol_user_real)} |
        | TX_UU_CPF Calculado | {tx_uu_cpf:.2f} |
        | Origem | {origem_tx} |
        | CR Segmento | {cr_segmento*100:.2f}% |
        | % Retido Aplicado | {retido*100:.2f}% |
        """, unsafe_allow_html=True)

    # =================== CARD DE RESULTADO ===================
    st.markdown(
        f"""
        <div style="max-width:520px;margin:18px auto;padding:18px 22px;
        background:linear-gradient(90deg,#b31313 0%,#d01f1f 60%,#e23a3a 100%);
        border-radius:18px;box-shadow:0 8px 18px rgba(139,0,0,.25);color:#fff;">
        <div style="display:flex;justify-content:space-between;align-items:center">
        <div style="font-weight:700;font-size:20px;">Volume de CR Evitado Estimado</div>
        <div style="font-weight:800;font-size:30px;background:#fff;color:#b31313;
        padding:6px 16px;border-radius:12px;line-height:1">{fmt_int(vol_lig_ev_hum)}</div>
        </div></div>""", unsafe_allow_html=True)

    st.caption("Fórmulas: Acessos = Transações ÷ (Tx Transações/Acesso).  MAU = Transações ÷ (Transações/Usuários no Subcanal1 e ANOMES selecionado).  CR Evitado = Acessos × CR × %Retido.")
