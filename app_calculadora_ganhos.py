# app_calculadora_ganhos.py
import io
import base64
from pathlib import Path
from datetime import datetime

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

# ====================== AUTENTICAÇÃO COM SENHA ======================
def check_password():
    def password_entered():
        st.session_state["authenticated"] = (
            st.session_state.get("password", "") == "claro@123"
        )
        if not st.session_state["authenticated"]:
            st.error("Senha incorreta. Tente novamente.")

    if not st.session_state.get("authenticated", False):
        st.text_input("🔐 Insira a senha para acessar:", type="password",
                      on_change=password_entered, key="password")
        st.stop()

check_password()

# ====================== ASSETS (LOGO NO TÍTULO) ======================
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
        Path.cwd(),
        Path.cwd() / "assets",
        Path.cwd() / "static",
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

logo_bytes = load_logo_for_title()
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(
        f"""
        <h1 style='text-align:center; color:#8B0000; font-size:58px;'>
            <img src='data:image/png;base64,{img_b64}'
                 style='height:72px; vertical-align:middle; margin-right:14px'>
            Calculadora de Ganhos
        </h1>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        "<h1 style='text-align:center; color:#8B0000;'>🖩 Calculadora de Ganhos</h1>",
        unsafe_allow_html=True,
    )

# ====================== CARREGAR DADOS ======================
URL_GITHUB = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

DEFAULTS = {
    "CR": {"Móvel": 0.4947, "Residencial": 0.4989},
    "RETIDO": {"App": 0.9169, "Bot": 0.8835, "Web": 0.9027},
    "TX_UU_CPF": 12.28,
    "TX_FALLBACK": 1.75,
}

def _normalize_percent(x):
    """Aceita '49,47%', '49.47%', 0.4947, 49.47 etc e devolve fração (0-1)"""
    if pd.isna(x):
        return np.nan
    if isinstance(x, str):
        x = x.replace("%", "").replace(".", "").replace(",", ".")
    try:
        val = float(x)
        if val > 1:
            val = val / 100.0
        return val
    except Exception:
        return np.nan

def _try_get_sheet(xls, like_list, default=None):
    names = [n for n in xls.sheet_names]
    for like in like_list:
        for n in names:
            if like.lower() in n.lower():
                return n
    return default

def _extract_apoio_params(df_apoio_raw: pd.DataFrame) -> dict:
    """
    Varre a aba 'Base de Apoio' (estrutura livre) e tenta extrair:
      - CR por segmento (Móvel, Residencial)
      - Retido Digital por tribo (App, Bot, Web)
      - TX_UU_CPF (se houver)
    Retorna dict com fallback para DEFAULTS quando necessário.
    """
    params = {
        "CR": DEFAULTS["CR"].copy(),
        "RETIDO": DEFAULTS["RETIDO"].copy(),
        "TX_UU_CPF": DEFAULTS["TX_UU_CPF"],
    }

    df_txt = df_apoio_raw.astype(str).applymap(lambda s: s.strip())

    # --- CR por segmento ---
    for seg_key in ["Móvel", "Movel", "M\u00f3vel", "Residencial"]:
        mask = df_txt.apply(lambda col: col.str.fullmatch(seg_key, case=False)).any(axis=1)
        idxs = list(np.where(mask)[0])
        for idx in idxs:
            row_vals = df_txt.iloc[idx].tolist()
            # pega primeiro numérico da linha
            for cell in row_vals[1:]:
                frac = _normalize_percent(cell)
                if not np.isnan(frac):
                    if "mov" in seg_key.lower():
                        params["CR"]["Móvel"] = frac
                    else:
                        params["CR"]["Residencial"] = frac
                    break

    # --- Retido por tribo ---
    for tribo in ["App", "Bot", "Web"]:
        mask = df_txt.apply(lambda col: col.str.fullmatch(tribo, case=False)).any(axis=1)
        idxs = list(np.where(mask)[0])
        for idx in idxs:
            row_vals = df_txt.iloc[idx].tolist()
            for cell in row_vals[1:]:
                frac = _normalize_percent(cell)
                if not np.isnan(frac):
                    params["RETIDO"][tribo] = frac
                    break

    # --- TX_UU_CPF (número, não %). Procura label "TX UU CPF".
    where = np.where(df_txt.apply(lambda col: col.str.contains("TX UU CPF", case=False, na=False)).values)
    if len(where[0]) > 0:
        r, c = where[0][0], where[1][0]
        # tenta pegar uma célula numérica ao lado/esquerda/direita/mesma linha
        candidates = []
        # direita
        if c + 1 < df_txt.shape[1]:
            candidates.append(df_txt.iat[r, c + 1])
        # esquerda
        if c - 1 >= 0:
            candidates.append(df_txt.iat[r, c - 1])
        # mesma linha, próximos
        candidates += df_txt.iloc[r].tolist()

        for cell in candidates:
            s = str(cell).strip().replace(",", ".")
            try:
                val = float(s)
                if val > 0:
                    params["TX_UU_CPF"] = val
                    break
            except Exception:
                pass

    return params

@st.cache_data(show_spinner=False)
def carregar_dados(file_bytes: bytes | None = None):
    # abre ExcelFile de URL ou bytes
    if file_bytes:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
    else:
        xls = pd.ExcelFile(URL_GITHUB)

    # encontra abas por "apelido"
    perf_name = _try_get_sheet(xls, ["tabela performance", "performance", "tabela"], xls.sheet_names[0])
    apoio_name = _try_get_sheet(xls, ["base de apoio", "base apoio", "apoio"], None)

    # lê performance
    df_perf = pd.read_excel(xls, sheet_name=perf_name)
    # normalizações mínimas
    for col in ["ANOMES", "TP_META", "SEGMENTO", "NM_TORRE", "NM_SUBCANAL", "NM_KPI", "VOL_KPI"]:
        if col not in df_perf.columns:
            # não quebra se faltar ANOMES, CR_DIR etc.
            df_perf[col] = np.nan

    # filtros estáveis
    df_perf["TP_META"] = df_perf["TP_META"].astype(str).str.strip()
    df_perf = df_perf[df_perf["TP_META"].str.lower().eq("real") | df_perf["TP_META"].isna()]

    # tipos numéricos
    df_perf["VOL_KPI"] = pd.to_numeric(df_perf["VOL_KPI"], errors="coerce")
    if "CR_DIR" in df_perf.columns:
        df_perf["CR_DIR"] = pd.to_numeric(df_perf.get("CR_DIR"), errors="coerce")

    # lê apoio (se existir)
    apoio_params = DEFAULTS.copy()
    if apoio_name:
        df_apoio_raw = pd.read_excel(xls, sheet_name=apoio_name, header=None)
        apoio_params = DEFAULTS.copy()
        apoio_params.update(_extract_apoio_params(df_apoio_raw))

    return df_perf, apoio_params

# --- tentativas de carga: 1) GitHub; 2) Upload manual (fallback)
try:
    df, apoio_params = carregar_dados(None)
except Exception as e:
    st.error("❌ Não foi possível ler do GitHub. Envie o arquivo .xlsx manualmente.")
    uploaded = st.file_uploader("📂 Envie o Excel com as abas 'Tabela Performance' e 'Base de Apoio'", type=["xlsx"])
    if not uploaded:
        st.stop()
    df, apoio_params = carregar_dados(uploaded.getvalue())

# ====================== TAXAS (vêm do apoio com fallback) ======================
retido_dict = apoio_params["RETIDO"]
cr_por_segmento = apoio_params["CR"]

# ====================== FILTROS (SEM MÊS) ======================
st.markdown("### 🔎 Filtros de Cenário")

col1, col2 = st.columns(2)
segmento = col1.selectbox("📶 Segmento", sorted(x for x in df["SEGMENTO"].dropna().unique()))
# lista de subcanais daquele segmento
df_seg = df[df["SEGMENTO"] == segmento]
subcanais_disponiveis = sorted(df_seg["NM_SUBCANAL"].dropna().unique())
subcanal = col2.selectbox("📌 Subcanal", subcanais_disponiveis)

# tribo detectada
df_sub = df_seg[df_seg["NM_SUBCANAL"] == subcanal]
tribo_detectada = df_sub["NM_TORRE"].dropna().unique()
tribo = tribo_detectada[0] if len(tribo_detectada) else "Indefinido"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tribo", tribo)
c2.metric("Canal", tribo)
c3.metric("Segmento", segmento)
c4.metric("Subcanal", subcanal)

retido_pct = retido_dict.get(tribo, 1.0)

# ====================== PARÂMETROS ======================
st.markdown("---")
st.markdown("<h3 style='color:#555;'>🧮 Parâmetros de Simulação</h3>", unsafe_allow_html=True)
st.caption("Preencha os valores para simular o impacto das alavancas de autoatendimento.")
colp, _ = st.columns([2, 1])
volume_esperado = colp.number_input("📥 Insira o volume de transações", min_value=0, value=10000)

# ====================== CÁLCULO DO CENÁRIO SELECIONADO ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    df_final = df_sub.copy()

    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    # CR por segmento (da Base de Apoio ou fallback)
    cr_segmento = cr_por_segmento.get(segmento, np.nan)
    if pd.isna(cr_segmento):
        cr_segmento = df_final.get("CR_DIR", pd.Series(dtype=float)).mean(skipna=True)
        if pd.isna(cr_segmento):
            cr_segmento = DEFAULTS["CR"].get(segmento, 0.49)

    # Transações / Acessos (agregado sem mês)
    df_acc = df_final[df_final["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
    df_trn = df_final[df_final["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]

    vol_acessos = df_acc["VOL_KPI"].sum(skipna=True)
    vol_trans = df_trn["VOL_KPI"].sum(skipna=True)

    tx_trans_acessos = (vol_trans / vol_acessos) if vol_acessos > 0 else DEFAULTS["TX_FALLBACK"]
    if tx_trans_acessos <= 0 or np.isinf(tx_trans_acessos) or np.isnan(tx_trans_acessos):
        tx_trans_acessos = DEFAULTS["TX_FALLBACK"]

    # cálculo principal (volume de CR evitado estimado)
    cr_evitado = (volume_esperado / tx_trans_acessos) * cr_segmento * retido_pct

    # ===== RESULTADO DESTACADO =====
    valor_formatado = f"{cr_evitado:,.0f}".replace(",", ".")
    st.markdown(
        f"""
        <div style='background-color:#f8f9fa;
                    border:2px solid #8B0000;
                    border-radius:12px;
                    padding:22px;
                    margin-top:10px;
                    text-align:center;
                    color:#8B0000;
                    font-size:40px;
                    font-weight:700;
                    box-shadow:0 4px 10px rgba(0,0,0,0.07);'>
            ✅ Volume de CR Evitado Estimado<br>
            <span style='font-size:56px;'>{valor_formatado}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 📊 Resultados do cenário")
    m1, m2, m3 = st.columns(3)
    m1.metric("Transações / Acessos", f"{tx_trans_acessos:.2f}")
    m2.metric("CR Segmento (%)", f"{cr_segmento*100:.2f}")
    m3.metric(f"% Retido ({tribo})", f"{retido_pct*100:.2f}")

    # ====================== SIMULAÇÃO PARA TODOS OS SUBCANAIS ======================
    st.markdown("---")
    st.markdown("### 📄 Simulação para Todos os Subcanais (segmento atual)")
    resultados_lote = []

    for sub in subcanais_disponiveis:
        df_s = df_seg[df_seg["NM_SUBCANAL"] == sub]
        tribo_lote = df_s["NM_TORRE"].dropna().unique()
        tribo_lote = tribo_lote[0] if len(tribo_lote) else "Indefinido"
        ret_lote = retido_dict.get(tribo_lote, 1.0)

        acc = df_s[df_s["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]["VOL_KPI"].sum(skipna=True)
        trn = df_s[df_s["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]["VOL_KPI"].sum(skipna=True)
        tx = (trn / acc) if acc > 0 else DEFAULTS["TX_FALLBACK"]
        if tx <= 0 or np.isinf(tx) or np.isnan(tx):
            tx = DEFAULTS["TX_FALLBACK"]

        cr_seg = cr_por_segmento.get(segmento, np.nan)
        if pd.isna(cr_seg):
            cr_seg = df_s.get("CR_DIR", pd.Series(dtype=float)).mean(skipna=True)
            if pd.isna(cr_seg):
                cr_seg = DEFAULTS["CR"].get(segmento, 0.49)

        estimado = (volume_esperado / tx) * cr_seg * ret_lote

        resultados_lote.append({
            "Subcanal": sub,
            "Tribo": tribo_lote,
            "Transações / Acessos": round(tx, 2),
            "% Retido": round(ret_lote * 100, 2),
            "% CR": round(cr_seg * 100, 2),
            "Volume de CR Evitado": round(estimado),
        })

    df_lote = pd.DataFrame(resultados_lote)
    st.dataframe(df_lote, use_container_width=True)

    # ====================== PARETO ======================
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
    total_sum = max(df_pareto["Volume de CR Evitado"].sum(), 1)  # evita div/0
    df_pareto["Acumulado %"] = 100 * df_pareto["Acumulado"] / total_sum
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig_pareto = go.Figure()
    # Barras
    fig_pareto.add_trace(
        go.Bar(
            x=df_pareto["Subcanal"],
            y=df_pareto["Volume de CR Evitado"],
            name="Volume de CR Evitado",
            marker_color=df_pareto["Cor"],
            hovertemplate="<b>%{x}</b><br>CR evitado: %{y:,}<extra></extra>",
        )
    )
    # Linha acumulada
    fig_pareto.add_trace(
        go.Scatter(
            x=df_pareto["Subcanal"],
            y=df_pareto["Acumulado %"],
            name="Acumulado %",
            mode="lines+markers",
            marker=dict(color="royalblue"),
            yaxis="y2",
            hovertemplate="Acumulado: %{y:.1f}%<extra></extra>",
        )
    )

    fig_pareto.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais", tickangle=-25),
        yaxis=dict(title="CR Evitado", separatethousands=True),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100], ticksuffix="%"),
        bargap=0.2,
        legend=dict(orientation="h", y=-0.25, x=0),
        margin=dict(t=60, b=120),
    )
    st.plotly_chart(fig_pareto, use_container_width=True)

    # ====================== TABELA TOP 80% ======================
    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(
        df_top80[["Subcanal", "Tribo", "Volume de CR Evitado", "Acumulado %"]],
        use_container_width=True,
    )

    # ====================== INSIGHT AUTOMÁTICO ======================
    total_ev = df_lote["Volume de CR Evitado"].sum()
    total_ev_fmt = f"{total_ev:,.0f}".replace(",", ".")
    top80_names = ", ".join(df_top80["Subcanal"].tolist())

    st.markdown(
        f"""
        > 🧠 **Insight Automático**  
        > • O volume total estimado de **CR evitado** é **{total_ev_fmt}**.  
        > • Apenas **{len(df_top80)} subcanais** concentram **80%** do potencial de ganho.  
        > • Subcanais prioritários: **{top80_names}**.  
        > • Priorize esses subcanais para maximizar o impacto.
        """
    )

    # ====================== DOWNLOAD (EXCEL ou CSV) ======================
    try:
        import xlsxwriter  # noqa: F401
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df_lote.to_excel(writer, sheet_name="Resultados", index=False)
            df_top80.to_excel(writer, sheet_name="Top_80_Pareto", index=False)
        st.download_button(
            label="📥 Baixar Excel Completo",
            data=buffer.getvalue(),
            file_name="simulacao_cr.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception:
        csv_all = df_lote.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Baixar Resultados (CSV)",
            data=csv_all,
            file_name="simulacao_cr.csv",
            mime="text/csv",
        )
