# app_calculadora_ganhos.py — versão final (10/10/2025)
# Corrigida: ZeroDivisionError + leitura robusta + Pareto + Excel
import io, base64, re, unicodedata
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

# ====================== LOGO ======================
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

# ====================== NORMALIZAÇÃO ======================
def _norm_txt(x: str) -> str:
    """remove acentos, NBSP, travessões, múltiplos espaços, deixa minúsculo"""
    if pd.isna(x): return ""
    s = str(x).replace("\u00A0"," ").replace("–","-").replace("—","-")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch)!="Mn")
    s = re.sub(r"\s+"," ",s.strip().lower())
    return s

# ====================== CONSTANTES DE KPI ======================
KPI_TRANS    = _norm_txt("7.1 - Transações")
KPI_ACESSOS  = _norm_txt("6 - Acessos Usuários")
KPI_UU_CPF   = _norm_txt("4.1 - Usuários Únicos (CPF)")

# ====================== BASE ======================
URL = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL, sheet_name="Tabela Performance")
    df = df[df["TP_META"].astype(str).str.lower().eq("real")].copy()
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce").fillna(0)
    df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype(int)

    # normaliza colunas
    df["KPI_KEY"] = df["NM_KPI"].map(_norm_txt)
    df["SEG_KEY"] = df["SEGMENTO"].map(_norm_txt)
    df["TORRE_KEY"] = df["NM_TORRE"].map(_norm_txt)

    # define subcanal principal com fallback
    if "Subcanal1" in df.columns and df["Subcanal1"].notna().any():
        df["COL_SUBCANAL"] = df["Subcanal1"]
    else:
        df["COL_SUBCANAL"] = df["NM_SUBCANAL"]
    df["SUB_KEY"] = df["COL_SUBCANAL"].map(_norm_txt)
    return df

df = carregar_dados()

# ====================== HELPERS ======================
def fmt_int(x):
    try: return f"{np.floor(float(x)+1e-9):,.0f}".replace(",", ".")
    except: return "0"

def vol_by_kpi(df_scope: pd.DataFrame, kpi_key: str) -> float:
    """busca exata + fallback (4.1+cpf, 7.1+transa, 6+acess)"""
    if df_scope.empty: return 0.0
    vol = df_scope.loc[df_scope["KPI_KEY"].eq(kpi_key), "VOL_KPI"].sum()

    if vol == 0 and ("4.1" in kpi_key or "cpf" in kpi_key):
        vol = df_scope.loc[df_scope["KPI_KEY"].str.contains("4.1") &
                           df_scope["KPI_KEY"].str.contains("cpf"), "VOL_KPI"].sum()
    if vol == 0 and ("7.1" in kpi_key or "transa" in kpi_key):
        vol = df_scope.loc[df_scope["KPI_KEY"].str.contains("7.1") &
                           df_scope["KPI_KEY"].str.contains("transa"), "VOL_KPI"].sum()
    if vol == 0 and ("6" in kpi_key or "acess" in kpi_key):
        vol = df_scope.loc[df_scope["KPI_KEY"].str.contains("6") &
                           df_scope["KPI_KEY"].str.contains("acess"), "VOL_KPI"].sum()
    return float(vol)

def tx_trn_por_acesso(df_scope):
    vt = vol_by_kpi(df_scope, KPI_TRANS)
    va = vol_by_kpi(df_scope, KPI_ACESSOS)
    return vt/va if va>0 else 1.0

def regra_retido_por_tribo(tribo):
    if _norm_txt(tribo)=="dma": return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])

def tx_uu_cpf_dyn(df_all, segmento, subcanal, anomes, tribo):
    """lê 7.1 e 4.1 (CPF) com filtros exatos; fallback p/ segmento"""
    seg_key, sub_key, tor_key = map(_norm_txt, [segmento, subcanal, tribo])
    df_f = df_all[(df_all["ANOMES"]==anomes)&(df_all["SEG_KEY"]==seg_key)&
                  (df_all["SUB_KEY"]==sub_key)&(df_all["TORRE_KEY"]==tor_key)].copy()

    vt = vol_by_kpi(df_f, KPI_TRANS)
    vu = vol_by_kpi(df_f, KPI_UU_CPF)

    if vt>0 and vu>0:
        tx_calc = vt/vu
        return (tx_calc, vt, vu, "COL_SUBCANAL", anomes, tx_calc)

    # fallback por segmento
    df_seg = df_all[(df_all["ANOMES"]==anomes)&(df_all["SEG_KEY"]==seg_key)]
    vt_s = vol_by_kpi(df_seg, KPI_TRANS)
    vu_s = vol_by_kpi(df_seg, KPI_UU_CPF)
    if vt_s>0 and vu_s>0:
        tx_calc = vt_s/vu_s
        return (tx_calc, vt_s, vu_s, "SEGMENTO", anomes, tx_calc)

    return (DEFAULT_TX_UU_CPF, vt, vu, "Fallback", anomes, 0.0)

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
c1,c2,c3 = st.columns(3)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 Segmento", segmentos)

anomes_unicos = sorted(df["ANOMES"].unique())
meses_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
mes_legivel = [f"{meses_map[int(str(a)[4:]) ]}/{str(a)[:4]}" for a in anomes_unicos]
map_anomes_legivel = dict(zip(mes_legivel, anomes_unicos))
anomes_legivel = c2.selectbox("🗓️ Mês", mes_legivel, index=len(mes_legivel)-1)
anomes_escolhido = map_anomes_legivel[anomes_legivel]

subcanais = sorted(df.loc[df["SEGMENTO"]==segmento,"COL_SUBCANAL"].dropna().unique())
subcanal = c3.selectbox("📌 Subcanal", subcanais)

df_sub = df[(df["SEGMENTO"]==segmento)&(df["COL_SUBCANAL"]==subcanal)&(df["ANOMES"]==anomes_escolhido)]
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
    tx_trn_acc = tx_trn_acc if (tx_trn_acc and tx_trn_acc > 0) else 1.0  # evita divisão por zero
    cr_segmento = CR_SEGMENTO.get(segmento,0.50)
    retido = regra_retido_por_tribo(tribo)
    vol_acessos = volume_trans / tx_trn_acc

    tx_uu_cpf, vt_real, vu_real, origem_tx, anomes_usado, tx_calc_real = tx_uu_cpf_dyn(df,segmento,subcanal,anomes_escolhido,tribo)
    mau_cpf = volume_trans/(tx_uu_cpf if tx_uu_cpf>0 else DEFAULT_TX_UU_CPF)
    cr_evitado = (volume_trans/tx_trn_acc)*cr_segmento*retido
    cr_evitado_floor = np.floor(cr_evitado+1e-9)

    # =================== RESULTADOS ===================
    st.markdown("---")
    st.markdown("### 📊 Resultados Detalhados (Fórmulas)")
    c1,c2,c3 = st.columns(3)
    c1.metric("Volume de Transações",fmt_int(volume_trans))
    c2.metric("Taxa de Transação × Acesso",f"{tx_trn_acc:.2f}")
    c3.metric("% Ligação Direcionada Humano",f"{cr_segmento*100:.2f}%")
    c4,c5,c6 = st.columns(3)
    c4.metric("Retido Digital 72h",f"{retido*100:.2f}%")
    c5.metric("Volume de Acessos",fmt_int(vol_acessos))
    c6.metric("Volume de MAU (CPF)",fmt_int(mau_cpf))

    with st.expander("🔍 Diagnóstico de Premissas",expanded=False):
        st.markdown(f"""
**Segmento:** {segmento}  
**Subcanal:** {subcanal}  
**Tribo:** {tribo}  
**ANOMES usado:** {anomes_usado}  

| Item | Valor |
|------|------:|
| Volume Transações (7.1) | {fmt_int(vt_real)} |
| Volume Usuários Únicos (4.1 - CPF) | {fmt_int(vu_real)} |
| **TX_UU_CPF Calculada (Trans/Usuários)** | {tx_calc_real:.2f} |
| **TX_UU_CPF Usada no cálculo** | {tx_uu_cpf:.2f} |
| Origem | {origem_tx} |
| CR Segmento | {cr_segmento*100:.2f}% |
| % Retido Aplicado | {retido*100:.2f}% |
""",unsafe_allow_html=True)

    # card de resultado
    st.markdown(f"""
    <div style="max-width:520px;margin:18px auto;padding:18px 22px;
    background:linear-gradient(90deg,#b31313 0%,#d01f1f 60%,#e23a3a 100%);
    border-radius:18px;box-shadow:0 8px 18px rgba(139,0,0,.25);color:#fff;">
    <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="font-weight:700;font-size:20px;">Volume de CR Evitado Estimado</div>
    <div style="font-weight:800;font-size:30px;background:#fff;color:#b31313;
    padding:6px 16px;border-radius:12px;line-height:1">{fmt_int(cr_evitado_floor)}</div>
    </div></div>""",unsafe_allow_html=True)
    st.caption("Fórmulas: Acessos = Transações ÷ (Tx Transações/Acesso).  MAU = Transações ÷ TX_UU_CPF.  CR Evitado = Acessos × CR × %Retido.")

    # =================== PARETO ===================
    st.markdown("---")
    st.markdown("### 📄 Simulação - Todos os Subcanais")
    resultados = []
    for sub in sorted(df.loc[df["SEGMENTO"]==segmento,"COL_SUBCANAL"].dropna().unique()):
        df_i = df[(df["SEGMENTO"]==segmento)&(df["COL_SUBCANAL"]==sub)&(df["ANOMES"]==anomes_escolhido)]
        tribo_i = df_i["NM_TORRE"].dropna().unique().tolist()[0] if not df_i.empty else "Indefinido"

        tx_i = tx_trn_por_acesso(df_i)
        tx_i = tx_i if (tx_i and tx_i>0) else 1.0
        tx_uu_i,_,_,_,_,_ = tx_uu_cpf_dyn(df,segmento,sub,anomes_escolhido,tribo_i)
        ret_i = regra_retido_por_tribo(tribo_i)
        cr_seg_i = CR_SEGMENTO.get(segmento,0.50)

        vol_acc_i = volume_trans / tx_i
        mau_i = volume_trans / (tx_uu_i if tx_uu_i>0 else DEFAULT_TX_UU_CPF)
        est_i = np.floor((vol_acc_i * cr_seg_i * ret_i) + 1e-9)

        resultados.append({
            "Subcanal":sub,"Tribo":tribo_i,"Transações / Acesso":round(tx_i,2),
            "% Lig. Humano":round(cr_seg_i*100,2),"↓ % Retido":round(ret_i*100,2),
            "Volume de Acessos":int(vol_acc_i),"MAU (CPF)":int(mau_i),
            "Volume de CR Evitado":int(est_i)})

    df_lote = pd.DataFrame(resultados)
    st.dataframe(df_lote,use_container_width=False)

    # Pareto
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_p = df_lote.sort_values("Volume de CR Evitado",ascending=False).reset_index(drop=True)
    tot = df_p["Volume de CR Evitado"].sum()
    if tot>0:
        df_p["Acumulado"] = df_p["Volume de CR Evitado"].cumsum()
        df_p["Acumulado %"] = 100 * df_p["Acumulado"]/tot
    else:
        df_p["Acumulado"] = 0; df_p["Acumulado %"] = 0.0
    df_p["Cor"] = np.where(df_p["Acumulado %"]<=80,"crimson","lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_p["Subcanal"],y=df_p["Volume de CR Evitado"],
                         name="Volume de CR Evitado",marker_color=df_p["Cor"]))
    fig.add_trace(go.Scatter(x=df_p["Subcanal"],y=df_p["Acumulado %"],name="Acumulado %",
                             mode="lines+markers",marker=dict(color="royalblue"),yaxis="y2"))
    fig.update_layout(title="📈 Pareto - Volume de CR Evitado",
                      xaxis=dict(title="Subcanais"),
                      yaxis=dict(title="Volume de CR Evitado"),
                      yaxis2=dict(title="Acumulado %",overlaying="y",side="right",range=[0,100]),
                      legend=dict(x=0.7,y=1.15,orientation="h"),bargap=0.2,
                      margin=dict(l=10,r=10,t=60,b=80))
    st.plotly_chart(fig,use_container_width=False)

    df_top = df_p[df_p["Acumulado %"]<=80]
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top[["Subcanal","Tribo","Volume de CR Evitado","Acumulado %"]],
                 use_container_width=False)

    tot_ev = int(df_lote["Volume de CR Evitado"].sum())
    top_names = ", ".join(df_top["Subcanal"].tolist())
    st.markdown(f"""**🧠 Insight Automático**  

- Volume total estimado de **CR evitado**: **{fmt_int(tot_ev)}**.  
- **{len(df_top)} subcanais** concentram **80 %** do potencial: **{top_names}**.  
- **Ação:** priorize estes subcanais para maximizar impacto.""")

    # Download Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer,engine="xlsxwriter") as w:
        df_lote.to_excel(w,sheet_name="Resultados",index=False)
        df_top.to_excel(w,sheet_name="Top_80_Pareto",index=False)
    st.download_button("📥 Baixar Excel Completo",buffer.getvalue(),
                       file_name="simulacao_cr.xlsx",
                       mime="application/vnd.ms-excel")
