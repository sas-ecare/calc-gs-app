# app_calculadora_ganhos.py
import io
import base64
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ====================== CONFIG INICIAL ======================
st.set_page_config(
    page_title="🖩 Calculadora de Ganhos",
    page_icon="📶",
    layout="wide",
)

# ====================== AUTENTICAÇÃO ======================
def check_password():
    def password_entered():
        st.session_state["authenticated"] = (
            st.session_state.get("password") == "claro@123"
        )
        if not st.session_state["authenticated"]:
            st.error("Senha incorreta. Tente novamente.")
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.text_input("🔐 Insira a senha para acessar:", type="password",
                      on_change=password_entered, key="password")
        st.stop()

check_password()

# ====================== LOGO E TÍTULO ======================
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    for d in [script_dir, script_dir/"assets", script_dir/"static", Path.cwd()]:
        for base in name_candidates:
            for ext in exts:
                p = d / f"{base}{ext}"
                if p.exists():
                    return p.read_bytes()
    return None

def load_logo_for_title():
    return _find_asset_bytes(["claro_logo", "logo_claro", "claro"])

logo_bytes = load_logo_for_title()
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(
        f"""
        <h1 style='text-align:center;color:#8B0000;font-size:56px;margin:6px 0 10px'>
          <img src='data:image/png;base64,{img_b64}' style='height:70px;vertical-align:middle;margin-right:12px'>
          Calculadora de Ganhos
        </h1>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown("<h1 style='text-align:center;color:#8B0000;font-size:52px'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

# ====================== PARÂMETROS FIXOS ======================
RETIDO_DICT = {"App": 0.916893598, "Bot": 0.883475537, "Web": 0.902710768}
CR_SEGMENTO = {"Móvel": 0.4947, "Residencial": 0.4989}
DEFAULT_TX_UU_CPF = 12.28

# ====================== CARREGAR BASE ======================
URL_PERFORMANCE_RAW = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL_PERFORMANCE_RAW, sheet_name="Tabela Performance")
    if "TP_META" in df.columns:
        df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    for c in ["VOL_KPI"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

df = carregar_dados()

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = col1.selectbox("📊 Segmento", segmentos)
subcanais = sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique())
subcanal = col2.selectbox("📌 Subcanal", subcanais)

df_sub = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == subcanal)]
tribo = df_sub["NM_TORRE"].dropna().unique().tolist()[0] if not df_sub.empty else "Indefinido"

# ====================== INFO CONTEXTO ======================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tribo", tribo)
c2.metric("Canal", tribo)
c3.metric("Segmento", segmento)
c4.metric("Subcanal", subcanal)

# ====================== PREMISSAS ======================
with st.expander("⚙️ Premissas utilizadas (fixas)", expanded=False):
    st.write(
        f"""
- **CR por segmento**: Móvel = {CR_SEGMENTO['Móvel']*100:.2f}%, Residencial = {CR_SEGMENTO['Residencial']*100:.2f}%  
- **% Retido 72h**: App = {RETIDO_DICT['App']*100:.2f}%, Bot = {RETIDO_DICT['Bot']*100:.2f}%, Web = {RETIDO_DICT['Web']*100:.2f}%  
- **TX UU / CPF (dinâmica)** = Transações ÷ Usuários únicos, fallback {DEFAULT_TX_UU_CPF:.2f} se não houver dados.  
- **Regra Retido (Dma)**: quando Tribo = Dma → usa **% Retido = Bot (88,35%)**.
- **Transações/Acessos mínimo**: valores < 1,00 → forçado para 1,00.
        """
    )

# ====================== INPUT ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros de Simulação")
volume_trans = st.number_input("📥 Volume de Transações", min_value=0, value=10_000, step=1000)

# ====================== FUNÇÃO FORMATAÇÃO ======================
def fmt_int(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    df_final = df_sub.copy()
    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    cr_segmento = CR_SEGMENTO.get(segmento, 0.50)
    # Transações e Acessos
    df_acc = df_final[df_final["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
    df_trn = df_final[df_final["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
    df_uu = df_final[df_final["NM_KPI"].str.contains("4.1 - Usuários", case=False, na=False)]

    vol_acc, vol_trn, vol_uu = df_acc["VOL_KPI"].sum(), df_trn["VOL_KPI"].sum(), df_uu["VOL_KPI"].sum()
    tx_trn_acc = (vol_trn / vol_acc) if vol_acc > 0 else 1.0
    if tx_trn_acc < 1:
        tx_trn_acc = 1.0

    # TX UU CPF dinâmica
    tx_uu_cpf = (vol_trn / vol_uu) if (vol_trn > 0 and vol_uu > 0) else DEFAULT_TX_UU_CPF

    # Regra DMA → Retido = BOT
    retido_base = RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])
    if str(tribo).strip().lower() == "dma":
        retido_base = RETIDO_DICT["Bot"]

    volume_acessos = volume_trans / tx_trn_acc
    mau_cpf = volume_trans / tx_uu_cpf
    cr_evitado = volume_acessos * cr_segmento * retido_base
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)

    # =================== RESULTADOS ===================
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transações / Acessos", f"{tx_trn_acc:.2f}")
    c2.metric("% CR do Segmento", f"{cr_segmento*100:.2f}%")
    c3.metric("% Retido (regra)", f"{retido_base*100:.2f}%")
    c4.metric("MAU (CPF)", fmt_int(mau_cpf))

    st.markdown(
        f"""
        <div style="
            max-width:480px;margin:18px auto;padding:18px 22px;
            background:linear-gradient(90deg,#b31313 0%, #d01f1f 60%, #e23a3a 100%);
            border-radius:18px; box-shadow:0 8px 18px rgba(139,0,0,.25); color:#fff;">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="font-weight:700;font-size:20px;">Volume de CR Evitado Estimado</div>
            <div style="font-weight:800;font-size:30px;background:#fff;color:#b31313;
                        padding:6px 16px;border-radius:12px;line-height:1">
              {fmt_int(cr_evitado_floor)}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Fórmulas: Volume de Acessos = Transações ÷ (Tx Transações/Acesso).  MAU = Transações ÷ (Transações/Usuários).  CR Evitado = Acessos × CR × % Retido.")

    # =================== TABELA LOTE ===================
    st.markdown("---")
    st.markdown("### 📄 Simulação - Todos os Subcanais")

    resultados = []
    for sub in subcanais:
        df_i = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == sub)]
        tribo_i = df_i["NM_TORRE"].dropna().unique().tolist()[0] if not df_i.empty else "Indefinido"
        df_t, df_a, df_u = (
            df_i[df_i["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)],
            df_i[df_i["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)],
            df_i[df_i["NM_KPI"].str.contains("4.1 - Usuários", case=False, na=False)],
        )
        vt, va, vu = df_t["VOL_KPI"].sum(), df_a["VOL_KPI"].sum(), df_u["VOL_KPI"].sum()
        tx = (vt / va) if va > 0 else 1.0
        if tx < 1:
            tx = 1.0
        tx_uu = (vt / vu) if (vt > 0 and vu > 0) else DEFAULT_TX_UU_CPF

        ret = RETIDO_DICT.get(tribo_i, RETIDO_DICT["Web"])
        if str(tribo_i).strip().lower() == "dma":
            ret = RETIDO_DICT["Bot"]

        cr_seg = CR_SEGMENTO.get(segmento, 0.50)
        vol_acc = volume_trans / tx
        mau = volume_trans / tx_uu
        est = np.floor(vol_acc * cr_seg * ret + 1e-9)
        resultados.append({
            "Subcanal": sub, "Tribo": tribo_i,
            "Transações / Acessos": round(tx, 2),
            "↓ % Retido": round(ret*100, 2),
            "% CR": round(cr_seg*100, 2),
            "Volume de Acessos": int(vol_acc),
            "MAU (CPF)": int(mau),
            "Volume de CR Evitado": int(est)
        })
    df_out = pd.DataFrame(resultados)
    st.dataframe(df_out, use_container_width=False)
