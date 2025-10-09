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

# ====================== AUTENTICAÇÃO COM SENHA ======================
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

# ====================== UTIL / LOGO NO TÍTULO ======================
def _find_asset_bytes(name_candidates):
    exts = [".png", ".jpg", ".jpeg", ".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    search_dirs = [
        script_dir, script_dir/"assets", script_dir/"static",
        Path.cwd().resolve(), Path.cwd().resolve()/ "assets", Path.cwd().resolve()/ "static",
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
        <h1 style='text-align:center;color:#8B0000;font-size:56px;margin:6px 0 10px'>
          <img src='data:image/png;base64,{img_b64}' style='height:70px;vertical-align:middle;margin-right:12px'>
          Calculadora de Ganhos
        </h1>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        "<h1 style='text-align:center;color:#8B0000;font-size:52px'>🖩 Calculadora de Ganhos</h1>",
        unsafe_allow_html=True,
    )

# ====================== PARAMETROS FIXOS ======================
# Retido por tribo. Para "Dma", usar CR do segmento (regra abaixo).
RETIDO_DICT = {
    "App": 0.916893598,
    "Bot": 0.883475537,
    "Web": 0.902710768,
}

# CR por segmento
CR_SEGMENTO = {
    "Móvel": 0.4947,        # 49,47%
    "Residencial": 0.4989,  # 49,89%
}

# Fallback para TX_UU_CPF quando não houver dados para calcular Transações/Usuários únicos
DEFAULT_TX_UU_CPF = 12.28

# ====================== CARREGAR DADOS ======================
URL_PERFORMANCE_RAW = (
    "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"
)

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL_PERFORMANCE_RAW, sheet_name="Tabela Performance")
    # Normalizações
    if "ANOMES" in df.columns:
        df["ANOMES"] = pd.to_datetime(df["ANOMES"].astype(str), format="%Y%m", errors="coerce")
    for c in ["VOL_KPI", "CR_DIR"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # manter só "Real"
    if "TP_META" in df.columns:
        df = df[df["TP_META"].astype(str).str.strip().str.lower() == "real"].copy()
    # Colunas padrão esperadas
    for c in ["SEGMENTO", "NM_SUBCANAL", "NM_TORRE", "NM_KPI"]:
        if c not in df.columns:
            st.error(f"Coluna ausente na base: {c}")
            st.stop()
    return df

df = carregar_dados()

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
col_f1, col_f2 = st.columns(2)

segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = col_f1.selectbox("📊 Segmento", segmentos)

subcanais_disp = sorted(
    df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"]
    .dropna().unique().tolist()
)
subcanal = col_f2.selectbox("📌 Subcanal", subcanais_disp)

df_sub = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == subcanal)]
tribos = df_sub["NM_TORRE"].dropna().unique().tolist()
tribo = tribos[0] if tribos else "Indefinido"

# métricas de contexto
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tribo", tribo)
c2.metric("Canal", tribo)
c3.metric("Segmento", segmento)
c4.metric("Subcanal", subcanal)

# ====================== PREMISSAS (expander) ======================
with st.expander("⚙️ Premissas utilizadas (fixas)", expanded=False):
    st.write(
        f"""
- **CR por segmento**: Móvel = {CR_SEGMENTO['Móvel']*100:.2f}%, Residencial = {CR_SEGMENTO['Residencial']*100:.2f}%  
- **% Retido 72h**: App = {RETIDO_DICT['App']*100:.2f}%, Bot = {RETIDO_DICT['Bot']*100:.2f}%, Web = {RETIDO_DICT['Web']*100:.2f}%  
- **TX UU / CPF (dinâmica)** = **Transações ÷ Usuários únicos** do subcanal/segmento; fallback **{DEFAULT_TX_UU_CPF:.2f}** se não houver dados.  
- **Regra Retido (Dma)**: quando **Tribo = Dma**, o **% Retido = CR do Segmento** (nunca 100%).
- **Transações/Acessos mínimo**: valores < **1,00** são forçados para **1,00**.
        """
    )

# ====================== INPUT ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros para Simulação")
col_in, _ = st.columns([2, 1])
volume_trans = col_in.number_input(
    "📥 Volume de Transações",
    min_value=0, value=10_000, step=1000
)

# ====================== CÁLCULO (subcanal selecionado) ======================
def fmt_int(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")

if st.button("🚀 Calcular Ganhos Potenciais"):
    df_final = df_sub.copy()
    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    # CR do segmento
    cr_segmento = CR_SEGMENTO.get(segmento, 0.50)

    # Acessos e Transações (histórico) para obter Transações/Acessos
    df_acc = df_final[df_final["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
    df_trn = df_final[df_final["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
    vol_acc = df_acc["VOL_KPI"].sum()
    vol_trn = df_trn["VOL_KPI"].sum()
    tx_trn_acc = (vol_trn / vol_acc) if vol_acc > 0 else 1.0
    if tx_trn_acc < 1.0:
        tx_trn_acc = 1.0  # força mínimo de 1,00

    # === NOVO: Usuários únicos (para TX_UU_CPF dinâmica)
    df_uu = df_final[df_final["NM_KPI"].str.contains("4.1 - Usuários", case=False, na=False)]
    vol_uu = df_uu["VOL_KPI"].sum()

    if vol_trn > 0 and vol_uu > 0:
        tx_uu_cpf = vol_trn / vol_uu   # Transações / Usuários únicos
    else:
        tx_uu_cpf = DEFAULT_TX_UU_CPF  # fallback

    # Regra do % Retido (Dma = usa CR do segmento)
    retido_base = RETIDO_DICT.get(tribo, cr_segmento)
    if str(tribo).strip().lower() == "dma":
        retido_base = cr_segmento

    # Volume de acessos e MAU (CPF)
    volume_acessos = volume_trans / tx_trn_acc
    mau_cpf = volume_trans / (tx_uu_cpf if tx_uu_cpf > 0 else DEFAULT_TX_UU_CPF)

    # CR evitado
    cr_evitado = volume_acessos * cr_segmento * retido_base
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)  # evita arredondar p/ cima por flutuante

    # =================== RESULTADOS (cards) ===================
    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Transações / Acessos", f"{tx_trn_acc:.2f}")
    m2.metric("% CR do Segmento", f"{cr_segmento*100:.2f}%")
    m3.metric("% Retido (regra)", f"{retido_base*100:.2f}%")
    m4.metric("MAU (CPF)", fmt_int(np.floor(mau_cpf + 1e-9)))

    # KPI premium – gradiente
    valor_destacado = fmt_int(cr_evitado_floor)
    st.markdown(
        f"""
        <div style="
            max-width:450px;margin:18px;padding:18px 22px;
            background:linear-gradient(90deg,#b31313 0%, #d01f1f 55%, #e23a3a 100%);
            border-radius:18px; box-shadow:0 8px 18px rgba(139,0,0,.25); color:#fff">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="font-weight:700;font-size:20px;letter-spacing:.3px">Volume de CR Evitado Estimado</div>
            <div style="font-weight:800;font-size:30px;background:#fff;color:#b31313;
                        padding:6px 16px;border-radius:12px; line-height:1">
              {valor_destacado}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Fórmulas: ① Volume de Acessos = Volume de Transações ÷ (Transações/Acessos). ② MAU (CPF) = Volume de Transações ÷ (Transações ÷ Usuários únicos). ③ CR Evitado = Volume de Acessos × CR × % Retido.")

    # =================== LOTE (todos os subcanais do SEGMENTO) ===================
    st.markdown("---")
    st.markdown("### 📄 Simulação para Todos os Subcanais")

    resultados = []
    for sub in subcanais_disp:
        df_sub_i = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == sub)]
        tribos_i = df_sub_i["NM_TORRE"].dropna().unique().tolist()
        tribo_i = tribos_i[0] if tribos_i else "Indefinido"

        df_a = df_sub_i[df_sub_i["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
        df_t = df_sub_i[df_sub_i["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
        df_u = df_sub_i[df_sub_i["NM_KPI"].str.contains("4.1 - Usuários", case=False, na=False)]

        va = df_a["VOL_KPI"].sum()
        vt = df_t["VOL_KPI"].sum()
        vu = df_u["VOL_KPI"].sum()

        tx = (vt / va) if va > 0 else 1.0
        if tx < 1.0:
            tx = 1.0

        # TX_UU_CPF dinâmica + fallback
        if vt > 0 and vu > 0:
            tx_uu_i = vt / vu
        else:
            tx_uu_i = DEFAULT_TX_UU_CPF

        cr_seg = CR_SEGMENTO.get(segmento, 0.50)
        ret_b = RETIDO_DICT.get(tribo_i, cr_seg)
        if str(tribo_i).strip().lower() == "dma":
            ret_b = cr_seg

        vol_acc_i = volume_trans / tx
        mau_i = volume_trans / (tx_uu_i if tx_uu_i > 0 else DEFAULT_TX_UU_CPF)
        estimado = np.floor((vol_acc_i * cr_seg * ret_b) + 1e-9)

        resultados.append({
            "Subcanal": sub,
            "Tribo": tribo_i,
            "Transações / Acessos": round(tx, 2),
            "↓ % Retido": round(ret_b * 100, 2),
            "% CR": round(cr_seg * 100, 2),
            "Volume de Acessos": int(vol_acc_i),
            "MAU (CPF)": int(np.floor(mau_i + 1e-9)),
            "Volume de CR Evitado": int(estimado),
        })

    df_lote = pd.DataFrame(resultados)
    st.dataframe(df_lote, use_container_width=False)

    # =================== PARETO ===================
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    if df_pareto["Volume de CR Evitado"].sum() > 0:
        df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
        df_pareto["Acumulado %"] = 100 * df_pareto["Acumulado"] / df_pareto["Volume de CR Evitado"].sum()
    else:
        df_pareto["Acumulado"] = 0
        df_pareto["Acumulado %"] = 0.0
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig_p = go.Figure()
    fig_p.add_trace(go.Bar(
        x=df_pareto["Subcanal"],
        y=df_pareto["Volume de CR Evitado"],
        name="Volume de CR Evitado",
        marker_color=df_pareto["Cor"]
    ))
    fig_p.add_trace(go.Scatter(
        x=df_pareto["Subcanal"],
        y=df_pareto["Acumulado %"],
        name="Acumulado %",
        mode="lines+markers",
        marker=dict(color="royalblue"),
        yaxis="y2"
    ))
    fig_p.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(x=0.72, y=1.18, orientation="h"),
        bargap=0.2,
        margin=dict(l=10, r=10, t=60, b=80)
    )
    st.plotly_chart(fig_p, use_container_width=False)

    # =================== TOP 80% & INSIGHT ===================
    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top80[["Subcanal", "Tribo", "Volume de CR Evitado", "Acumulado %"]],
                 use_container_width=False)

    total_ev = int(df_lote["Volume de CR Evitado"].sum())
    top80_names = ", ".join(df_top80["Subcanal"].tolist())
    total_ev_fmt = fmt_int(total_ev)
    st.markdown(
        f"""
**🧠 Insight Automático**

# == Volume total estimado de **CR evitado**: **{total_ev_fmt}**.  
- **{len(df_top80)} subcanais** concentram **80%** do potencial: **{top80_names}**.  
- **Ação**: priorize esses subcanais para maximizar impacto.
        """
    )

    # =================== DOWNLOAD EXCEL ===================
    buffer = io.BytesIO()
    engine = "xlsxwriter"
    try:
        import xlsxwriter  # noqa: F401
    except Exception:
        engine = "openpyxl"

    with pd.ExcelWriter(buffer, engine=engine) as writer:
        df_lote.to_excel(writer, sheet_name="Resultados", index=False)
        df_top80.to_excel(writer, sheet_name="Top_80_Pareto", index=False)

    st.download_button(
        label="📥 Baixar Excel Completo",
        data=buffer.getvalue(),
        file_name="simulacao_cr.xlsx",
        mime="application/vnd.ms-excel"
    )
