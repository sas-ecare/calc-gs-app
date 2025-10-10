# app_calculadora_ganhos.py — leitura robusta de 7.1 / 4.1, normalização e fallbacks
import io, base64
from pathlib import Path
import numpy as np, pandas as pd, plotly.graph_objects as go, streamlit as st

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
RETIDO_DICT = {"App":0.9169,"Bot":0.8835,"Web":0.9027}        # % Retido 72h por tribo (DMA usa Bot)
CR_SEGMENTO = {"Móvel":0.4947,"Residencial":0.4989}           # % Lig. Direcionada Humano por segmento
DEFAULT_TX_UU_CPF = 12.28                                      # fallback final

# ====================== BASE ======================
URL = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

def _norm(s: pd.Series) -> pd.Series:
    # normaliza/remover acentos, hifens diferentes e espaços duplos
    s = s.astype(str).str.strip()
    s = s.str.replace(r"\s+", " ", regex=True)
    s = (s.str.normalize("NFKD")
           .str.encode("ascii", "ignore").str.decode("ascii"))
    s = s.str.replace("–", "-", regex=False).str.lower()
    return s

@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL, sheet_name="Tabela Performance")
    # filtros e tipos
    df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce").fillna(0.0)
    df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype("Int64")

    # colunas normalizadas para match robusto
    for c in ["SEGMENTO","NM_SUBCANAL","NM_TORRE","NM_KPI"]:
        df[c+"_N"] = _norm(df[c])
    return df

df = carregar_dados()

# ====================== HELPERS ======================
def fmt_int(x):
    try:
        return f"{np.floor(float(x)+1e-9):,.0f}".replace(",", ".")
    except Exception:
        return "0"

def regra_retido_por_tribo(tribo):
    if str(tribo).strip().lower() == "dma":   # regra: DMA usa Bot
        return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo, RETIDO_DICT["Web"])

def _mask_71(kpin: pd.Series):
    return kpin.str.contains(r"\b7\.?1\b") & kpin.str.contains("transa")

def _mask_41cpf(kpin: pd.Series):
    return (kpin.str.contains(r"\b4\.?1\b") &
            kpin.str.contains("unicos") &
            kpin.str.contains("cpf"))

def _mask_6_acessos(kpin: pd.Series):
    return (kpin.str.match(r"^6\b") & kpin.str.contains("acess"))

def obter_kpis(df_all: pd.DataFrame, segmento: str, subcanal: str, tribo: str, anomes: int):
    """
    Retorna (vt_71, vu_41, va_6, origem), tentando em camadas:
    1) seg+sub+tribo+mes  2) seg+sub+mes  3) seg+mes
    """
    segN = _norm(pd.Series([segmento])).iat[0]
    subN = _norm(pd.Series([subcanal])).iat[0]
    triN = _norm(pd.Series([tribo])).iat[0]

    base_real = (df_all["TP_META"].str.lower()=="real")

    camadas = [
        ("NM_SUBCANAL+TORRE",  base_real & (df_all["SEGMENTO_N"]==segN) & (df_all["NM_SUBCANAL_N"]==subN) & (df_all["NM_TORRE_N"]==triN) & (df_all["ANOMES"]==anomes)),
        ("NM_SUBCANAL",        base_real & (df_all["SEGMENTO_N"]==segN) & (df_all["NM_SUBCANAL_N"]==subN) & (df_all["ANOMES"]==anomes)),
        ("SEGMENTO",           base_real & (df_all["SEGMENTO_N"]==segN) & (df_all["ANOMES"]==anomes)),
    ]

    for origem, mask in camadas:
        d = df_all.loc[mask].copy()
        if d.empty:
            continue
        kpin = d["NM_KPI_N"]

        vt = float(d.loc[_mask_71(kpin), "VOL_KPI"].sum())       # 7.1 Transações
        vu = float(d.loc[_mask_41cpf(kpin), "VOL_KPI"].sum())    # 4.1 Usuários Únicos (CPF)
        va = float(d.loc[_mask_6_acessos(kpin), "VOL_KPI"].sum())# 6 Acessos Usuários

        if vt>0 or vu>0 or va>0:
            return vt, vu, va, origem

    return 0.0, 0.0, 0.0, "Fallback"

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
c1,c2,c3 = st.columns(3)

segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 Segmento", segmentos)

anomes_unicos = sorted([int(x) for x in df["ANOMES"].dropna().unique().tolist()])
meses_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
labels = [f"{meses_map[int(str(a)[4:]) ]}/{str(a)[:4]}" for a in anomes_unicos]
map_label = dict(zip(labels, anomes_unicos))
label_mes = c2.selectbox("🗓️ Mês", labels, index=len(labels)-1)
anomes_sel = map_label[label_mes]

subcanais = sorted(df.loc[df["SEGMENTO"]==segmento,"NM_SUBCANAL"].dropna().unique())
subcanal = c3.selectbox("📌 Subcanal", subcanais)

# tribo do subcanal no mês (se houver)
df_sub = df[(df["SEGMENTO"]==segmento)&(df["NM_SUBCANAL"]==subcanal)&(df["ANOMES"]==anomes_sel)]
tribo = df_sub["NM_TORRE"].dropna().unique().tolist()[0] if not df_sub.empty else "Indefinido"

k1,k2,k3,k4 = st.columns(4)
k1.metric("Tribo",tribo)
k2.metric("Canal",tribo)
k3.metric("Segmento",segmento)
k4.metric("Subcanal",subcanal)

# ====================== INPUT ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros de Simulação")
volume_trans = st.number_input("📥 Volume de Transações",min_value=0,value=10_000,step=1000)

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    cr_segmento = CR_SEGMENTO.get(segmento,0.50)
    retido = regra_retido_por_tribo(tribo)

    # KPIs brutos (robustos)
    vt_71, vu_41, va_6, origem_kpi = obter_kpis(df, segmento, subcanal, tribo, anomes_sel)

    # Taxas
    tx_trn_acc = max((vt_71 / va_6) if (vt_71>0 and va_6>0) else 1.0, 1.0)     # 7.1/6, min 1.00
    tx_uu_cpf  = (vt_71 / vu_41) if (vt_71>0 and vu_41>0) else DEFAULT_TX_UU_CPF

    # Cálculos principais (iguais à sua planilha)
    vol_acessos = volume_trans / tx_trn_acc
    mau_cpf     = volume_trans / tx_uu_cpf
    vol_lig_ev  = vol_acessos * cr_segmento * retido
    vol_lig_ev  = np.floor(vol_lig_ev + 1e-9)  # truncar, não arredondar p/ cima

    # =================== RESULTADOS ===================
    st.markdown("---")
    st.markdown("### 📊 Resultados Detalhados (Fórmulas)")
    cA,cB,cC,cD = st.columns(4)
    cA.metric("Taxa de Transação × Acesso", f"{tx_trn_acc:.2f}")
    cB.metric("% Ligação Direcionada Humano", f"{cr_segmento*100:.2f}%")
    cC.metric("Retido Digital 72h", f"{retido*100:.2f}%")
    cD.metric("MAU (CPF)", fmt_int(mau_cpf))

    # Card premium
    st.markdown(
        f"""
        <div style="max-width:520px;margin:18px auto;padding:18px 22px;
        background:linear-gradient(90deg,#b31313 0%,#d01f1f 60%,#e23a3a 100%);
        border-radius:18px;box-shadow:0 8px 18px rgba(139,0,0,.25);color:#fff;">
        <div style="display:flex;justify-content:space-between;align-items:center">
        <div style="font-weight:700;font-size:20px;">Volume de CR Evitado Estimado</div>
        <div style="font-weight:800;font-size:30px;background:#fff;color:#b31313;
        padding:6px 16px;border-radius:12px;line-height:1">{fmt_int(vol_lig_ev)}</div>
        </div></div>""", unsafe_allow_html=True)

    # Diagnóstico (mostra 7.1, 4.1, 6 e origem)
    with st.expander("🔍 Diagnóstico de Premissas", expanded=True):
        st.markdown(f"""
        **Segmento:** {segmento}  
        **Subcanal:** {subcanal}  
        **Tribo:** {tribo}  
        **ANOMES usado:** {anomes_sel}  

        | Item | Valor |
        |------|------:|
        | Volume Transações (7.1) | {fmt_int(vt_71)} |
        | Volume Usuários Únicos (4.1 - CPF) | {fmt_int(vu_41)} |
        | Volume Acessos Usuários (6) | {fmt_int(va_6)} |
        | TX_UU_CPF Calculado | {tx_uu_cpf:.2f} |
        | Origem | {origem_kpi} |
        | CR Segmento | {cr_segmento*100:.2f}% |
        | % Retido Aplicado | {retido*100:.2f}% |
        """, unsafe_allow_html=True)

    # =================== PARETO ===================
    st.markdown("---")
    st.markdown("### 📄 Simulação - Todos os Subcanais")
    resultados=[]
    for sub in sorted(df.loc[df["SEGMENTO"]==segmento,"NM_SUBCANAL"].dropna().unique()):
        df_i = df[(df["SEGMENTO"]==segmento)&(df["NM_SUBCANAL"]==sub)&(df["ANOMES"]==anomes_sel)]
        tribo_i = df_i["NM_TORRE"].dropna().unique().tolist()[0] if not df_i.empty else "Indefinido"

        vt_i, vu_i, va_i, _ = obter_kpis(df, segmento, sub, tribo_i, anomes_sel)
        tx_acc_i = max((vt_i/va_i) if (vt_i>0 and va_i>0) else 1.0, 1.0)
        tx_uu_i  = (vt_i/vu_i) if (vt_i>0 and vu_i>0) else DEFAULT_TX_UU_CPF

        ret_i = regra_retido_por_tribo(tribo_i)
        cr_i  = CR_SEGMENTO.get(segmento, 0.50)

        vol_acc_i = volume_trans / tx_acc_i
        mau_i     = volume_trans / tx_uu_i
        est_i     = np.floor(vol_acc_i * cr_i * ret_i + 1e-9)

        resultados.append({
            "Subcanal": sub,
            "Tribo": tribo_i,
            "Transações / Acesso": round(tx_acc_i,2),
            "↓ % Retido": round(ret_i*100,2),
            "% CR": round(cr_i*100,2),
            "MAU (CPF)": int(mau_i),
            "Volume de CR Evitado": int(est_i)
        })

    df_lote = pd.DataFrame(resultados)
    st.dataframe(df_lote, use_container_width=False)

    # Pareto
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_p = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    tot = df_p["Volume de CR Evitado"].sum()
    if tot>0:
        df_p["Acumulado"]  = df_p["Volume de CR Evitado"].cumsum()
        df_p["Acumulado %"]= 100 * df_p["Acumulado"] / tot
    else:
        df_p["Acumulado"]=0; df_p["Acumulado %"]=0.0
    df_p["Cor"] = np.where(df_p["Acumulado %"]<=80, "crimson", "lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_p["Subcanal"], y=df_p["Volume de CR Evitado"],
                         name="Volume de CR Evitado", marker_color=df_p["Cor"]))
    fig.add_trace(go.Scatter(x=df_p["Subcanal"], y=df_p["Acumulado %"],
                             name="Acumulado %", mode="lines+markers",
                             marker=dict(color="royalblue"), yaxis="y2"))
    fig.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(x=0.7, y=1.15, orientation="h"),
        bargap=0.2, margin=dict(l=10, r=10, t=60, b=80)
    )
    st.plotly_chart(fig, use_container_width=False)

    df_top = df_p[df_p["Acumulado %"]<=80]
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top[["Subcanal","Tribo","Volume de CR Evitado","Acumulado %"]],
                 use_container_width=False)

    tot_ev = int(df_lote["Volume de CR Evitado"].sum())
    top_names = ", ".join(df_top["Subcanal"].tolist())
    st.markdown(f"""**🧠 Insight Automático**  

- Volume total estimado de **CR evitado**: **{fmt_int(tot_ev)}**.  
- **{len(df_top)} subcanais** concentram **80 %** do potencial: **{top_names}**.  
- **Ação:** priorize estes subcanais para maximizar impacto.""")

    # Download
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as w:
        df_lote.to_excel(w, sheet_name="Resultados", index=False)
        df_top.to_excel(w, sheet_name="Top_80_Pareto", index=False)
    st.download_button("📥 Baixar Excel Completo", buffer.getvalue(),
                       file_name="simulacao_cr.xlsx",
                       mime="application/vnd.ms-excel")
