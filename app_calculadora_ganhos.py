import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import base64
from pathlib import Path
import plotly.graph_objects as go
import io
import math

# ============= CONFIG =============
st.set_page_config(page_title="🖩 Calculadora de Ganhos", page_icon="📶", layout="wide")

# ------------- senha --------------
def check_password():
    def _ok():
        st.session_state["auth"] = (st.session_state.get("password") == "claro@123")
        if not st.session_state["auth"]:
            st.error("Senha incorreta. Tente novamente.")
    if "auth" not in st.session_state:
        st.session_state["auth"] = False
    if not st.session_state["auth"]:
        st.text_input("🔐 Insira a senha para acessar:", type="password", on_change=_ok, key="password")
        st.stop()
check_password()

# ======== util: logo no título ========
def _find_asset_bytes(cands):
    exts = [".png",".jpg",".jpeg",".webp"]
    try:
        script_dir = Path(__file__).parent.resolve()
    except NameError:
        script_dir = Path.cwd().resolve()
    search = [script_dir, script_dir/"assets", script_dir/"static", Path.cwd(), Path.cwd()/ "assets", Path.cwd()/ "static"]
    for d in search:
        for b in cands:
            for e in exts:
                p = d / f"{b}{e}"
                if p.exists():
                    try: return p.read_bytes()
                    except: pass
    return None

def _logo_title():
    b = _find_asset_bytes(["claro_logo","logo_claro","claro"])
    if b:
        b64 = base64.b64encode(b).decode()
        st.markdown(
            f"""
            <h1 style='text-align:center;color:#8B0000;font-size:60px;'>
              <img src='data:image/png;base64,{b64}' style='height:80px;vertical-align:middle;margin-right:15px'>
              Calculadora de Ganhos
            </h1>
            """, unsafe_allow_html=True)
    else:
        st.markdown("<h1 style='text-align:center;color:#8B0000;font-size:50px;'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

_logo_title()

# ============= Carga da base ============
RAW_URL = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

@st.cache_data
def carregar_dados():
    df = pd.read_excel(RAW_URL, sheet_name="Tabela Performance")
    # limpeza
    if "ANOMES" in df.columns:
        df["ANOMES"] = pd.to_datetime(df["ANOMES"].astype(str), format="%Y%m", errors="coerce")
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce")
    if "CR_DIR" in df.columns:
        df["CR_DIR"] = pd.to_numeric(df["CR_DIR"], errors="coerce")
    return df

try:
    df = carregar_dados()
except Exception as e:
    st.error("❌ Não consegui carregar a planilha do GitHub. Verifique a URL do arquivo.")
    st.stop()

# ============= Taxas fixas no código ============
# % Retido por tribo
RETIDO_DICT = {
    "App": 0.916893598,
    "Bot": 0.883475537,
    "Web": 0.902710768,
}
RETIDO_FALLBACK = float(np.mean(list(RETIDO_DICT.values())))  # fallback seguro (~0.9017)

# CR por segmento
CR_SEGMENTO = {
    "Móvel": 0.494699284,
    "Residencial": 0.498877199,
}

# TX UU por CPF (se não houver valor dinâmico informado, usar esse)
TX_UU_CPF_PADRAO = 12.28  # exemplo usado por você

# ============= Helpers =============
def normalizar_tribo(nome_tribo: str) -> str:
    """
    Normaliza NM_TORRE para uma das chaves do RETIDO_DICT.
    Evita % Retido cair para 100% por default.
    """
    if not isinstance(nome_tribo, str):
        return "Web"  # escolha conservadora
    s = nome_tribo.strip().lower()
    if "app" in s or "appbot" in s or "dma" in s or "dial" in s:  # mapeia Dma/Dial para App
        return "App"
    if "bot" in s or "whatsapp" in s:
        return "Bot"
    if "web" in s or "site" in s:
        return "Web"
    # fallback
    return "Web"

def format_int_ptbr(v: float) -> str:
    return f"{int(v):,}".replace(",", ".")

# ============= Filtros (sem mês) =============
st.markdown("### 🔎 Filtros de Cenário")
colS1, colS2 = st.columns(2)

segmento = colS2.selectbox("📶 Segmento", sorted(df["SEGMENTO"].dropna().unique()))
# filtra uma vez: só Real + segmento
df_seg = df[(df["TP_META"].str.lower() == "real") & (df["SEGMENTO"] == segmento)]

subcanais_disp = sorted(df_seg["NM_SUBCANAL"].dropna().unique())
subcanal = st.selectbox("📌 Subcanal", subcanais_disp)

# tribo do subcanal
tribos = df_seg[df_seg["NM_SUBCANAL"] == subcanal]["NM_TORRE"].dropna().unique()
tribo_raw = tribos[0] if len(tribos) else "Indefinido"
tribo_norm = normalizar_tribo(tribo_raw)
retido_pct = RETIDO_DICT.get(tribo_norm, RETIDO_FALLBACK)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tribo", tribo_raw if isinstance(tribo_raw,str) else str(tribo_raw))
c2.metric("Canal", tribo_norm)
c3.metric("Segmento", segmento)
c4.metric("Subcanal", subcanal)

# ============= Parâmetros =============
st.markdown("---")
st.markdown("### ➗ Parâmetros para Simulação")

left, right = st.columns([2,1])
vol_transacoes = left.number_input("📥 Volume de Transações (input do cenário)", min_value=0, value=10000)
# opcionalmente permitir TX_UU_CPF manual
tx_uu_cpf = right.number_input("TX UU/CPF (deixe 0 para usar padrão)", min_value=0.0, value=0.0, step=0.01)
if tx_uu_cpf <= 0:
    tx_uu_cpf = TX_UU_CPF_PADRAO

# ============= Calcular ============
if st.button("🚀 Calcular Ganhos Potenciais"):
    # subset do subcanal
    df_sub = df_seg[df_seg["NM_SUBCANAL"] == subcanal]
    if df_sub.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    # Transações/Acessos a partir do histórico
    df_acc = df_sub[df_sub["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
    df_trn = df_sub[df_sub["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
    vol_acc_hist = df_acc["VOL_KPI"].sum()
    vol_trn_hist = df_trn["VOL_KPI"].sum()

    tx_trx_acesso = (vol_trn_hist / vol_acc_hist) if vol_acc_hist > 0 else 1.75
    # regra: se <1 vira 1 (100%)
    tx_trx_acesso = max(tx_trx_acesso, 1.0)

    # CR do segmento (fixo no código)
    cr_segmento = CR_SEGMENTO.get(segmento, float(df_sub["CR_DIR"].mean()) if "CR_DIR" in df_sub else 0.50)

    # Volume de Acessos e MAU
    vol_acessos = vol_transacoes / tx_trx_acesso if tx_trx_acesso > 0 else 0
    mau_cpf = (vol_acessos / tx_uu_cpf) if tx_uu_cpf > 0 else 0

    # Volume de CR Evitado (principal KPI)
    cr_evitado = (vol_transacoes / tx_trx_acesso) * cr_segmento * retido_pct if tx_trx_acesso > 0 else 0

    # ======= KPI Card premium (gradiente) =======
    cr_fmt = format_int_ptbr(math.floor(cr_evitado))  # truncar
    st.markdown(
        f"""
        <div style="
            border-radius:18px;
            padding:24px 28px;
            margin: 8px 0 18px 0;
            background: linear-gradient(135deg, #b30000 0%, #e63939 60%, #ff8585 100%);
            color: white; box-shadow: 0 8px 24px rgba(179,0,0,.25);
        ">
          <div style="font-size:14px; opacity:.95; letter-spacing:.5px;">Volume de CR Evitado Estimado</div>
          <div style="font-size:48px; font-weight:800; line-height:1.1; margin-top:6px;">{cr_fmt}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ======= Métricas auxiliares =======
    m1,m2,m3 = st.columns(3)
    m1.metric("Transações / Acessos", f"{tx_trx_acesso:.2f}")
    m2.metric("% CR do Segmento", f"{cr_segmento*100:.2f}%")
    m3.metric(f"% Retido ({tribo_norm})", f"{retido_pct*100:.2f}%")

    # ======= Premissas utilizadas (side box) =======
    st.markdown(
        """
        <div style="border:1px solid #eee;border-radius:12px;padding:16px 18px;margin-top:6px;background:#fafafa;">
          <div style="font-weight:700;margin-bottom:8px;">🧩 Premissas utilizadas</div>
          <ul style="margin:0 0 0 18px; padding:0;">
            <li><b>CR por Segmento</b>: Móvel = 49,47%, Residencial = 49,89%</li>
            <li><b>% Retido por tribo</b>: App = 91,69% · Bot = 88,35% · Web = 90,27% (Dma/Dial ⇒ App)</li>
            <li><b>Regra</b>: se Transações/Acessos &lt; 1 ⇒ usa 1,00</li>
            <li><b>TX UU/CPF</b>: {tx_uu_cpf:.2f} (padrão 12,28 quando não informado)</li>
          </ul>
        </div>
        """, unsafe_allow_html=True
    )

    # ============= Lote (todos subcanais) =============
    resultados = []
    for sub in subcanais_disp:
        df_s = df_seg[df_seg["NM_SUBCANAL"] == sub]
        tribo_s_raw = df_s["NM_TORRE"].dropna().unique()
        tribo_s = normalizar_tribo(tribo_s_raw[0]) if len(tribo_s_raw) else "Web"
        ret_s = RETIDO_DICT.get(tribo_s, RETIDO_FALLBACK)

        dfa = df_s[df_s["NM_KPI"].str.contains("6 - Acessos", case=False, na=False)]
        dft = df_s[df_s["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
        acc = dfa["VOL_KPI"].sum()
        trn = dft["VOL_KPI"].sum()
        tx = (trn / acc) if acc > 0 else 1.75
        tx = max(tx, 1.0)

        cr = CR_SEGMENTO.get(segmento, float(df_s["CR_DIR"].mean()) if "CR_DIR" in df_s else 0.50)
        vol_acc = vol_transacoes / tx if tx > 0 else 0
        mau = vol_acc / tx_uu_cpf if tx_uu_cpf > 0 else 0
        estimado = (vol_transacoes / tx) * cr * ret_s if tx > 0 else 0

        resultados.append({
            "Subcanal": sub,
            "Tribo": tribo_s,
            "Transações / Acessos": round(tx, 2),
            "↓ % Retido": round(ret_s*100, 2),
            "% CR": round(cr*100, 2),
            "Volume de Acessos": math.floor(vol_acc),
            "MAU (CPF)": math.floor(mau),
            "Volume de CR Evitado": math.floor(estimado)  # truncar para evitar arredondar p/ cima (ex.: 2497)
        })

    df_lote = pd.DataFrame(resultados).sort_values("Volume de CR Evitado", ascending=False)
    st.markdown("### 📄 Simulação para Todos os Subcanais")
    st.dataframe(df_lote, use_container_width=True)

    # ============= Pareto =============
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_pareto = df_lote.copy().reset_index(drop=True)
    df_pareto["Acumulado"] = df_pareto["Volume de CR Evitado"].cumsum()
    total_v = df_pareto["Volume de CR Evitado"].sum()
    df_pareto["Acumulado %"] = (100 * df_pareto["Acumulado"] / total_v) if total_v > 0 else 0
    df_pareto["Cor"] = np.where(df_pareto["Acumulado %"] <= 80, "crimson", "lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_pareto["Subcanal"], y=df_pareto["Volume de CR Evitado"],
        name="Volume de CR Evitado", marker_color=df_pareto["Cor"]
    ))
    fig.add_trace(go.Scatter(
        x=df_pareto["Subcanal"], y=df_pareto["Acumulado %"],
        name="Acumulado %", mode="lines+markers",
        marker=dict(color="royalblue"), yaxis="y2"
    ))
    fig.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0,100]),
        legend=dict(x=0.72, y=1.16, orientation="h"),
        bargap=0.2
    )
    st.plotly_chart(fig, use_container_width=True)

    # Top 80%
    df_top80 = df_pareto[df_pareto["Acumulado %"] <= 80].copy()
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top80[["Subcanal","Tribo","Volume de CR Evitado","Acumulado %"]], use_container_width=True)

    # Insight
    total_ev = df_lote["Volume de CR Evitado"].sum()
    total_ev_fmt = format_int_ptbr(total_ev)
    top80_names = ", ".join(df_top80["Subcanal"].tolist())
    st.info(
        "🧠 **Insight Automático**\n\n"
        f"- O volume total estimado de **CR evitado** é **{total_ev_fmt}**.\n\n"
        f"- Apenas **{len(df_top80)} subcanais** concentram **80%** do potencial de ganho.\n\n"
        f"- Subcanais prioritários: **{top80_names}**.\n\n"
        "👉 Recomenda-se priorizar estes subcanais para maximizar o impacto."
    )

    # Excel p/ download
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as w:
        df_lote.to_excel(w, sheet_name="Resultados", index=False)
        df_top80.to_excel(w, sheet_name="Top_80_Pareto", index=False)
    st.download_button(
        "📥 Baixar Excel Completo",
        data=buffer.getvalue(),
        file_name="simulacao_cr.xlsx",
        mime="application/vnd.ms-excel"
    )
