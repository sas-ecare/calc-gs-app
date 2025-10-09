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

# ====================== FUNÇÃO PARA CARREGAR IMAGEM ======================
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

# ====================== CARREGAR LOGO NO TÍTULO ====================== 
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

# ====================== CARGA DE DADOS ======================
URL_GITHUB = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"
# Opcional: se quiser um arquivo separado apenas para apoio, defina a URL aqui:
URL_GITHUB_APOIO_ALT = None  # exemplo: "https://raw.githubusercontent.com/.../Base_Apoio.xlsx"

@st.cache_data(show_spinner=True)
def carregar_dados():
    # Lê tabela principal
    df = pd.read_excel(URL_GITHUB, sheet_name="Tabela Performance")
    # df['ANOMES'] = pd.to_datetime(df['ANOMES'].astype(str), format='%Y%m', errors='coerce')
    df['VOL_KPI'] = pd.to_numeric(df['VOL_KPI'], errors='coerce')
    df['CR_DIR']  = pd.to_numeric(df.get('CR_DIR', np.nan), errors='coerce')

    # Tenta ler a aba "BASE APOIO" no mesmo arquivo
    apoio_params = {"TX_UU_CPF": 12.28}  # fallback padrão
    try:
        xls = pd.ExcelFile(URL_GITHUB)
        possible_names = ["BASE APOIO", "BASE_APOIO", "BASE APOIO 23", "BASE_APOIO_23"]
        apoio_df = None
        for nm in possible_names:
            if nm in xls.sheet_names:
                apoio_df = pd.read_excel(xls, sheet_name=nm, header=None)
                break

        # Se não encontrou no mesmo arquivo, tenta arquivo alternativo
        if apoio_df is None and URL_GITHUB_APOIO_ALT:
            xls2 = pd.ExcelFile(URL_GITHUB_APOIO_ALT)
            for nm in possible_names:
                if nm in xls2.sheet_names:
                    apoio_df = pd.read_excel(xls2, sheet_name=nm, header=None)
                    break

        # Tenta extrair TX_UU_CPF (ex: célula tipo "L5" ou linha com texto correspondente)
        if apoio_df is not None:
            # 1) Procura por uma célula com o texto da label e pega o número vizinho
            label_candidates = ["TX UU CPF", "TX_UU_CPF", "TX UU/CPF", "TX UU CPF (MAU)"]
            tx_found = None
            for i in range(apoio_df.shape[0]):
                for j in range(apoio_df.shape[1]):
                    val = apoio_df.iat[i, j]
                    if isinstance(val, str) and any(lbl.lower() in val.lower() for lbl in label_candidates):
                        # tenta ler a célula à direita
                        if j + 1 < apoio_df.shape[1]:
                            maybe_num = pd.to_numeric(apoio_df.iat[i, j+1], errors="coerce")
                            if pd.notna(maybe_num):
                                tx_found = float(maybe_num)
                                break
                if tx_found is not None:
                    break
            # 2) Se não achou por rótulo, tenta procurar algum número plausível na planilha
            if tx_found is None:
                numeric_vals = pd.to_numeric(apoio_df.select_dtypes(exclude=[object]).stack(), errors="coerce")
                numeric_vals = numeric_vals[~numeric_vals.isna()]
                # se houver algum número com ordem de grandeza parecida (ex: entre 1 e 100)
                plausible = numeric_vals[(numeric_vals > 0.1) & (numeric_vals < 100)]
                if not plausible.empty:
                    tx_found = float(plausible.iloc[0])
            if tx_found is not None and tx_found > 0:
                apoio_params["TX_UU_CPF"] = tx_found
    except Exception:
        pass  # mantém fallback 12.28

    return df, apoio_params

df, apoio_params = carregar_dados()

# ======= TAXAS FIXAS =======
retido_dict = {
    'App': 0.916893598,
    'Bot': 0.883475537,
    'Web': 0.902710768
}

# ======= FILTROS =======
st.markdown("### 🔎 Filtros de Cenário")
col1, col2 = st.columns(2)

#mes_atual_str = pd.to_datetime(datetime.today()).strftime('%Y-%m')
#anomes_opcoes = sorted(df['ANOMES'].dt.strftime('%Y-%m').dropna().unique())
#anomes = col1.selectbox(
 #   "🗓️ Mês",
  #  anomes_opcoes,
   # index=anomes_opcoes.index(mes_atual_str) if mes_atual_str in anomes_opcoes else 0
#)

segmento = col2.selectbox("📶 Segmento", sorted(df['SEGMENTO'].dropna().unique()))

anomes_dt = pd.to_datetime(anomes)
tp_meta = "Real"

df_segmento = df[
 #   (df['ANOMES'] == anomes_dt) &
    (df['TP_META'] == tp_meta) &
    (df['SEGMENTO'] == segmento)
]

subcanais_disponiveis = sorted(df_segmento['NM_SUBCANAL'].dropna().unique())
subcanal = st.selectbox("📌 Subcanal", subcanais_disponiveis)

df_subcanal = df_segmento[df_segmento['NM_SUBCANAL'] == subcanal]
tribo_detectada = df_subcanal['NM_TORRE'].dropna().unique()
tribo = tribo_detectada[0] if len(tribo_detectada) > 0 else "Indefinido"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tribo", tribo)
c2.metric("Canal", tribo)
c3.metric("Segmento", segmento)
c4.metric("Subcanal", subcanal)

retido_pct = retido_dict.get(tribo, 1.0)

# ======= PARÂMETROS =======
st.markdown("---")
st.markdown("### ➗ Parâmetros para Simulação")
colp1, _ = st.columns([2, 1])
volume_esperado = colp1.number_input("📥 Insira o volume de transações", min_value=0, value=10000)

# ======= CÁLCULO =======
if st.button("🚀 Calcular Ganhos Potenciais"):
    df_final = df_subcanal[df_subcanal['SEGMENTO'] == segmento]

    if df_final.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    # CR Segmento
    cr_segmento = 0.494699284 if segmento == "Móvel" else 0.498877199 if segmento == "Residencial" else df_final['CR_DIR'].mean()

    # Transações / Acessos
    df_acessos = df_final[df_final['NM_KPI'].str.contains("6 - Acessos", case=False, na=False)]
    df_transacoes = df_final[df_final['NM_KPI'].str.contains("7.1 - Transações", case=False, na=False)]
    vol_acessos = df_acessos['VOL_KPI'].sum()
    vol_trans = df_transacoes['VOL_KPI'].sum()
    tx_trans_acessos = vol_trans / vol_acessos if vol_acessos > 0 else 1.75
    tx_trans_acessos = tx_trans_acessos if tx_trans_acessos > 0 else 1.75

    # ======= NOVOS CÁLCULOS =======
    # Volume de Acessos = Y3 / Y17
    volume_acessos = volume_esperado / tx_trans_acessos if tx_trans_acessos > 0 else 0.0

    # MAU CPF = Volume de Acessos / TX_UU_CPF  (se TX_UU_CPF vazio => 12,28)
    tx_uu_cpf = apoio_params.get("TX_UU_CPF", 12.28)
    if not isinstance(tx_uu_cpf, (int, float)) or tx_uu_cpf <= 0:
        tx_uu_cpf = 12.28
    mau_cpf = volume_acessos / tx_uu_cpf if tx_uu_cpf > 0 else 0.0

    # Volume de CR Evitado (sua métrica principal)
    cr_evitado = (volume_esperado / tx_trans_acessos) * cr_segmento * retido_pct

    st.markdown("---")
    st.markdown("### 📊 Resultados da Simulação")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Transações / Acessos", f"{tx_trans_acessos:.2f}")
    r2.metric("CR Segmento (%)", f"{cr_segmento*100:.2f}")
    r3.metric(f"% Retido ({tribo})", f"{retido_pct*100:.2f}")
    # novos KPIs auxiliares
    r4.metric("TX UU CPF (Base Apoio)", f"{tx_uu_cpf:.2f}")

    # Destaque principal
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

    # KPIs auxiliares abaixo
    a1, a2 = st.columns(2)
    a1.metric("📊 Volume de Acessos (Y3/Y17)", f"{volume_acessos:,.0f}".replace(",", "."))
    a2.metric("👤 MAU (CPF) (Acessos/TX_UU_CPF)", f"{mau_cpf:,.0f}".replace(",", "."))

    st.caption("Fórmula CR Evitado: Volume Acessos ÷ (Transações / Acessos) × CR Segmento × % Retido")

    # ======= LOTE: TODOS OS SUBCANAIS =======
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

        # também calcula Acessos e MAU por subcanal (usando o mesmo TX_UU_CPF)
        vol_acessos_sc = volume_esperado / tx if tx > 0 else 0
        mau_sc = vol_acessos_sc / tx_uu_cpf if tx_uu_cpf > 0 else 0

        # MAU CPF = SE(Y17="";"";Y13/SE('Base de Apoio'!L5=0;12,28;'Base de Apoio'!L5))
        if tx_trans_acessos == 0:
            mau_cpf = 0
        else:
            tx_uu_cpf = apoio_params.get("TX_UU_CPF", 12.28)
            try:
                tx_uu_cpf = float(tx_uu_cpf)
            except Exception:
                tx_uu_cpf = 12.28
            if tx_uu_cpf == 0:
                tx_uu_cpf = 12.28
            mau_cpf = volume_acessos / tx_uu_cpf




        resultados_lote.append({
            "Subcanal": sub,
            "Tribo": tribo_lote,
            "Transações / Acessos": round(tx, 2),
            "% Retido": round(ret_lote*100, 2),
            "% CR": round(cr*100, 2),
            "Volume de Acessos": round(vol_acessos_sc),
            "MAU (CPF)": round(mau_sc),
            "Volume de CR Evitado": round(estimado)
        })

    df_lote = pd.DataFrame(resultados_lote)
    st.dataframe(df_lote, use_container_width=True)

    # ======= PARETO =======
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    if df_pareto["Volume de CR Evitado"].sum() > 0:
        df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
        df_pareto["Acumulado %"] = 100 * df_pareto["Acumulado"] / df_pareto["Volume de CR Evitado"].sum()
    else:
        df_pareto["Acumulado"] = 0
        df_pareto["Acumulado %"] = 0

    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(
        x=df_pareto["Subcanal"],
        y=df_pareto["Volume de CR Evitado"],
        name="Volume de CR Evitado",
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
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(x=0.75, y=1.15, orientation="h"),
        bargap=0.2
    )
    st.plotly_chart(fig_pareto, use_container_width=True)

    # ======= TOP 80% =======
    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top80[["Subcanal", "Tribo", "Volume de Acessos", "MAU (CPF)", "Volume de CR Evitado", "Acumulado %"]],
                 use_container_width=True)

    # ======= INSIGHT =======
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

    # ======= DOWNLOAD EXCEL (2 abas) =======
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


