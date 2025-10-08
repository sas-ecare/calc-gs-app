import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np
import base64
from pathlib import Path
import plotly.graph_objects as go
import io
import requests

# ====================== CONFIG INICIAL ======================
st.set_page_config(
    page_title="🖩 Calculadora de Ganhos",
    page_icon="📶",
    layout="wide"
)

# ====================== AUTENTICAÇÃO COM SENHA ======================
def check_password():
    def password_entered():
        if st.session_state.get("password", "") == "claro@123":
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False
            st.error("Senha incorreta. Tente novamente.")

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.text_input("🔐 Insira a senha para acessar:", type="password", on_change=password_entered, key="password")
        st.stop()

check_password()

# ====================== FUNÇÕES DE ASSETS (LOGO NO TÍTULO) ======================
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    search_dirs = [
        script_dir,
        script_dir / "assets",
        script_dir / "static",
        Path.cwd().resolve(),
        Path.cwd().resolve() / "assets",
        Path.cwd().resolve() / "static",
    ]
    for d in search_dirs:
        for base in name_candidates:
            for ext in exts:
                p = d / f"{base}{ext}"
                if p.exists():
                    try:
                        return p.read_bytes()
                    except Exception:
                        pass
    return None

def load_logo_for_title():
    return _find_asset_bytes(["claro_logo", "logo_claro", "claro"])

# ====================== TÍTULO COM LOGO ======================
logo_bytes = load_logo_for_title()
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(
        f"""
        <h1 style='text-align: center; color: #8B0000; font-size: 60px;'>
            <img src='data:image/png;base64,{img_b64}' style='height:80px; vertical-align:middle; margin-right:15px'>
            Calculadora de Ganhos
        </h1>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        "<h1 style='text-align: center; color: #8B0000; font-size: 50px;'>🖩 Calculadora de Ganhos</h1>",
        unsafe_allow_html=True
    )

# ====================== CARGA DOS DADOS (GITHUB OU UPLOAD) ======================
URL_GITHUB = "https://github.com/gustavo3-freitas/base_calculadora/raw/main/Calculadora%20de%20Ganho%202.xlsx"

st.caption("Fonte dos dados: GitHub (automático) ou upload manual do mesmo layout.")

uploaded = st.file_uploader("📂 (Opcional) Envie o Excel com as abas 'Tabela Performance' e 'BASE APOIO'", type=["xlsx"])

@st.cache_data(show_spinner=False)
def carregar_dados(_uploaded_file_bytes: bytes | None):
    if _uploaded_file_bytes:
        xls = pd.ExcelFile(io.BytesIO(_uploaded_file_bytes))
    else:
        response = requests.get(URL_GITHUB)
        if response.status_code != 200:
            st.error(f"❌ Falha ao acessar o arquivo no GitHub (HTTP {response.status_code}).")
            st.stop()
        xls = pd.ExcelFile(io.BytesIO(response.content))

    # --------- TABELA PERFORMANCE ---------
    df_perf = pd.read_excel(xls, sheet_name="Tabela Performance")
    df_perf["ANOMES"] = pd.to_datetime(df_perf["ANOMES"].astype(str), format="%Y%m", errors="coerce")
    df_perf["VOL_KPI"] = pd.to_numeric(df_perf["VOL_KPI"], errors="coerce")
    df_perf["CR_DIR"] = pd.to_numeric(df_perf["CR_DIR"], errors="coerce")

    # --------- BASE APOIO ---------
    df_apoio_raw = pd.read_excel(xls, sheet_name="BASE APOIO", header=None)
    table = df_apoio_raw.fillna("")
    apoio = {
        "CR": {"Móvel": 0.4947, "Residencial": 0.4989},
        "RETIDO": {"App": 0.9169, "Bot": 0.8835, "Web": 0.9027},
        "TX_UU_CPF": 0.1228
    }

    for r in range(table.shape[0]):
        row = [str(x).strip() for x in table.iloc[r].tolist()]
        # Detecta CR
        if any("cr" == v.lower() for v in row):
            for rr in range(r+1, min(r+10, table.shape[0])):
                a = str(table.iloc[rr, 0]).strip().lower()
                val = str(table.iloc[rr, 1]).strip()
                try:
                    num = float(val.replace("%", "").replace(",", "."))
                    if "mó" in a or "mov" in a:
                        apoio["CR"]["Móvel"] = num/100 if num > 1 else num
                    if "res" in a:
                        apoio["CR"]["Residencial"] = num/100 if num > 1 else num
                except:
                    pass
        # Retido Digital
        if any("retido" in v.lower() for v in row):
            for rr in range(r+1, min(r+10, table.shape[0])):
                canal = str(table.iloc[rr, 0]).strip().capitalize()
                val = str(table.iloc[rr, 1]).strip()
                if canal in ["App", "Bot", "Web"]:
                    try:
                        num = float(val.replace("%", "").replace(",", "."))
                        apoio["RETIDO"][canal] = num/100 if num > 1 else num
                    except:
                        pass
        # TX UU CPF
        if any("tx uu cpf" in v.lower() for v in row):
            for c in range(table.shape[1]):
                try:
                    num = float(str(table.iloc[r, c]).replace("%", "").replace(",", "."))
                    if 0 < num <= 100:
                        apoio["TX_UU_CPF"] = num/100 if num > 1 else num
                except:
                    pass

    return df_perf, apoio

file_bytes = uploaded.getvalue() if uploaded else None
df, apoio_params = carregar_dados(file_bytes)

# ====================== TAXAS ======================
CR_SEGMENTO = apoio_params["CR"]
RETIDO_DICT = apoio_params["RETIDO"]
TX_UU_CPF = apoio_params["TX_UU_CPF"]

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)

segmentos_disp = sorted(df["SEGMENTO"].dropna().astype(str).unique())
segmento = col2.selectbox("📶 Segmento", segmentos_disp)

df_seg = df[(df["SEGMENTO"] == segmento) & (df["TP_META"].astype(str).str.lower() == "real")]
subcanais_disp = sorted(df_seg["NM_SUBCANAL"].dropna().astype(str).unique())
subcanal = st.selectbox("📌 Subcanal", subcanais_disp)

df_subcanal = df_seg[df_seg["NM_SUBCANAL"] == subcanal]
tribo_detectada = df_subcanal["NM_TORRE"].dropna().astype(str).unique()
tribo = tribo_detectada[0] if len(tribo_detectada) else "Indefinido"

cA, cB, cC, cD = st.columns(4)
cA.metric("Tribo", tribo)
cB.metric("Canal", tribo)
cC.metric("Segmento", segmento)
cD.metric("Subcanal", subcanal)

retido_pct = RETIDO_DICT.get(tribo, 1.0)

# ====================== PARÂMETROS ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros para Simulação")
colx, _ = st.columns([2,1])
volume_trans_esperado = colx.number_input("📥 Insira o volume de **Transações**", min_value=0, value=10000)

# ====================== CÁLCULOS ======================
def _pick_acessos_df(_df):
    return _df[_df["NM_KPI"].str.contains("Acesso|Usu.rio", case=False, na=False)]

def _pick_trans_df(_df):
    return _df[_df["NM_KPI"].str.contains("7.1 - Transa", case=False, na=False)]

if st.button("🚀 Calcular Ganhos Potenciais"):
    df_final = df_subcanal.copy()
    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    cr_segmento = CR_SEGMENTO.get(segmento, np.nan)
    if pd.isna(cr_segmento):
        cr_segmento = df_final["CR_DIR"].mean()
        cr_segmento = cr_segmento if cr_segmento <= 1 else cr_segmento/100

    df_acessos = _pick_acessos_df(df_final)
    df_trans = _pick_trans_df(df_final)
    vol_acessos_hist = pd.to_numeric(df_acessos["VOL_KPI"], errors="coerce").sum()
    vol_trans_hist = pd.to_numeric(df_trans["VOL_KPI"], errors="coerce").sum()

    tx_trans_acessos = vol_trans_hist / vol_acessos_hist if vol_acessos_hist > 0 else 1.75
    acessos_estimados = volume_trans_esperado / tx_trans_acessos if tx_trans_acessos > 0 else 0
    cr_evitado = (volume_trans_esperado / tx_trans_acessos) * cr_segmento * retido_pct
    mau_cpf = acessos_estimados * TX_UU_CPF

    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    c1, c2, c3 = st.columns(3)
    c1.metric("Transações / Acessos", f"{tx_trans_acessos:.2f}")
    c2.metric("CR Segmento (%)", f"{cr_segmento*100:.2f}")
    c3.metric(f"% Retido ({tribo})", f"{retido_pct*100:.2f}")

    st.success(f"✅ Volume de CR Evitado Estimado: **{f'{cr_evitado:,.0f}'.replace(',', '.')}**")
    st.caption("Fórmula: Volume Transações ÷ (Transações/Acessos) × CR × % Retido")

    c4, c5, c6 = st.columns(3)
    c4.metric("📉 Volume Ligações Evitadas", f"{f'{cr_evitado:,.0f}'.replace(',', '.')}")
    c5.metric("📊 Volume de Acessos", f"{f'{acessos_estimados:,.0f}'.replace(',', '.')}")
    c6.metric("👤 Volume de MAU (CPF)", f"{f'{mau_cpf:,.0f}'.replace(',', '.')}")

    st.markdown("---")
    st.markdown("### 📄 Simulação para Todos os Subcanais")
    resultados_lote = []
    for sub in subcanais_disp:
        df_sub = df_seg[df_seg["NM_SUBCANAL"] == sub]
        tribo_lote = df_sub["NM_TORRE"].dropna().astype(str).unique()
        tribo_lote = tribo_lote[0] if len(tribo_lote) else "Indefinido"
        ret_lote = RETIDO_DICT.get(tribo_lote, 1.0)
        df_acc_lote = _pick_acessos_df(df_sub)
        df_trn_lote = _pick_trans_df(df_sub)
        acc = pd.to_numeric(df_acc_lote["VOL_KPI"], errors="coerce").sum()
        trn = pd.to_numeric(df_trn_lote["VOL_KPI"], errors="coerce").sum()
        tx = trn/acc if acc > 0 else 1.75
        cr_lote = CR_SEGMENTO.get(segmento, 0.5)
        estimado = (volume_trans_esperado / tx) * cr_lote * ret_lote
        resultados_lote.append({
            "Subcanal": sub,
            "Tribo": tribo_lote,
            "Transações / Acessos": round(tx, 2),
            "% Retido": round(ret_lote*100, 2),
            "% CR": round(cr_lote*100, 2),
            "Volume de CR Evitado": round(estimado)
        })

    df_lote = pd.DataFrame(resultados_lote)
    st.dataframe(df_lote, use_container_width=True)

    # ===== PARETO =====
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
    df_pareto["Acumulado %"] = 100 * df_pareto["Acumulado"] / df_pareto["Volume de CR Evitado"].sum()
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(
        x=df_pareto["Subcanal"], y=df_pareto["Volume de CR Evitado"],
        name="Volume de CR Evitado", marker_color=df_pareto["Cor"]
    ))
    fig_pareto.add_trace(go.Scatter(
        x=df_pareto["Subcanal"], y=df_pareto["Acumulado %"],
        name="Acumulado %", mode="lines+markers", marker=dict(color="royalblue"), yaxis="y2"
    ))
    fig_pareto.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0,100]),
        legend=dict(x=0.75, y=1.15, orientation="h"), bargap=0.2
    )
    st.plotly_chart(fig_pareto, use_container_width=True)

    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top80[["Subcanal", "Tribo", "Volume de CR Evitado", "Acumulado %"]], use_container_width=True)

    # ===== INSIGHT =====
    total_ev = df_lote["Volume de CR Evitado"].sum()
    total_ev_fmt = f"{total_ev:,.0f}".replace(",", ".")
    top80_names = ", ".join(df_top80["Subcanal"].tolist())
    insight_text = (
        f"🧠 **Insight Automático**  \n"
        f"- O volume total estimado de **CR evitado** é **{total_ev_fmt}**.  \n"
        f"- Apenas **{len(df_top80)} subcanais** concentram **80%** do potencial de ganho.  \n"
        f"- Subcanais prioritários: **{top80_names}**.  \n"
        f"👉 Recomenda-se priorizar estes subcanais para maximizar o impacto."
    )
    st.markdown(insight_text)

    # ===== DOWNLOAD EXCEL =====
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_lote.to_excel(writer, sheet_name="Resultados", index=False)
        df_top80.to_excel(writer, sheet_name="Top_80_Pareto", index=False)
    st.download_button("📥 Baixar Excel Completo", buffer.getvalue(), "simulacao_cr.xlsx", "application/vnd.ms-excel")
