import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np
import base64
from pathlib import Path
import io
import plotly.express as px
import plotly.graph_objects as go

# ====================== CONFIG INICIAL ======================
st.set_page_config(
    page_title="🖩 Calculadora de Ganhos",
    page_icon="📶",
    layout="wide"
)

# ====================== AUTENTICAÇÃO COM SENHA ======================
def check_password():
    def password_entered():
        if st.session_state.get("password") == "claro@123":
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

# ====================== UTIL (logo no título) ======================
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    search_dirs = [script_dir, script_dir/"assets", script_dir/"static",
                   Path.cwd(), Path.cwd()/"assets", Path.cwd()/"static"]
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

def format_br(x, dec=0):
    if pd.isna(x):
        return "-"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

# ====================== TÍTULO COM LOGO ======================
logo_bytes = load_logo_for_title()
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(
        f"""
        <h1 style='text-align:center;color:#8B0000;font-size:70px;'>
            Calculadora de Ganhos
            <img src='data:image/png;base64,{img_b64}' style='height:100px;vertical-align:middle;margin-left:10px'>
        </h1>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        "<h1 style='text-align:center;color:#8B0000;font-size:60px;'>🖩 Calculadora de Ganhos</h1>",
        unsafe_allow_html=True
    )

# ========== CARGA DE DADOS ==========
@st.cache_data
def carregar_dados():
    url_base = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"
    df = pd.read_excel(url_base, sheet_name="Tabela Performance")
    df["ANOMES"] = pd.to_datetime(df["ANOMES"].astype(str), format="%Y%m", errors="coerce")
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce")
    df["CR_DIR"] = pd.to_numeric(df["CR_DIR"], errors="coerce")
    return df

df = carregar_dados()

# ========== TAXAS FIXAS ==========
retido_dict = {"App": 0.916893598, "Bot": 0.883475537, "Web": 0.902710768}

# ========== FILTROS ========== #
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)

mes_atual_str = pd.to_datetime(datetime.today()).strftime("%Y-%m")
meses = sorted(df["ANOMES"].dt.strftime("%Y-%m").dropna().unique())
idx_mes = meses.index(mes_atual_str) if mes_atual_str in meses else 0
anomes = col1.selectbox("🗓️ Mês", meses, index=idx_mes)

segmentos = sorted(df["SEGMENTO"].dropna().unique())
segmento = col2.selectbox("📶 Segmento", segmentos)

anomes_dt = pd.to_datetime(anomes)
tp_meta = "Real"

df_segmento = df[(df["ANOMES"] == anomes_dt) & (df["TP_META"] == tp_meta) & (df["SEGMENTO"] == segmento)]

subcanais_disponiveis = sorted(df_segmento["NM_SUBCANAL"].dropna().unique())
subcanal = st.selectbox("📌 Subcanal", subcanais_disponiveis)

df_subcanal = df_segmento[df_segmento["NM_SUBCANAL"] == subcanal]
tribo_detectada = df_subcanal["NM_TORRE"].dropna().unique()
tribo = tribo_detectada[0] if len(tribo_detectada) > 0 else "Indefinido"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Tribo", tribo)
col2.metric("Canal", tribo)
col3.metric("Segmento", segmento)
col4.metric("Subcanal", subcanal)

retido_pct = retido_dict.get(tribo, 1.0)

# ========== PARÂMETROS DE SIMULAÇÃO ==========
st.markdown("---")
st.markdown("### ➗ Parâmetros para Simulação")
col1, _ = st.columns([2, 1])
volume_esperado = col1.number_input("📥 Volume de Transações Esperado", min_value=0, value=10000)

# ====================== BOTÃO / CÁLCULO ======================
if st.button("🚀 Calcular Transações Evitadas"):
    df_final = df_subcanal[df_subcanal["SEGMENTO"] == segmento]
    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    cr_segmento = 0.494699284 if segmento == "Móvel" else 0.498877199 if segmento == "Residencial" else df_final["CR_DIR"].mean()
    df_acessos = df_final[df_final["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
    df_transacoes = df_final[df_final["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
    vol_acessos = df_acessos["VOL_KPI"].sum()
    vol_transacoes = df_transacoes["VOL_KPI"].sum()
    tx_trans_acessos = vol_transacoes / vol_acessos if vol_acessos > 0 else 1.75
    tx_trans_acessos = tx_trans_acessos if tx_trans_acessos > 0 else 1.75

    transacoes_esperadas = (volume_esperado / tx_trans_acessos) * cr_segmento * retido_pct

    # ===== Resultados imediatos =====
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    c1, c2, c3 = st.columns(3)
    c1.metric("Transações / Acessos", f"{tx_trans_acessos:.2f}")
    c2.metric("CR Segmento (%)", f"{cr_segmento*100:.2f}")
    c3.metric(f"% Retido ({tribo})", f"{retido_pct*100:.2f}")

    st.success(f"✅ Transações Evitadas: **{format_br(transacoes_esperadas,0)}**")
    st.caption("Fórmula: Volume Esperado ÷ (Transações / Acessos) × CR Segmento × % Retido")

    # ===== Simulação por TODOS os subcanais =====
    st.markdown("---")
    st.markdown("### 📄 Simulação para Todos os Subcanais")
    resultados_lote = []
    for sub in subcanais_disponiveis:
        df_sub = df_segmento[df_segmento["NM_SUBCANAL"] == sub]
        tribo_lote_arr = df_sub["NM_TORRE"].dropna().unique()
        tribo_lote = tribo_lote_arr[0] if len(tribo_lote_arr) > 0 else "Indefinido"
        ret_lote = retido_dict.get(tribo_lote, 1.0)

        df_acessos_lote = df_sub[df_sub["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
        df_trans_lote = df_sub[df_sub["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
        acessos = df_acessos_lote["VOL_KPI"].sum()
        transacoes = df_trans_lote["VOL_KPI"].sum()
        tx = transacoes / acessos if acessos > 0 else 1.75
        tx = tx if tx > 0 else 1.75
        cr = 0.494699284 if segmento == "Móvel" else 0.498877199 if segmento == "Residencial" else df_sub["CR_DIR"].mean()
        estimado = (volume_esperado / tx) * cr * ret_lote

        resultados_lote.append({
            "Subcanal": sub,
            "Tribo": tribo_lote,
            "Transações / Acessos": round(tx, 2),
            "% Retido": round(ret_lote*100, 2),
            "% CR": round(cr*100, 2),
            "Transações Evitadas": round(estimado)
        })

    df_lote = pd.DataFrame(resultados_lote).sort_values("Transações Evitadas", ascending=False).reset_index(drop=True)

    # ===== KPIs executivos =====
    st.markdown("### ⭐ KPIs Executivos (Cenário - Todos Subcanais)")
    k1, k2, k3 = st.columns(3)
    total_trans_esp = df_lote["Transações Evitadas"].sum()
    media_retido = df_lote["% Retido"].mean()
    top1 = df_lote.iloc[0] if not df_lote.empty else None
    k1.metric("Total Transações Evitadas", format_br(total_trans_esp, 0))
    k2.metric("Retido Médio (%)", f"{media_retido:.2f}")
    if top1 is not None:
        k3.metric("Líder (Subcanal)", f"{top1['Subcanal']} ({format_br(top1['Transações Evitadas'],0)})")
    else:
        k3.metric("Líder (Subcanal)", "-")

    st.dataframe(df_lote, use_container_width=True)

    # ===== Download CSV =====
    csv = df_lote.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Baixar Simulação Completa (CSV)", csv, "simulacao_transacoes.csv", "text/csv")

    # ===== Exportação Excel (2 abas) =====
    with io.BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df_lote.to_excel(writer, index=False, sheet_name="Resultados")
            # Pareto será gerado abaixo e exportado como tabela também (Top80)
            # (preenchemos depois de criar df_pareto_top)
        excel_bytes_initial = buffer.getvalue()  # placeholder

    # ===== Gráfico de barras =====
    fig = px.bar(
        df_lote.sort_values("Transações Evitadas", ascending=False),
        x="Subcanal", y="Transações Evitadas",
        title="📊 Transações Evitadas por Subcanal",
        color="Tribo",
        text_auto=True
    )
    st.plotly_chart(fig, use_container_width=True)

    # ===== Pareto =====
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.copy()
    df_pareto["Acumulado"] = df_pareto["Transações Evitadas"].cumsum()
    total = df_pareto["Transações Evitadas"].sum()
    df_pareto["Acumulado %"] = 100 * df_pareto["Acumulado"] / total if total > 0 else 0
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(
        x=df_pareto["Subcanal"],
        y=df_pareto["Transações Evitadas"],
        name="Transações Evitadas",
        marker_color=df_pareto["Cor"]
    ))
    fig_pareto.add_trace(go.Scatter(
        x=df_pareto["Subcanal"],
        y=df_pareto["Acumulado %"],
        name="Acumulado %",
        mode="lines+markers",
        marker=dict(color="royalblue"),
        yaxis="y2"
    ))
    fig_pareto.update_layout(
        title="Pareto das Transações Evitadas",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Transações Evitadas"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(x=0.75, y=1.15, orientation="h"),
        bargap=0.2
    )
    st.plotly_chart(fig_pareto, use_container_width=True)

    # ===== Top 80% – Tabela executiva =====
    df_pareto_top = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    # Garante incluir o próximo que ultrapassa 80% (fronteira)
    if not df_pareto_top.empty and len(df_pareto_top) < len(df_pareto):
        prox_idx = len(df_pareto_top)
        df_pareto_top = df_pareto.iloc[:prox_idx+1].copy()

    if not df_pareto_top.empty:
        # Junta colunas de contexto
        df_top_merge = df_pareto_top[["Subcanal","Transações Evitadas","Acumulado %"]].merge(
            df_lote[["Subcanal","Tribo"]], on="Subcanal", how="left")
        df_top_merge["% do Total"] = (df_top_merge["Transações Evitadas"]/total*100).round(2) if total>0 else 0
        df_top_merge = df_top_merge[["Subcanal","Tribo","Transações Evitadas","% do Total","Acumulado %"]]

        st.markdown("#### 🥇 Subcanais Prioritários (até ~80% do ganho)")
        st.dataframe(df_top_merge, use_container_width=True)

        # ===== Insight automático =====
        qtd_top = len(df_top_merge)
        lider = df_top_merge.iloc[0]["Subcanal"]
        lider_val = df_top_merge.iloc[0]["Transações Evitadas"]
        pareto_final = df_top_merge["Acumulado %"].iloc[-1]
        st.info(
            f"💡 **Insight**: Os **{qtd_top}** principais subcanais "
            f"concentram **{pareto_final:.1f}%** do potencial de ganho. "
            f"O líder é **{lider}** com **{format_br(lider_val,0)}** transações evitadas."
        )

        # ===== Regerar Excel com abas =====
        with io.BytesIO() as buffer:
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                df_lote.to_excel(writer, index=False, sheet_name="Resultados")
                df_top_merge.to_excel(writer, index=False, sheet_name="Top_80_Pareto")
            excel_bytes = buffer.getvalue()
        st.download_button(
            "📊 Baixar Excel Executivo (Resultados + Top 80%)",
            data=excel_bytes,
            file_name="simulacao_executivo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Nenhum subcanal atingiu 80% acumulado — distribuição bastante uniforme.")
