# app_calculadora_ganhos.py
import io
import base64
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ====================== CONFIG INICIAL ======================
st.set_page_config(page_title="🖩 Calculadora de Ganhos", page_icon="📶", layout="wide")

# ====================== AUTENTICAÇÃO ======================
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

# ====================== LOGO/TÍTULO ======================
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

# ====================== PARÂMETROS FIXOS ======================
RETIDO_DICT = {"App": 0.9169, "Bot": 0.8835, "Web": 0.9027}
CR_SEGMENTO = {"Móvel": 0.4947, "Residencial": 0.4989}
DEFAULT_TX_UU_CPF = 12.28

# ====================== CARREGAR BASE ======================
URL_PERFORMANCE_RAW = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL_PERFORMANCE_RAW, sheet_name="Tabela Performance")
    if "TP_META" in df.columns:
        df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce")
    return df

df = carregar_dados()

# ====================== FUNÇÕES ======================
def fmt_int(x: float) -> str:
    return f"{np.floor(x + 1e-9):,.0f}".replace(",", ".")

def sum_kpi(df_scope: pd.DataFrame, patterns):
    """Soma VOL_KPI de linhas cujo NM_KPI contenha QUALQUER padrão listado."""
    m = False
    for pat in patterns:
        m = m | df_scope["NM_KPI"].str.contains(pat, case=False, na=False, regex=True)
    return df_scope.loc[m, "VOL_KPI"].sum()

def tx_trans_por_acesso(df_scope: pd.DataFrame) -> float:
    vt = sum_kpi(df_scope, [r"7\.1\s*-\s*Transa", "Transações"])
    va = sum_kpi(df_scope, [r"6\s*-\s*Acesso", "Acessos"])
    if va <= 0:
        return 1.0
    tx = vt / va
    return max(tx, 1.0)

def tx_uu_cpf_dyn(df_all: pd.DataFrame, segmento: str, subcanal: str) -> float:
    df_seg = df_all[df_all["SEGMENTO"] == segmento]
    df_sub = df_seg[df_seg["NM_SUBCANAL"] == subcanal]
    vt_sub = sum_kpi(df_sub, [r"7\.1\s*-\s*Transa", "Transações"])
    vu_sub = sum_kpi(df_sub, [r"4\.1\s*-\s*Usu", "Usuár", "Único", "CPF"])
    if vt_sub > 0 and vu_sub > 0:
        return vt_sub / vu_sub
    vt_seg = sum_kpi(df_seg, [r"7\.1\s*-\s*Transa", "Transações"])
    vu_seg = sum_kpi(df_seg, [r"4\.1\s*-\s*Usu", "Usuár", "Único", "CPF"])
    if vt_seg > 0 and vu_seg > 0:
        return vt_seg / vu_seg
    return DEFAULT_TX_UU_CPF

def regra_retido_por_tribo(tribo: str) -> float:
    if str(tribo).strip().lower() == "dma":
        return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = col1.selectbox("📊 Segmento", segmentos)
subcanais = sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique())
subcanal = col2.selectbox("📌 Subcanal", subcanais)

df_sub = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == subcanal)]
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

# ====================== CÁLCULO ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    if df_sub.empty:
        st.warning("❌ Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    # Fórmulas
    tx_trn_acc = tx_trans_por_acesso(df_sub)
    cr_segmento = CR_SEGMENTO.get(segmento, 0.50)
    retido_base = regra_retido_por_tribo(tribo)
    tx_uu_cpf = tx_uu_cpf_dyn(df, segmento, subcanal)

    volume_acessos = volume_trans / tx_trn_acc
    mau_cpf = volume_trans / (tx_uu_cpf if tx_uu_cpf > 0 else DEFAULT_TX_UU_CPF)
    cr_evitado = volume_acessos * cr_segmento * retido_base
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)

    # =================== RESULTADOS ===================
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Transações / Acessos", f"{tx_trn_acc:.2f}")
    r2.metric("% CR do Segmento", f"{cr_segmento*100:.2f}%")
    r3.metric("% Retido (72h)", f"{retido_base*100:.2f}%")
    r4.metric("MAU (CPF)", fmt_int(mau_cpf))

    # KPI destaque
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

    # =================== TABELA LOTE ===================
    resultados = []
    for sub in subcanais:
        df_i = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == sub)]
        tribo_i = df_i["NM_TORRE"].dropna().unique().tolist()[0] if not df_i.empty else "Indefinido"
        tx_i = tx_trans_por_acesso(df_i)
        tx_uu_i = tx_uu_cpf_dyn(df, segmento, sub)
        ret_i = regra_retido_por_tribo(tribo_i)
        cr_seg_i = CR_SEGMENTO.get(segmento, 0.50)

        vol_acc_i = volume_trans / tx_i
        mau_i = volume_trans / (tx_uu_i if tx_uu_i > 0 else DEFAULT_TX_UU_CPF)
        est_i = np.floor(vol_acc_i * cr_seg_i * ret_i + 1e-9)

        resultados.append({
            "Subcanal": sub,
            "Tribo": tribo_i,
            "Transações / Acessos": round(tx_i, 2),
            "% CR": round(cr_seg_i*100, 2),
            "↓ % Retido": round(ret_i*100, 2),
            "Volume de Acessos": int(vol_acc_i),
            "MAU (CPF)": int(mau_i),
            "Volume de CR Evitado": int(est_i),
        })

    df_lote = pd.DataFrame(resultados)
   
