# app_calculadora_ganhos.py
import io
import base64
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

# ============== CONFIG ==============
st.set_page_config(page_title="🖩 Calculadora de Ganhos", page_icon="📶", layout="wide")

# ============== LOGIN ==============
def check_password():
    def password_entered():
        st.session_state["authenticated"] = (st.session_state.get("password") == "claro@123")
        if not st.session_state["authenticated"]:
            st.error("Senha incorreta. Tente novamente.")
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.text_input("🔐 Insira a senha para acessar:", type="password",
                      on_change=password_entered, key="password")
        st.stop()
check_password()

# ============== LOGO / TÍTULO ==============
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    for d in [script_dir, script_dir/"assets", script_dir/"static", Path.cwd(), Path.cwd()/ "assets", Path.cwd()/ "static"]:
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

# ============== PARÂMETROS FIXOS ==============
CR_SEGMENTO = {"Móvel": 0.4947, "Residencial": 0.4989}  # 49,47% / 49,89%
RETIDO_DICT  = {"App": 0.9169, "Bot": 0.8835, "Web": 0.9027}
DEFAULT_TX_UU_CPF = 12.28  # fallback final

# ============== BASE ==============
URL_PERFORMANCE_RAW = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL_PERFORMANCE_RAW, sheet_name="Tabela Performance")
    # manter apenas Real
    if "TP_META" in df.columns:
        df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    for c in ["VOL_KPI"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

df = carregar_dados()

# ============== HELPERS ==============
def fmt_int(x: float) -> str:
    return f"{np.floor(x + 1e-9):,.0f}".replace(",", ".")

def _sum_kpi(df_scope: pd.DataFrame, must_have: list[str]) -> float:
    """Soma VOL_KPI onde NM_KPI contém *todas* as palavras de must_have (case-insensitive)."""
    if df_scope.empty:
        return 0.0
    s = df_scope["NM_KPI"].astype(str).str.lower()
    mask = True
    for token in must_have:
        mask &= s.str.contains(token.lower(), na=False)
    return df_scope.loc[mask, "VOL_KPI"].sum()

def tx_trans_por_acesso(df_scope: pd.DataFrame) -> float:
    vt = _sum_kpi(df_scope, ["7.1", "transa"])         # "7.1 - Transações"
    va = _sum_kpi(df_scope, ["6", "acesso"])           # "6 - Acessos" (ou "Acessos Usuários")
    if va <= 0:
        return 1.0
    tx = vt / va
    return max(tx, 1.0)                                # minimo 1,00

def tx_uu_cpf_dyn(df_all: pd.DataFrame, segmento: str, subcanal: str) -> float:
    """
    Tx_UU_CPF = Transações / Usuários Únicos (CPF).
    1) tenta no Subcanal
    2) se vazio, tenta no Segmento
    3) se vazio, fallback 12,28
    """
    df_seg = df_all[df_all["SEGMENTO"] == segmento]

    # Subcanal
    df_sub = df_seg[df_seg["NM_SUBCANAL"] == subcanal]
    vt_sub = _sum_kpi(df_sub, ["7.1", "transa"])
    vu_sub = _sum_kpi(df_sub, ["4.1", "usuár", "únic"])  # "4.1 - Usuários Únicos (CPF)"
    if vt_sub > 0 and vu_sub > 0:
        return vt_sub / vu_sub

    # Segmento
    vt_seg = _sum_kpi(df_seg, ["7.1", "transa"])
    vu_seg = _sum_kpi(df_seg, ["4.1", "usuár", "únic"])
    if vt_seg > 0 and vu_seg > 0:
        return vt_seg / vu_seg

    return DEFAULT_TX_UU_CPF

def retido_por_tribo(tribo: str) -> float:
    """DMA herda Bot (88,35%)."""
    if str(tribo).strip().lower() == "dma":
        return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])

# ============== FILTROS ==============
st.markdown("### 🔎 Filtros de Cenário")
c1, c2 = st.columns(2)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 Segmento", segmentos)
subcanais = sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique().tolist())
subcanal = c2.selectbox("📌 Subcanal", subcanais)

df_sub = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == subcanal)]
tribo = df_sub["NM_TORRE"].dropna().unique().tolist()[0] if not df_sub.empty else "Indefinido"

k1, k2, k3, k4 = st.columns(4)
k1.metric("Tribo", tribo)
k2.metric("Canal", tribo)
k3.metric("Segmento", segmento)
k4.metric("Subcanal", subcanal)

with st.expander("⚙️ Premissas utilizadas (fixas)", expanded=False):
    st.write(
        f"""
- **%CR**: Móvel = {CR_SEGMENTO['Móvel']*100:.2f}% | Residencial = {CR_SEGMENTO['Residencial']*100:.2f}%  
- **%Retido 72h**: App = {RETIDO_DICT['App']*100:.2f}% | Bot = {RETIDO_DICT['Bot']*100:.2f}% | Web = {RETIDO_DICT['Web']*100:.2f}%  
- **DMA** usa **%Retido do Bot (88,35%)**.  
- **Tx Trans/Acesso** < 1 → **força 1,00**.  
- **MAU (CPF)**: Tx_UU_CPF calculado (subcanal→segmento→fallback 12,28).
        """
    )

# ============== INPUT ==============
st.markdown("---")
st.markdown("### ➗ Parâmetros de Simulação")
volume_trans = st.number_input("📥 Volume de Transações", min_value=0, value=10_000, step=1000)

# ============== CÁLCULO ==============
if st.button("🚀 Calcular Ganhos Potenciais"):
    if df_sub.empty:
        st.warning("❌ Nenhum dado encontrado para os filtros.")
        st.stop()

    # 2) Tx Trans/Acesso
    tx_trn_acc = tx_trans_por_acesso(df_sub)

    # 3) %CR do segmento
    cr_seg = CR_SEGMENTO.get(segmento, 0.50)

    # 4) %Retido (DMA herda Bot)
    retido = retido_por_tribo(tribo)

    # 6) Volume de Acessos
    vol_acessos = volume_trans / tx_trn_acc

    # 7) MAU (CPF) = Transações / (Transações/Usuários Únicos)
    tx_uu_cpf = tx_uu_cpf_dyn(df, segmento, subcanal)
    mau_cpf = volume_trans / (tx_uu_cpf if tx_uu_cpf > 0 else DEFAULT_TX_UU_CPF)

    # 5) Volume de Ligações Evitadas (CR Evitado)
    cr_evitado = vol_acessos * cr_seg * retido
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)

    # ===== cards superiores =====
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Transações / Acessos", f"{tx_trn_acc:.2f}")
    r2.metric("% CR do Segmento", f"{cr_seg*100:.2f}%")
    r3.metric("% Retido (72h)", f"{retido*100:.2f}%")
    r4.metric("MAU (CPF)", fmt_int(mau_cpf))

    # KPI premium (gradiente)
    st.markdown(
        f"""
        <div style="
            max-width:520px;margin:18px auto;padding:18px 22px;
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

    # ===== blocos estilo planilha (3 linhas finais) =====
    st.markdown("### 📄 Bloco de Saída (estilo planilha)")
    b1, b2, b3 = st.columns(3)
    b1.metric("Volume Ligações Evitadas Humano", fmt_int(cr_evitado_floor))
    b2.metric("Volume de Acessos", fmt_int(vol_acessos))
    b3.metric("Volume de MAU (CPF)", fmt_int(mau_cpf))

    st.caption("Fórmulas: "
               "Acessos = Transações ÷ (Tx Trans/Acesso) • "
               "MAU = Transações ÷ (Transações/Usuários Únicos) • "
               "CR Evitado = Acessos × CR × %Retido.")
