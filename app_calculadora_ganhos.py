# app_calculadora_ganhos.py — versão final (debug diagnóstico)
# Exibe linhas filtradas e valores reais dos KPIs carregados.

import io, base64
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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

# ====================== BASE ======================
URL = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance_v2.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL, sheet_name="Tabela Performance")
    df = df[df["TP_META"].astype(str).str.lower().eq("real")].copy()
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce").fillna(0)
    df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype(int)
    df["NM_KPI"] = df["NM_KPI"].astype(str).str.strip().str.lower()
    return df

df = carregar_dados()

# ====================== HELPERS ======================
def fmt_int(x):
    try:
        return f"{np.floor(float(x)+1e-9):,.0f}".replace(",", ".")
    except:
        return "0"

def regra_retido_por_tribo(tribo):
    if str(tribo).strip().lower() == "dma":
        return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])

# ====================== FUNÇÕES DE LEITURA ======================
def get_volumes(df, segmento, subcanal, anomes):
    """Retorna volumes de transacoes, usuarios_unicos_cpf e acessos com filtros exatos."""
    df_f = df[
        (df["SEGMENTO"] == segmento)
        & (df["NM_SUBCANAL"] == subcanal)
        & (df["ANOMES"] == anomes)
        & (df["TP_META"].astype(str).str.lower() == "real")
    ].copy()

    st.info(f"🔎 Linhas filtradas — Segmento: {segmento}, Subcanal: {subcanal}, ANOMES: {anomes}")
    st.dataframe(df_f[["ANOMES","SEGMENTO","NM_SUBCANAL","NM_KPI","VOL_KPI"]], use_container_width=True)

    vol_71 = df_f.loc[df_f["NM_KPI"] == "transacoes", "VOL_KPI"].sum()
    vol_41 = df_f.loc[df_f["NM_KPI"] == "usuarios_unicos_cpf", "VOL_KPI"].sum()
    vol_6  = df_f.loc[df_f["NM_KPI"] == "acessos", "VOL_KPI"].sum()

    st.info(f"📊 Volumes encontrados → Transações: {vol_71} | Usuários Únicos CPF: {vol_41} | Acessos: {vol_6}")
    return float(vol_71), float(vol_41), float(vol_6)

def tx_trn_por_acesso(vol_71, vol_6):
    if vol_6 <= 0:
        return 1.0
    return max(vol_71 / vol_6, 1.0)

def tx_uu_por_cpf(vol_71, vol_41):
    if vol_41 <= 0:
        return DEFAULT_TX_UU_CPF
    return vol_71 / vol_41

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
c1, c2, c3 = st.columns(3)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 Segmento", segmentos)

anomes_unicos = sorted(df["ANOMES"].unique())
meses_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
mes_legivel = [f"{meses_map[int(str(a)[4:]) ]}/{str(a)[:4]}" for a in anomes_unicos]
map_anomes_legivel = dict(zip(mes_legivel, anomes_unicos))
anomes_legivel = c2.selectbox("🗓️ Mês", mes_legivel, index=len(mes_legivel)-1)
anomes_escolhido = map_anomes_legivel[anomes_legivel]

subcanais = sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique())
subcanal = c3.selectbox("📌 Subcanal", subcanais)

df_sub = df[
    (df["SEGMENTO"] == segmento)
    & (df["NM_SUBCANAL"] == subcanal)
    & (df["ANOMES"] == anomes_escolhido)
]
tribo = df_sub["NM_TORRE"].dropna().unique().tolist()[0] if not df_sub.empty else "Indefinido"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tribo", tribo)
c2.metric("Canal", tribo)
c3.metric("Segmento", segmento)
c4.metric("Subcanal", subcanal)

# ====================== INPUT ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros de Simulação")
volume_trans = st.number_input("📥 Volume de Transações", min_value=0, value=10_000, step=1000)

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    vol_71, vol_41, vol_6 = get_volumes(df, segmento, subcanal, anomes_escolhido)
    tx_trn_acc = tx_trn_por_acesso(vol_71, vol_6)
    tx_uu_cpf = tx_uu_por_cpf(vol_71, vol_41)
    cr_segmento = CR_SEGMENTO.get(segmento, 0.50)
    retido = regra_retido_por_tribo(tribo)

    vol_acessos = volume_trans / tx_trn_acc if tx_trn_acc > 0 else 0
    mau_cpf = volume_trans / tx_uu_cpf if tx_uu_cpf > 0 else 0
    cr_evitado = vol_acessos * cr_segmento * retido
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)

    st.success(f"✅ Volumes lidos corretamente → Transações: {fmt_int(vol_71)} | Usuários Únicos CPF: {fmt_int(vol_41)} | Acessos: {fmt_int(vol_6)}")

    # Resultados
    st.markdown("---")
    st.markdown("### 📊 Resultados Detalhados (Fórmulas)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Volume de Transações", fmt_int(volume_trans))
    c2.metric("Taxa Transação × Acesso", f"{tx_trn_acc:.2f}")
    c3.metric("% Ligação Direcionada Humano", f"{cr_segmento*100:.2f}%")
    c4, c5, c6 = st.columns(3)
    c4.metric("Retido Digital 72h", f"{retido*100:.2f}%")
    c5.metric("Volume de Acessos", fmt_int(vol_acessos))
    c6.metric("Volume de MAU (CPF)", fmt_int(mau_cpf))

    with st.expander("🔍 Diagnóstico de Premissas", expanded=False):
        st.markdown(f"""
        **Segmento:** {segmento}  
        **Subcanal:** {subcanal}  
        **Tribo:** {tribo}  
        **ANOMES:** {anomes_escolhido}  

        | Item | Valor |
        |------|------:|
        | Volume transacoes | {fmt_int(vol_71)} |
        | Volume usuarios_unicos_cpf | {fmt_int(vol_41)} |
        | Volume acessos | {fmt_int(vol_6)} |
        | **Tx Transações/Acessos** | {tx_trn_acc:.2f} |
        | **Tx UU/CPF** | {tx_uu_cpf:.2f} |
        | CR Segmento | {cr_segmento*100:.2f}% |
        | % Retido Aplicado | {retido*100:.2f}% |
        """, unsafe_allow_html=True)
