import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np
import base64
from pathlib import Path
import plotly.graph_objects as go
import io

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

# ====================== CARGA DOS DADOS (GitHub OU Upload) ======================
URL_GITHUB = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Calculadora%20de%20Ganho%202.xlsx"

st.caption("Fonte dos dados: GitHub (automático) ou upload manual do mesmo layout.")

uploaded = st.file_uploader("📂 (Opcional) Envie o Excel com as abas 'Tabela Performance' e 'BASE APOIO'", type=["xlsx"])

@st.cache_data(show_spinner=False)
def carregar_dados(_uploaded_file_bytes: bytes | None):
    """
    Lê:
      - Tabela Performance (volumes)
      - BASE APOIO (parâmetros)
    Da URL do GitHub por padrão; se o usuário fizer upload, prioriza o upload.
    """
    if _uploaded_file_bytes:
        xls = pd.ExcelFile(io.BytesIO(_uploaded_file_bytes))
    else:
        # GitHub
        xls = pd.ExcelFile(URL_GITHUB)

    # TABELA PERFORMANCE (base principal)
    df_perf = pd.read_excel(xls, sheet_name="Tabela Performance")
    # Normalizações
    if "ANOMES" in df_perf.columns:
        df_perf["ANOMES"] = pd.to_datetime(df_perf["ANOMES"].astype(str), format="%Y%m", errors="coerce")
    for col in ["VOL_KPI", "CR_DIR"]:
        if col in df_perf.columns:
            df_perf[col] = pd.to_numeric(df_perf[col], errors="coerce")

    # BASE APOIO (parâmetros)
    df_apoio_raw = pd.read_excel(xls, sheet_name="BASE APOIO", header=None)
    # Vamos tentar extrair CR, Retido e TX UU CPF de forma robusta
    apoio = {
        "CR": {"Móvel": None, "Residencial": None},
        "RETIDO": {"App": None, "Bot": None, "Web": None},
        "TX_UU_CPF": None
    }

    # Varre as células procurando pelos rótulos
    table = df_apoio_raw.fillna("")
    for r in range(table.shape[0]):
        row_vals = [str(x).strip() for x in table.iloc[r].tolist()]

        # CR Móvel / Residencial em linha
        if any(v.lower() == "cr" for v in row_vals):
            # tentar ler linhas abaixo
            for rr in range(r+1, min(r+10, table.shape[0])):
                a = str(table.iloc[rr, 0]).strip().lower()
                val = str(table.iloc[rr, 1]).strip() if table.shape[1] > 1 else ""
                try:
                    num = float(str(val).replace("%","").replace(",","."))
                    if "mó" in a or "mov" in a:
                        apoio["CR"]["Móvel"] = num/100 if num > 1 else num
                    if "res" in a:
                        apoio["CR"]["Residencial"] = num/100 if num > 1 else num
                except:
                    pass

        # Retido Digital
        if any("retido" in v.lower() for v in row_vals):
            # ler 3 próximas linhas: App, Bot, Web
            for rr in range(r+1, min(r+10, table.shape[0])):
                canal = str(table.iloc[rr, 0]).strip()
                val = str(table.iloc[rr, 1]).strip() if table.shape[1] > 1 else ""
                if canal.lower() in ["app","bot","web"]:
                    try:
                        num = float(val.replace("%","").replace(",","."))
                        apoio["RETIDO"][canal.capitalize()] = num/100 if num > 1 else num
                    except:
                        pass

        # TX UU CPF (pelo rótulo na coluna ao lado)
        # Procuramos por "TX UU CPF" em qualquer célula da linha
        if any("tx uu cpf" in v.lower() for v in row_vals):
            # buscar número nesta linha
            for c in range(table.shape[1]):
                try:
                    num = float(str(table.iloc[r, c]).replace("%","").replace(",","."))
                    if 0 < num <= 100:
                        apoio["TX_UU_CPF"] = num/100 if num > 1 else num
                except:
                    pass

    # Fallbacks (caso não encontre na base de apoio)
    if apoio["CR"]["Móvel"] is None:
        apoio["CR"]["Móvel"] = 0.4947  # ~49,47%
    if apoio["CR"]["Residencial"] is None:
        apoio["CR"]["Residencial"] = 0.4989  # ~49,89%

    if apoio["RETIDO"]["App"] is None:
        apoio["RETIDO"]["App"] = 0.9169
    if apoio["RETIDO"]["Bot"] is None:
        apoio["RETIDO"]["Bot"] = 0.8835
    if apoio["RETIDO"]["Web"] is None:
        apoio["RETIDO"]["Web"] = 0.9027

    if apoio["TX_UU_CPF"] is None:
        apoio["TX_UU_CPF"] = 0.1228  # 12,28%

    return df_perf, apoio

file_bytes = uploaded.getvalue() if uploaded else None
df, apoio_params = carregar_dados(file_bytes)

# ====================== TAXAS (da BASE APOIO) ======================
CR_SEGMENTO = apoio_params["CR"]             # {"Móvel":float, "Residencial":float}
RETIDO_DICT = apoio_params["RETIDO"]         # {"App":float, "Bot":float, "Web":float}
TX_UU_CPF = apoio_params["TX_UU_CPF"]        # float (e.g., 0.1228)

# ====================== FILTROS (sem ANOMES) ======================
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)

segmentos_disp = sorted(df["SEGMENTO"].dropna().astype(str).unique())
segmento = col2.selectbox("📶 Segmento", segmentos_disp)

# filtra por segmento e REAL (sem mês)
df_seg = df[(df["SEGMENTO"] == segmento) & (df["TP_META"].astype(str).str.lower() == "real")]

subcanais_disp = sorted(df_seg["NM_SUBCANAL"].dropna().astype(str).unique())
subcanal = st.selectbox("📌 Subcanal", subcanais_disp)

# tribo detectada pelo subcanal
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
# de acordo com o layout-base, aqui o usuário informa VOLUME DE TRANSAÇÕES
volume_trans_esperado = colx.number_input("📥 Insira o volume de **Transações**", min_value=0, value=10000)

# ====================== CÁLCULOS (TX, CR, etc.) ======================
def _pick_acessos_df(_df):
    # algumas bases chamam "6 - Acessos", outras "4.1 - Usuários"
    return _df[_df["NM_KPI"].str.contains("Acesso|Usu.rio", case=False, na=False)]

def _pick_trans_df(_df):
    return _df[_df["NM_KPI"].str.contains("7.1 - Transa", case=False, na=False)]

if st.button("🚀 Calcular Ganhos Potenciais"):
    df_final = df_subcanal.copy()
    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    # CR do segmento (da BASE APOIO)
    cr_segmento = CR_SEGMENTO.get(segmento, np.nan)
    if pd.isna(cr_segmento):  # fallback se vier algo fora de padrão
        cr_segmento = df_final["CR_DIR"].mean()
        try:
            cr_segmento = float(cr_segmento)
            cr_segmento = cr_segmento if cr_segmento <= 1 else cr_segmento/100
        except:
            cr_segmento = 0.5

    # Transações/Acessos
    df_acessos = _pick_acessos_df(df_final)
    df_trans = _pick_trans_df(df_final)
    vol_acessos_hist = pd.to_numeric(df_acessos["VOL_KPI"], errors="coerce").sum()
    vol_trans_hist = pd.to_numeric(df_trans["VOL_KPI"], errors="coerce").sum()

    tx_trans_acessos = vol_trans_hist / vol_acessos_hist if vol_acessos_hist > 0 else np.nan
    if (pd.isna(tx_trans_acessos)) or (tx_trans_acessos <= 0):
        st.warning("⚠️ Não foi possível calcular a Taxa Transações/Acessos a partir do histórico — usando valor padrão 1,75.")
        tx_trans_acessos = 1.75

    # Acessos estimados a partir do input de transações
    acessos_estimados = volume_trans_esperado / tx_trans_acessos if tx_trans_acessos > 0 else 0

    # CR evitado (ligação direcionada humano evitada)
    cr_evitado = (volume_trans_esperado / tx_trans_acessos) * cr_segmento * retido_pct

    # MAU (CPF): se não houver base específica, usa TX_UU_CPF (da BASE APOIO) como fallback
    # Regra: MAU = acessos_estimados * TX_UU_CPF
    mau_cpf = acessos_estimados * TX_UU_CPF

    # ====================== RESULTADOS (painel) ======================
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    c1, c2, c3 = st.columns(3)
    c1.metric("Taxa Transações / Acessos", f"{tx_trans_acessos:.2f}")
    c2.metric("% CR Segmento (Humano)", f"{cr_segmento*100:.2f}%")
    c3.metric(f"% Retido 72h ({tribo})", f"{retido_pct*100:.2f}%")

    st.success(f"✅ Volume de **CR Evitado** Estimado: **{f'{cr_evitado:,.0f}'.replace(',', '.')}**")
    st.caption("Fórmula: Volume de Transações ÷ (Transações/Acessos) × CR Segmento × % Retido 72h")

    # Bloco extra (opcional) como no layout Excel
    c4, c5, c6 = st.columns(3)
    c4.metric("📉 Volume Ligações Evitadas (Humano)", f"{f'{cr_evitado:,.0f}'.replace(',', '.')}")
    c5.metric("📊 Volume de Acessos (estimado)", f"{f'{acessos_estimados:,.0f}'.replace(',', '.')}")
    c6.metric("👤 Volume de MAU (CPF) (estimado)", f"{f'{mau_cpf:,.0f}'.replace(',', '.')}")

    # ====================== SIMULAÇÃO PARA TODOS OS SUBCANAIS ======================
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
        tx = trn/acc if acc > 0 else np.nan
        if (pd.isna(tx)) or (tx <= 0):
            tx = 1.75

        cr_lote = CR_SEGMENTO.get(segmento, 0.5)  # da BASE APOIO
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

    # ====================== PARETO ======================
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho (CR Evitado)")
    df_pareto = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
    total_v = df_pareto["Volume de CR Evitado"].sum()
    df_pareto["Acumulado %"] = 100*df_pareto["Acumulado"]/total_v if total_v>0 else 0
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig_p = go.Figure()
    fig_p.add_trace(go.Bar(
        x=df_pareto["Subcanal"],
        y=df_pareto["Volume de CR Evitado"],
        name="Volume de CR Evitado",
        marker_color=df_pareto["Cor"],
        hovertemplate="<b>%{x}</b><br>CR Evitado: %{y:,.0f}<extra></extra>"
    ))
    fig_p.add_trace(go.Scatter(
        x=df_pareto["Subcanal"],
        y=df_pareto["Acumulado %"],
        name="Acumulado %",
        mode="lines+markers",
        marker=dict(color="royalblue"),
        yaxis="y2",
        hovertemplate="Acumulado: %{y:.1f}%<extra></extra>"
    ))

    fig_p.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais", tickangle=-15),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        bargap=0.2,
        margin=dict(l=20, r=20, t=60, b=20),
        hovermode="x unified"
    )
    st.plotly_chart(fig_p, use_container_width=True)

    # Top 80%
    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top80[["Subcanal","Tribo","Volume de CR Evitado","Acumulado %"]], use_container_width=True)

    # ====================== INSIGHT (com quebras e separador BR) ======================
    total_ev = df_lote["Volume de CR Evitado"].sum()
    total_ev_fmt = f"{total_ev:,.0f}".replace(",", ".")
    top80_names = ", ".join(df_top80["Subcanal"].tolist()) if not df_top80.empty else "—"

    insight_md = (
        "🧠 **Insight Automático**  \n"
        f"- O volume total estimado de **CR evitado** é **{total_ev_fmt}**.  \n"
        f"- **{len(df_top80)} subcanais** concentram **80%** do potencial de ganho.  \n"
        f"- **Priorize:** {top80_names}."
    )
    st.markdown(insight_md)

    # ====================== DOWNLOAD EXCEL (2 abas) ======================
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_lote.to_excel(writer, sheet_name="Resultados", index=False)
        df_top80.to_excel(writer, sheet_name="Top_80_Pareto", index=False)
    st.download_button(
        label="📥 Baixar Excel Completo",
        data=buffer.getvalue(),
        file_name="simulacao_cr.xlsx",
        mime="application/vnd.ms-excel"
    )
