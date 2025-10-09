import streamlit as st
import pandas as pd
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

# ====================== AUTENTICAÇÃO ======================
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

# ====================== LOGO ======================
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    for d in [script_dir, script_dir / "assets", script_dir / "static", Path.cwd() / "assets"]:
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
        <h1 style='text-align: center; color: #8B0000; font-size: 60px;'>
            <img src='data:image/png;base64,{img_b64}' style='height:80px; vertical-align:middle; margin-right:15px'>
            Calculadora de Ganhos
        </h1>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown("<h1 style='text-align: center; color: #8B0000;'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

# ====================== BASE ======================
@st.cache_data
def carregar_dados():
    url_base = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"
    df = pd.read_excel(url_base, sheet_name="Tabela Performance")
    df['VOL_KPI'] = pd.to_numeric(df['VOL_KPI'], errors='coerce')
    return df

df = carregar_dados()

# ====================== TAXAS FIXAS ======================
retido_dict = {
    'App': 0.9169,
    'Bot': 0.8835,
    'Web': 0.9027
}

cr_dict = {
    'Móvel': 0.4947,
    'Residencial': 0.4989
}

tx_trans_dict = {
    'Padrão': 1.75
}

tx_uu_cpf_dict = {
    'Padrão': 7.02  # conforme planilha
}

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)
segmento = col1.selectbox("📶 Segmento", sorted(df['SEGMENTO'].dropna().unique()))
subcanais_disponiveis = sorted(df[df['SEGMENTO'] == segmento]['NM_SUBCANAL'].dropna().unique())
subcanal = col2.selectbox("📌 Subcanal", subcanais_disponiveis)

df_subcanal = df[(df['SEGMENTO'] == segmento) & (df['NM_SUBCANAL'] == subcanal)]
tribo_detectada = df_subcanal['NM_TORRE'].dropna().unique()
tribo = tribo_detectada[0] if len(tribo_detectada) > 0 else "Indefinido"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tribo", tribo)
c2.metric("Canal", tribo)
c3.metric("Segmento", segmento)
c4.metric("Subcanal", subcanal)

# ====================== PARÂMETROS ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros para Simulação")
colp1, _ = st.columns([2, 1])
volume_esperado = colp1.number_input("📥 Insira o volume de transações", min_value=0, value=10000)

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):

    retido_pct = retido_dict.get(tribo, 1.0)
    cr_segmento = cr_dict.get(segmento, 0.49)
    tx_trans_acessos = tx_trans_dict.get('Padrão', 1.75)
    tx_uu_cpf = tx_uu_cpf_dict.get('Padrão', 7.02)

    # Volume de acessos
    volume_acessos = volume_esperado / tx_trans_acessos if tx_trans_acessos > 0 else 0

    # MAU (CPF) = SE(Y17="";"";Y13/SE(L5=0;12,28;L5))
    if tx_trans_acessos == 0:
        mau_cpf = 0
    else:
        if tx_uu_cpf in [0, None, np.nan]:
            tx_uu_cpf = 12.28
        mau_cpf = volume_acessos / tx_uu_cpf

    # CR evitado
    cr_evitado = (volume_esperado / tx_trans_acessos) * cr_segmento * retido_pct

    # ====================== RESULTADOS ======================
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Transações / Acessos", f"{tx_trans_acessos:.2f}")
    r2.metric("CR Segmento (%)", f"{cr_segmento*100:.2f}")
    r3.metric(f"% Retido ({tribo})", f"{retido_pct*100:.2f}")
    r4.metric("TX UU CPF", f"{tx_uu_cpf:.2f}")

    valor_formatado = f"{cr_evitado:,.0f}".replace(",", ".")
    st.markdown(
        f"""
        <div style="
            background-color:#fff7e6;
            border:1px solid #ffd591;
            padding:20px;
            border-radius:12px;
            text-align:center;
            margin-top:10px;
            margin-bottom:15px;">
            <div style="font-size:18px; color:#8B0000; font-weight:600; margin-bottom:6px;">
                ✅ Volume de CR Evitado Estimado
            </div>
            <div style="font-size:42px; color:#262626; font-weight:800;">
                {valor_formatado}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # KPIs auxiliares
    a1, a2 = st.columns(2)
    a1.metric("📊 Volume de Acessos", f"{volume_acessos:,.0f}".replace(",", "."))
    a2.metric("👤 MAU (CPF)", f"{mau_cpf:,.0f}".replace(",", "."))

    # ====================== PARETO ======================
    st.markdown("---")
    st.markdown("### 📄 Simulação para Todos os Subcanais")
    resultados_lote = []
    for sub in subcanais_disponiveis:
        df_sub = df[(df['SEGMENTO'] == segmento) & (df['NM_SUBCANAL'] == sub)]
        tribo_lote = df_sub['NM_TORRE'].dropna().unique()
        tribo_lote = tribo_lote[0] if len(tribo_lote) > 0 else "Indefinido"
        ret_lote = retido_dict.get(tribo_lote, 1.0)
        cr = cr_dict.get(segmento, 0.49)
        estimado = (volume_esperado / tx_trans_acessos) * cr * ret_lote
        vol_acessos_sc = volume_esperado / tx_trans_acessos if tx_trans_acessos > 0 else 0
        mau_sc = vol_acessos_sc / tx_uu_cpf

        resultados_lote.append({
            "Subcanal": sub,
            "Tribo": tribo_lote,
            "Transações / Acessos": round(tx_trans_acessos, 2),
            "% Retido": round(ret_lote*100, 2),
            "% CR": round(cr*100, 2),
            "Volume de Acessos": round(vol_acessos_sc),
            "MAU (CPF)": round(mau_sc),
            "Volume de CR Evitado": round(estimado)
        })

    df_lote = pd.DataFrame(resultados_lote)
    st.dataframe(df_lote, use_container_width=True)

    # ====================== PARETO ======================
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
    df_pareto["Acumulado %"] = 100 * df_pareto["Acumulado"] / df_pareto["Volume de CR Evitado"].sum()
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_pareto["Subcanal"],
        y=df_pareto["Volume de CR Evitado"],
        name="Volume de CR Evitado",
        marker_color=df_pareto["Cor"]
    ))
    fig.add_trace(go.Scatter(
        x=df_pareto["Subcanal"],
        y=df_pareto["Acumulado %"],
        name="Acumulado %",
        mode="lines+markers",
        marker=dict(color="royalblue"),
        yaxis="y2"
    ))
    fig.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(x=0.75, y=1.15, orientation="h"),
        bargap=0.2
    )
    st.plotly_chart(fig, use_container_width=True)

    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top80[["Subcanal", "Tribo", "Volume de Acessos", "MAU (CPF)", "Volume de CR Evitado", "Acumulado %"]],
                 use_container_width=True)

    # ====================== INSIGHT ======================
    total_ev = df_lote["Volume de CR Evitado"].sum()
    top80_names = ", ".join(df_top80["Subcanal"].tolist())
    total_ev_fmt = f"{total_ev:,.0f}".replace(",", ".")
    insight_text = (
        f"🧠 **Insight Automático**\n\n"
        f"- O volume total estimado de **CR evitado** é **{total_ev_fmt}**.\n\n"
        f"- Apenas **{len(df_top80)} subcanais** concentram **80%** do potencial de ganho.\n\n"
        f"- Subcanais prioritários: **{top80_names}**.\n\n"
        f"👉 Recomenda-se priorizar estes subcanais para maximizar o impacto."
    )
    st.markdown(insight_text)

    # ====================== DOWNLOAD ======================
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
