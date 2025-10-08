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

# ====================== AUTENTICAÇÃO ======================
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

# ====================== LOGO / TÍTULO ======================
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    search_dirs = [script_dir, script_dir / "assets", script_dir / "static", Path.cwd(), Path.cwd() / "assets"]
    for d in search_dirs:
        for base in name_candidates:
            for ext in exts:
                p = d / f"{base}{ext}"
                if p.exists():
                    return p.read_bytes()
    return None

logo_bytes = _find_asset_bytes(["claro_logo", "logo_claro", "claro"])
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(
        f"<h1 style='text-align:center;color:#8B0000;font-size:60px;'>"
        f"<img src='data:image/png;base64,{img_b64}' style='height:80px;vertical-align:middle;margin-right:15px'>"
        f"Calculadora de Ganhos</h1>", unsafe_allow_html=True)
else:
    st.markdown("<h1 style='text-align:center;color:#8B0000;font-size:50px;'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

# ====================== CARGA DE DADOS ======================
URL_GITHUB = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Calculadora%20de%20Ganho%202.xlsx"
uploaded = st.file_uploader("📂 (Opcional) Envie o Excel atualizado", type=["xlsx"])

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

    # -------- TABELA PERFORMANCE --------
    df_perf = pd.read_excel(xls, sheet_name="Tabela Performance")
    df_perf["ANOMES"] = pd.to_datetime(df_perf["ANOMES"].astype(str), format="%Y%m", errors="coerce")
    df_perf["VOL_KPI"] = pd.to_numeric(df_perf["VOL_KPI"], errors="coerce")

    # Detectar coluna de CR (caso mude nome)
    col_cr = next((c for c in df_perf.columns if "CR" in c.upper()), None)
    if col_cr:
        df_perf["CR_DIR"] = pd.to_numeric(df_perf[col_cr], errors="coerce")
    else:
        df_perf["CR_DIR"] = np.nan

    # -------- BASE DE APOIO (busca automática) --------
    apoio_sheet = None
    for s in xls.sheet_names:
        if "apoio" in s.lower():
            apoio_sheet = s
            break

    if apoio_sheet:
        df_apoio_raw = pd.read_excel(xls, sheet_name=apoio_sheet, header=None)
    else:
        st.warning("⚠️ Nenhuma aba de apoio encontrada no arquivo (ex: 'Base de Apoio'). Usando valores padrão.")
        df_apoio_raw = pd.DataFrame()

    table = df_apoio_raw.fillna("") if not df_apoio_raw.empty else pd.DataFrame()
    apoio = {
        "CR": {"Móvel": 0.4947, "Residencial": 0.4989},
        "RETIDO": {"App": 0.9169, "Bot": 0.8835, "Web": 0.9027},
        "TX_UU_CPF": 0.1228
    }

    # tentativa de leitura real dos valores
    try:
        for r in range(table.shape[0]):
            row = [str(x).strip() for x in table.iloc[r].tolist()]
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
            if any("tx uu cpf" in v.lower() for v in row):
                for c in range(table.shape[1]):
                    try:
                        num = float(str(table.iloc[r, c]).replace("%", "").replace(",", "."))
                        if 0 < num <= 100:
                            apoio["TX_UU_CPF"] = num/100 if num > 1 else num
                    except:
                        pass
    except Exception as e:
        st.warning(f"⚠️ Erro ao processar Base de Apoio: {e}")

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

colA, colB, colC, colD = st.columns(4)
colA.metric("Tribo", tribo)
colB.metric("Canal", tribo)
colC.metric("Segmento", segmento)
colD.metric("Subcanal", subcanal)

retido_pct = RETIDO_DICT.get(tribo, 1.0)

# ====================== PARÂMETROS ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros para Simulação")
colx, _ = st.columns([2,1])
volume_trans_esperado = colx.number_input("📥 Insira o volume de **Transações**", min_value=0, value=10000)

# ====================== CÁLCULOS ======================
def _pick_acessos_df(_df): return _df[_df["NM_KPI"].str.contains("Acesso|Usu.rio", case=False, na=False)]
def _pick_trans_df(_df): return _df[_df["NM_KPI"].str.contains("Transa", case=False, na=False)]

if st.button("🚀 Calcular Ganhos Potenciais"):
    df_final = df_subcanal.copy()
    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    cr_segmento = CR_SEGMENTO.get(segmento, np.nan)
    if pd.isna(cr_segmento):
        cr_segmento = df_final["CR_DIR"].mean()
        cr_segmento = cr_segmento if cr_segmento <= 1 else cr_segmento/100

    df_acc = _pick_acessos_df(df_final)
    df_trn = _pick_trans_df(df_final)
    acc_sum = pd.to_numeric(df_acc["VOL_KPI"], errors="coerce").sum()
    trn_sum = pd.to_numeric(df_trn["VOL_KPI"], errors="coerce").sum()
    tx_trans_acc = trn_sum / acc_sum if acc_sum > 0 else 1.75

    cr_evitado = (volume_trans_esperado / tx_trans_acc) * cr_segmento * retido_pct
    acessos_estimados = volume_trans_esperado / tx_trans_acc
    mau_cpf = acessos_estimados * TX_UU_CPF

    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    c1, c2, c3 = st.columns(3)
    c1.metric("Transações / Acessos", f"{tx_trans_acc:.2f}")
    c2.metric("CR Segmento (%)", f"{cr_segmento*100:.2f}")
    c3.metric(f"% Retido ({tribo})", f"{retido_pct*100:.2f}")

   
    c4, c5, c6 = st.columns(3)
    c4.metric("📉 Ligações Evitadas", valor_formatado)
    c5.metric("📊 Volume de Acessos", f"{acessos_estimados:,.0f}".replace(",", "."))
    c6.metric("👤 MAU (CPF)", f"{mau_cpf:,.0f}".replace(",", "."))


    # ====================== RESULTADO DESTACADO ======================
    valor_formatado = f"{cr_evitado:,.0f}".replace(",", ".")

    st.markdown(
    f"""
    <div style='background-color:#f8f9fa;
                border:2px solid #8B0000;
                border-radius:12px;
                padding:20px;
                margin-top:20px;
                text-align:center;
                color:#8B0000;
                font-size:42px;
                font-weight:bold;
                box-shadow:0 4px 10px rgba(0,0,0,0.1);'>
        ✅ Volume de CR Evitado Estimado:<br>
        <span style='font-size:56px;'>{valor_formatado}</span>
    </div>
    """,
    unsafe_allow_html=True
    )


    # ====================== SIMULAÇÃO EM LOTE ======================
    st.markdown("---")
    st.markdown("### 📄 Simulação para Todos os Subcanais")
    resultados = []
    for sub in subcanais_disp:
        df_sub = df_seg[df_seg["NM_SUBCANAL"] == sub]
        tribo_lote = df_sub["NM_TORRE"].dropna().astype(str).unique()
        tribo_lote = tribo_lote[0] if len(tribo_lote) else "Indefinido"
        ret_lote = RETIDO_DICT.get(tribo_lote, 1.0)
        df_acc_l = _pick_acessos_df(df_sub)
        df_trn_l = _pick_trans_df(df_sub)
        acc = pd.to_numeric(df_acc_l["VOL_KPI"], errors="coerce").sum()
        trn = pd.to_numeric(df_trn_l["VOL_KPI"], errors="coerce").sum()
        tx = trn / acc if acc > 0 else 1.75
        cr = CR_SEGMENTO.get(segmento, 0.5)
        estimado = (volume_trans_esperado / tx) * cr * ret_lote
        resultados.append({"Subcanal": sub, "Tribo": tribo_lote, "Transações / Acessos": round(tx,2),
                           "% Retido": round(ret_lote*100,2), "% CR": round(cr*100,2), "Volume de CR Evitado": round(estimado)})
    df_lote = pd.DataFrame(resultados)
    st.dataframe(df_lote, use_container_width=True)

    # 📉 Gráfico Pareto
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
    df_pareto["Acumulado %"] = 100 * df_pareto["Acumulado"] / df_pareto["Volume de CR Evitado"].sum()
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_pareto["Subcanal"], y=df_pareto["Volume de CR Evitado"],
                         name="Volume de CR Evitado", marker_color=df_pareto["Cor"]))
    fig.add_trace(go.Scatter(x=df_pareto["Subcanal"], y=df_pareto["Acumulado %"],
                             name="Acumulado %", mode="lines+markers", marker=dict(color="royalblue"), yaxis="y2"))
    fig.update_layout(title="📈 Pareto - Volume de CR Evitado",
                      xaxis=dict(title="Subcanais"),
                      yaxis=dict(title="Volume de CR Evitado"),
                      yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0,100]),
                      legend=dict(x=0.75, y=1.15, orientation="h"), bargap=0.2)
    st.plotly_chart(fig, use_container_width=True)

    # 📊 Tabela executiva Top 80%
    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top80[["Subcanal","Tribo","Volume de CR Evitado","Acumulado %"]], use_container_width=True)

    # 🧠 Insight automático
    total_ev = df_lote["Volume de CR Evitado"].sum()
    top80_names = ", ".join(df_top80["Subcanal"].tolist())
    st.info(f"🧠 **Insight Automático**\n\n"
            f"- O volume total estimado de **CR evitado** é **{f'{total_ev:,.0f}'.replace(',', '.')}**.\n\n"
            f"- Apenas **{len(df_top80)} subcanais** concentram **80%** do potencial de ganho.\n\n"
            f"- Subcanais prioritários: **{top80_names}**.\n\n"
            f"👉 Recomenda-se priorizar estes subcanais para maximizar o impacto.")

    # 📥 Download Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_lote.to_excel(writer, sheet_name="Resultados", index=False)
        df_top80.to_excel(writer, sheet_name="Top_80_Pareto", index=False)
    st.download_button("📥 Baixar Excel Completo", buffer.getvalue(), "simulacao_cr.xlsx", "application/vnd.ms-excel")

