# app_calculadora_ganhos.py — versão final (14/10/2025)


import io, base64, unicodedata, re
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ====================== CONFIG ======================
st.set_page_config(page_title="🖩 Calculadora de Ganhos", page_icon="📶", layout="wide")

# ====================== LOGIN ======================
def check_password():
    def password_entered():
        st.session_state["authenticated"] = (st.session_state.get("password") == "claro@123")
        if not st.session_state["authenticated"]:
            st.error("Senha incorreta. Tente novamente.")
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.text_input("🔐 Insira a senha:", type="password",
                      on_change=password_entered, key="password")
        st.stop()

check_password()

# ====================== LOGO ======================
def _find_asset_bytes(name_candidates):
    for d in [Path.cwd(), Path.cwd()/ "assets", Path.cwd()/ "static"]:
        for base in name_candidates:
            for ext in [".png",".jpg",".jpeg",".webp"]:
                p = d / f"{base}{ext}"
                if p.exists():
                    return p.read_bytes()
    return None

logo_bytes = _find_asset_bytes(["claro_logo","logo_claro","claro"])
if logo_bytes:
    img_b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(f"""
        <h1 style='text-align:center;color:#8B0000;font-size:54px;'>
        <img src='data:image/png;base64,{img_b64}' style='height:70px;vertical-align:middle;margin-right:10px'>
        Calculadora de Ganhos</h1>""", unsafe_allow_html=True)
else:
    st.markdown("<h1 style='text-align:center;color:#8B0000;'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

# ====================== PARÂMETROS FIXOS ======================
RETIDO_DICT = {"App":0.9169,"Bot":0.8835,"Web":0.9027}
CR_SEGMENTO = {"Móvel":0.4947,"Residencial":0.4989}
DEFAULT_TX_UU_CPF = 12.28

# ====================== NORMALIZAÇÃO ======================
def normalize_text(s):
    """Remove acentos, pontuação e prefixos numéricos."""
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"^[0-9.\-\s]+", "", s)       # remove prefixos tipo '7.1 -'
    s = re.sub(r"[^a-z0-9\s]", " ", s)       # remove pontuação
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# ====================== BASE ======================
URL = "https://raw.githubusercontent.com/gustavo3-freitas/calculadora-ganhos-claro/main/base/Tabela_Performance_v2.xlsx"

st.cache_data.clear()  # limpa cache sempre que roda

@st.cache_data(show_spinner=True)
def carregar_dados():
    try:
        df = pd.read_excel(URL, sheet_name="Tabela Performance")
    except Exception:
        st.warning("⚠️ Não foi possível carregar do GitHub. Faça upload manual abaixo.")
        uploaded = st.file_uploader("📄 Envie a planilha Tabela_Performance_v2.xlsx", type=["xlsx"])
        if uploaded is not None:
            df = pd.read_excel(uploaded, sheet_name="Tabela Performance")
            st.success("✅ Base carregada com sucesso via upload manual.")
        else:
            st.stop()

    df = df[df["TP_META"].astype(str).str.lower().eq("real")].copy()
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce").fillna(0)
    df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype(int)
    df["NM_KPI_NORM"] = df["NM_KPI"].map(normalize_text)
    df["SEGMENTO_NORM"] = df["SEGMENTO"].map(normalize_text)
    df["SUBCANAL_NORM"] = df["NM_SUBCANAL"].map(normalize_text)
    df["TORRE_NORM"] = df["NM_TORRE"].map(normalize_text)
    return df

df = carregar_dados()

# ====================== HELPERS ======================
def fmt_int(x):
    try: return f"{np.floor(float(x)+1e-9):,.0f}".replace(",", ".")
    except: return "0"

def regra_retido_por_tribo(tribo):
    if str(tribo).strip().lower() == "dma":
        return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])

# ====================== FUNÇÕES DE LEITURA ======================
def soma_kpi(df_scope, termos):
    mask = False
    for termo in termos:
        mask |= df_scope["NM_KPI_NORM"].str.contains(termo, case=False, na=False)
    return df_scope.loc[mask, "VOL_KPI"].sum()

def get_volumes(df, segmento, subcanal, anomes):
    seg_key = normalize_text(segmento)
    sub_key = normalize_text(subcanal)
    df_f = df[
        (df["SEGMENTO_NORM"] == seg_key) &
        (df["SUBCANAL_NORM"] == sub_key) &
        (df["ANOMES"] == anomes)
    ].copy()

    vol_71 = soma_kpi(df_f, ["transacao", "transa", "7 1"])
    vol_41 = soma_kpi(df_f, ["usuario unico", "cpf", "4 1"])
    vol_6  = soma_kpi(df_f, ["acesso", "6 "])
    return float(vol_71), float(vol_41), float(vol_6)

def tx_trn_por_acesso(vol_71, vol_6):
    return max(vol_71 / vol_6, 1.0) if vol_6 > 0 else 1.0

def tx_uu_por_cpf(vol_71, vol_41):
    return vol_71 / vol_41 if vol_41 > 0 else DEFAULT_TX_UU_CPF

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
c1, c2, c3 = st.columns(3)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 SEGMENTO", segmentos)
anomes_unicos = sorted(df["ANOMES"].unique())
meses_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
mes_legivel = [f"{meses_map[int(str(a)[4:]) ]}/{str(a)[:4]}" for a in anomes_unicos]
map_anomes_legivel = dict(zip(mes_legivel, anomes_unicos))
anomes_legivel = c2.selectbox("🗓️ MÊS", mes_legivel, index=len(mes_legivel)-1)
anomes_escolhido = map_anomes_legivel[anomes_legivel]
subcanais = sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique())
subcanal = c3.selectbox("📌 SUBCANAL", subcanais)

df_sub = df[(df["SEGMENTO"] == segmento) & (df["NM_SUBCANAL"] == subcanal) & (df["ANOMES"] == anomes_escolhido)]
tribo = df_sub["NM_TORRE"].dropna().unique().tolist()[0] if not df_sub.empty else "Indefinido"

# ====================== INPUT ======================
st.markdown("---")

volume_trans = st.number_input("📥 VOLUME DE TRANSAÇÕES ESPERADO", min_value=0, value=1_000, step=1000)

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    vol_71, vol_41, vol_6 = get_volumes(df, segmento, subcanal, anomes_escolhido)
    tx_trn_acc = tx_trn_por_acesso(vol_71, vol_6)
    tx_uu_cpf = tx_uu_por_cpf(vol_71, vol_41)
    cr_segmento = CR_SEGMENTO.get(segmento, 0.50)
    retido = regra_retido_por_tribo(tribo)

    vol_acessos = volume_trans / tx_trn_acc if tx_trn_acc > 0 else 0
    mau_cpf = volume_trans / tx_uu_cpf if tx_uu_cpf > 0 else 0
    cr_evitado = vol_acessos * cr_segmento * retido
    cr_evitado_floor = np.floor(cr_evitado + 1e-9)

    # Resultados
    st.markdown("---")
    st.markdown("### 📊 ResultadoS")
    c1,c2,c3 = st.columns(3)
    c1.metric("VOLUME DE TRANSAÇÕES", fmt_int(volume_trans))
    c2.metric("TAXA TRANSAÇÃO × ACESSO", f"{tx_trn_acc:.2f}")
    c3.metric("% LIGAÇÃO DIRECIONADA HUMANO", f"{cr_segmento*100:.2f}%")
    c4,c5,c6 = st.columns(3)
    c4.metric("RETIDO DIGITAL 72H", f"{retido*100:.2f}%")
    c5.metric("VOLUME DE ACESSOS", fmt_int(vol_acessos))
    c6.metric("VOLUME DE MAU (CPF)", fmt_int(mau_cpf))

    with st.expander("🔍 Diagnóstico de Premissas", expanded=False):
        st.markdown(f"""
        **Segmento:** {segmento}  
        **Subcanal:** {subcanal}  
        **Tribo:** {tribo}  
        **ANOMES:** {anomes_escolhido}  

        | Item | Valor |
        |------|------:|
        | Volume transacoes | {fmt_int(vol_71)} |
        | Volume usuarios_unicos_cpf | {fmt_int(vol_41)} |
        | Volume acessos | {fmt_int(vol_6)} |
        | **Tx Transações/Acessos** | {tx_trn_acc:.2f} |
        | **Tx UU/CPF** | {tx_uu_cpf:.2f} |
        | CR Segmento | {cr_segmento*100:.2f}% |
        | % Retido Aplicado | {retido*100:.2f}% |
        """, unsafe_allow_html=True)

    # =================== KPI CARD ===================
    st.markdown(
        f"""
        <div style="max-width:630px; padding:30px 45px;
        background:linear-gradient(90deg,#b31313 0%,#d01f1f 60%,#e23a3a 100%);
        border-radius:18px;box-shadow:0 8px 18px rgba(139,0,0,.25);color:#fff;">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="font-weight:700;font-size:30px;">Volume de CR Evitado Estimado</div>
            <div style="font-weight:800;font-size:40px;background:#fff;color:#b31313;
                        padding:6px 16px;border-radius:12px;line-height:1">{fmt_int(cr_evitado_floor)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Fórmulas: Acessos = Transações ÷ (Tx Transações/Acesso).  MAU = Transações ÷ (Transações/Usuários Únicos).  CR Evitado = Acessos × CR × %Retido.")

    # =================== PARETO ===================
    st.markdown("---")
    st.markdown("### 📄 Simulação - Todos os Subcanais")
    resultados = []
    for sub in sorted(df.loc[df["SEGMENTO"] == segmento, "NM_SUBCANAL"].dropna().unique()):
        df_i = df[
            (df["SEGMENTO"] == segmento)
            & (df["NM_SUBCANAL"] == sub)
            & (df["ANOMES"] == anomes_escolhido)
        ]
        tribo_i = df_i["NM_TORRE"].dropna().unique().tolist()[0] if not df_i.empty else "Indefinido"
        v71, v41, v6 = get_volumes(df, segmento, sub, anomes_escolhido)
        tx_i = tx_trn_por_acesso(v71, v6)
        tx_uu_i = tx_uu_por_cpf(v71, v41)
        ret_i = regra_retido_por_tribo(tribo_i)
        cr_i = CR_SEGMENTO.get(segmento, 0.50)

        vol_acc_i = volume_trans / tx_i if tx_i > 0 else 0
        mau_i = volume_trans / tx_uu_i if tx_uu_i > 0 else 0
        est_i = np.floor((vol_acc_i * cr_i * ret_i) + 1e-9)

        resultados.append({
            "Subcanal": sub,
            "Tribo": tribo_i,
            "Tx Trans/Acessos": round(tx_i,2),
            "Tx UU/CPF": round(tx_uu_i,2),
            "% Retido": round(ret_i*100,2),
            "% CR": round(cr_i*100,2),
            "Volume Acessos": int(vol_acc_i),
            "MAU (CPF)": int(mau_i),
            "Volume CR Evitado": int(est_i)
        })

    df_lote = pd.DataFrame(resultados)
    st.dataframe(df_lote, use_container_width=False)

    # Pareto
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_p = df_lote.sort_values("Volume CR Evitado", ascending=False).reset_index(drop=True)
    tot = df_p["Volume CR Evitado"].sum()
    df_p["Acumulado"] = df_p["Volume CR Evitado"].cumsum()
    df_p["Acumulado %"] = 100 * df_p["Acumulado"] / tot if tot > 0 else 0
    df_p["Cor"] = np.where(df_p["Acumulado %"] <= 80, "crimson", "lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_p["Subcanal"], y=df_p["Volume CR Evitado"],
                         name="Volume CR Evitado", marker_color=df_p["Cor"]))
    fig.add_trace(go.Scatter(x=df_p["Subcanal"], y=df_p["Acumulado %"],
                             name="Acumulado %", mode="lines+markers",
                             marker=dict(color="royalblue"), yaxis="y2"))
    fig.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0,100]),
        legend=dict(x=0.7, y=1.15, orientation="h"),
        bargap=0.2, margin=dict(l=10,r=10,t=60,b=80)
    )
    st.plotly_chart(fig, use_container_width=False)

    df_top = df_p[df_p["Acumulado %"] <= 80]
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top[["Subcanal","Tribo","Volume CR Evitado","Acumulado %"]],
                 use_container_width=False)

    total_ev = int(df_lote["Volume CR Evitado"].sum())
    top_names = ", ".join(df_top["Subcanal"].tolist())
    st.markdown("### 🧠 Insight Automático")

- **{len(df_top)} subcanais** concentram **80 %** do potencial: **{top_names}**.  
- **Ação:** priorize estes subcanais para maximizar impacto.""")

    # Download Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as w:
        df_lote.to_excel(w, sheet_name="Resultados", index=False)
        df_top.to_excel(w, sheet_name="Top_80_Pareto", index=False)
    st.download_button("📥 Baixar Excel Completo", buffer.getvalue(),
                       file_name="simulacao_cr.xlsx",
                       mime="application/vnd.ms-excel")







