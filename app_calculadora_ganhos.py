import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np
import base64
from pathlib import Path
import plotly.express as px

# ====================== CONFIG INICIAL ======================
st.set_page_config(
    page_title="🖩 Calculadora de Ganhos",
    page_icon="📶",
    layout="wide"
)

# ====================== AUTENTICAÇÃO COM SENHA ======================
def check_password():
    def password_entered():
        if st.session_state["password"] == "claro@123":
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False
            st.error("Senha incorreta. Tente novamente.")
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.text_input("🔐 Insira a senha para acessar:", type="password",
                      on_change=password_entered, key="password")
        st.stop()

check_password()

# ====================== FUNÇÃO PARA CARREGAR IMAGEM ======================
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    search_dirs = [
        script_dir, script_dir / "assets", script_dir / "static",
        Path.cwd().resolve(), Path.cwd().resolve() / "assets", Path.cwd().resolve() / "static",
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

# ====================== CARREGAR LOGO NO TÍTULO ======================
logo_bytes = load_logo_for_title()
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(
        f"""
        <h1 style='text-align: center; color: #8B0000; font-size: 60px;'>
            <img src='data:image/png;base64,{img_b64}' style='height:80px; vertical-align:middle; margin-right:10px'>
            Calculadora de Ganhos - Volume de CR Evitado
        </h1>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        "<h1 style='text-align: center; color: #8B0000;'>🖩 Calculadora de Ganhos - Volume de CR Evitado</h1>",
        unsafe_allow_html=True
    )

# ========== FUNÇÃO DE CARGA ==========
@st.cache_data
def carregar_dados():
    url_base = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"
    df = pd.read_excel(url_base, sheet_name="Tabela Performance")
    df['ANOMES'] = pd.to_datetime(df['ANOMES'].astype(str), format='%Y%m', errors='coerce')
    df['VOL_KPI'] = pd.to_numeric(df['VOL_KPI'], errors='coerce')
    df['CR_DIR'] = pd.to_numeric(df['CR_DIR'], errors='coerce')
    return df

df = carregar_dados()

# ========== TAXAS FIXAS ==========
retido_dict = {'App': 0.916893598, 'Bot': 0.883475537, 'Web': 0.902710768}

# ========== FILTROS ==========
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)
mes_atual_str = pd.to_datetime(datetime.today()).strftime('%Y-%m')
anomes = col1.selectbox("🗓️ Mês",
                        sorted(df['ANOMES'].dt.strftime('%Y-%m').dropna().unique()),
                        index=sorted(df['ANOMES'].dt.strftime('%Y-%m').dropna().unique()).index(mes_atual_str)
                        if mes_atual_str in df['ANOMES'].dt.strftime('%Y-%m').dropna().unique() else 0)
segmento = col2.selectbox("📶 Segmento", sorted(df['SEGMENTO'].dropna().unique()))
anomes_dt = pd.to_datetime(anomes)
tp_meta = "Real"
df_segmento = df[(df['ANOMES'] == anomes_dt) & (df['TP_META'] == tp_meta) & (df['SEGMENTO'] == segmento)]

subcanais_disponiveis = sorted(df_segmento['NM_SUBCANAL'].dropna().unique())
subcanal = st.selectbox("📌 Subcanal", subcanais_disponiveis)

df_subcanal = df_segmento[df_segmento['NM_SUBCANAL'] == subcanal]
tribo_detectada = df_subcanal['NM_TORRE'].dropna().unique()
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
volume_esperado = col1.number_input("📥 Volume de Acessos com Potencial de Redução de CR",
                                    min_value=0, value=10000)

# ========== CÁLCULO ==========
if st.button("🚀 Calcular Volume de CR Evitado"):
    df_final = df_subcanal[df_subcanal['SEGMENTO'] == segmento]
    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    cr_segmento = 0.494699284 if segmento == "Móvel" else 0.498877199 if segmento == "Residencial" else df_final['CR_DIR'].mean()
    df_acessos = df_final[df_final['NM_KPI'].str.contains("6 - Acessos", case=False, na=False)]
    df_transacoes = df_final[df_final['NM_KPI'].str.contains("7.1 - Transações", case=False, na=False)]
    vol_acessos = df_acessos['VOL_KPI'].sum()
    vol_transacoes = df_transacoes['VOL_KPI'].sum()
    tx_trans_acessos = vol_transacoes / vol_acessos if vol_acessos > 0 else 1.75
    tx_trans_acessos = tx_trans_acessos if tx_trans_acessos > 0 else 1.75

    volume_cr_evitado = (volume_esperado / tx_trans_acessos) * cr_segmento * retido_pct
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    col1, col2, col3 = st.columns(3)
    col1.metric("Transações / Acessos", f"{tx_trans_acessos:.2f}")
    col2.metric("CR Segmento (%)", f"{cr_segmento*100:.2f}")
    col3.metric(f"% Retido ({tribo})", f"{retido_pct*100:.2f}")
    valor_formatado = f"{volume_cr_evitado:,.0f}".replace(",", ".")
    st.success(f"✅ Volume de CR Evitado: **{valor_formatado}**")

    # ================= DASHBOARD POR SUBCANAIS =================
    st.markdown("---")
    st.markdown("### 📄 Simulação para Todos os Subcanais")
    resultados_lote = []
    for sub in subcanais_disponiveis:
        df_sub = df_segmento[df_segmento['NM_SUBCANAL'] == sub]
        tribo_lote = df_sub['NM_TORRE'].dropna().unique()
        tribo_lote = tribo_lote[0] if len(tribo_lote) > 0 else "Indefinido"
        ret_lote = retido_dict.get(tribo_lote, 1.0)
        df_acessos_lote = df_sub[df_sub['NM_KPI'].str.contains("6 - Acessos", case=False, na=False)]
        df_trans_lote = df_sub[df_sub['NM_KPI'].str.contains("7.1 - Transações", case=False, na=False)]
        acessos = df_acessos_lote['VOL_KPI'].sum()
        transacoes = df_trans_lote['VOL_KPI'].sum()
        tx = transacoes / acessos if acessos > 0 else 1.75
        tx = tx if tx > 0 else 1.75
        cr = 0.494699284 if segmento == "Móvel" else 0.498877199 if segmento == "Residencial" else df_sub['CR_DIR'].mean()
        estimado = (volume_esperado / tx) * cr * ret_lote
        resultados_lote.append({
            "Subcanal": sub,
            "Tribo": tribo_lote,
            "Transações / Acessos": round(tx, 2),
            "% Retido": round(ret_lote*100, 2),
            "% CR": round(cr*100, 2),
            "Volume de CR Evitado": round(estimado)
        })
    df_lote = pd.DataFrame(resultados_lote)
    st.dataframe(df_lote, use_container_width=True)

    # ================= PARETO AJUSTADO =================
    df_lote_sorted = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    df_lote_sorted["% Acumulado"] = df_lote_sorted["Volume de CR Evitado"].cumsum() / df_lote_sorted["Volume de CR Evitado"].sum() * 100
    df_lote_sorted["Pareto"] = np.where(df_lote_sorted["% Acumulado"] <= 80, "Top 80%", "Outros")

    fig_pareto = px.bar(
        df_lote_sorted,
        x="Subcanal",
        y="Volume de CR Evitado",
        color="Pareto",
        color_discrete_map={"Top 80%": "red", "Outros": "lightgray"},
        title="📈 Pareto - Volume de CR Evitado",
        text="Volume de CR Evitado"
    )

    # Linha do % acumulado com labels
    fig_pareto.add_scatter(
        x=df_lote_sorted["Subcanal"],
        y=df_lote_sorted["% Acumulado"],
        mode="lines+markers+text",
        name="% Acumulado",
        yaxis="y2",
        line=dict(color="blue"),
        marker=dict(size=6),
        text=[f"{v:.1f}%" for v in df_lote_sorted["% Acumulado"]],
        textposition="top center"
    )

    fig_pareto.update_layout(
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(overlaying="y", side="right", range=[0, 110], title="% Acumulado"),
        legend=dict(title="Legenda", orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5)
    )

    st.plotly_chart(fig_pareto, use_container_width=True)
