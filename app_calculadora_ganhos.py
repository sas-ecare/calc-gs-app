# app_calculadora_ganhos.py — versão final com TX_UU_CPF esperada no diagnóstico
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
RETIDO_DICT = {"App":0.9169,"Bot":0.8835,"Web":0.9027}
CR_SEGMENTO = {"Móvel":0.4947,"Residencial":0.4989}
DEFAULT_TX_UU_CPF = 12.28

# ====================== BASE ======================
URL = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"
@st.cache_data(show_spinner=True)
def carregar_dados():
    df = pd.read_excel(URL, sheet_name="Tabela Performance")
    df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce")
    df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype(int)
    return df
df = carregar_dados()

# ====================== FUNÇÕES ======================
def fmt_int(x):
    try:
        return f"{np.floor(float(x)+1e-9):,.0f}".replace(",",".")
    except Exception:
        return "0"

def sum_kpi(df_scope, patterns):
    if df_scope.empty or "NM_KPI" not in df_scope.columns:
        return 0.0
    m = False
    for p in patterns:
        m = m | df_scope["NM_KPI"].str.contains(p,case=False,na=False,regex=True)
    return float(df_scope.loc[m,"VOL_KPI"].sum())

def tx_trn_por_acesso(df_scope):
    vt = sum_kpi(df_scope,[r"7\.1","Transa"])
    va = sum_kpi(df_scope,[r"6","Acesso"])
    if va<=0: return 1.0
    return max(vt/va,1.0)

def regra_retido_por_tribo(tribo):
    if str(tribo).strip().lower()=="dma": return RETIDO_DICT["Bot"]
    return RETIDO_DICT.get(tribo,RETIDO_DICT["Web"])

def tx_uu_cpf_dyn(df_all, segmento, subcanal, anomes, tribo):
    """
    Busca exata dos KPIs:
    7.1 - Transações
    4.1 - Usuários Únicos (CPF)
    """
    df_filt = df_all[
        (df_all["TP_META"].astype(str).str.lower() == "real") &
        (df_all["ANOMES"] == anomes) &
        (df_all["SEGMENTO"] == segmento) &
        (df_all["NM_SUBCANAL"] == subcanal) &
        (df_all["NM_TORRE"] == tribo)
    ].copy()

    if df_filt.empty:
        return (DEFAULT_TX_UU_CPF, 0.0, 0.0, "Fallback", anomes, 0.0)

    df_filt["NM_KPI_LIMPO"] = df_filt["NM_KPI"].str.strip().str.lower()
    vt = df_filt.loc[
        df_filt["NM_KPI_LIMPO"].str.contains("7.1") &
        df_filt["NM_KPI_LIMPO"].str.contains("transa"),
        "VOL_KPI"
    ].sum()
    vu = df_filt.loc[
        df_filt["NM_KPI_LIMPO"].str.contains("4.1") &
        df_filt["NM_KPI_LIMPO"].str.contains("cpf"),
        "VOL_KPI"
    ].sum()

    if vt>0 and vu>0:
        tx_calc = vt/vu
        return (tx_calc, vt, vu, "NM_SUBCANAL", anomes, tx_calc)
    else:
        return (DEFAULT_TX_UU_CPF, vt, vu, "Fallback", anomes, 0.0)

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
c1,c2,c3 = st.columns(3)
segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = c1.selectbox("📊 Segmento", segmentos)

anomes_unicos = sorted(df["ANOMES"].unique())
meses_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
mes_legivel = [f"{meses_map[int(str(a)[4:]) ]}/{str(a)[:4]}" for a in anomes_unicos]
map_anomes_legivel = dict(zip(mes_legivel, anomes_unicos))
anomes_legivel = c2.selectbox("🗓️ Mês", mes_legivel, index=len(mes_legivel)-1)
anomes_escolhido = map_anomes_legivel[anomes_legivel]

subcanais = sorted(df.loc[df["SEGMENTO"]==segmento,"NM_SUBCANAL"].dropna().unique())
subcanal = c3.selectbox("📌 Subcanal", subcanais)

df_sub = df[(df["SEGMENTO"]==segmento)&(df["NM_SUBCANAL"]==subcanal)&(df["ANOMES"]==anomes_escolhido)]
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
    if df_sub.empty:
        st.warning("❌ Nenhum dado encontrado para o mês selecionado.")
        st.stop()

    tx_trn_acc = tx_trn_por_acesso(df_sub)
    cr_segmento = CR_SEGMENTO.get(segmento,0.50)
    retido = regra_retido_por_tribo(tribo)
    vol_acessos = volume_trans/tx_trn_acc

    tx_uu_cpf, vol_trn_real, vol_user_real, origem_tx, anomes_usado, tx_calc_real = tx_uu_cpf_dyn(df,segmento,subcanal,anomes_escolhido,tribo)
    mau_cpf = volume_trans/(tx_uu_cpf if tx_uu_cpf>0 else DEFAULT_TX_UU_CPF)
    vol_lig_ev_hum = (volume_trans/tx_trn_acc)*cr_segmento*retido

    # =================== RESULTADOS ===================
    st.markdown("---")
    st.markdown("### 📊 Resultados Detalhados (Fórmulas)")
    c1,c2,c3 = st.columns(3)
    c1.metric("Volume de Transações", fmt_int(volume_trans))
    c2.metric("Taxa de Transação × Acesso", f"{tx_trn_acc:.2f}")
    c3.metric("% Ligação Direcionada Humano", f"{cr_segmento*100:.2f}%")
    c4,c5,c6 = st.columns(3)
    c4.metric("Retido Digital 72h", f"{retido*100:.2f}%")
    c5.metric("Volume de Acessos", fmt_int(vol_acessos))
    c6.metric("Volume de MAU (CPF)", fmt_int(mau_cpf))

    # =================== EXPANDER DIAGNÓSTICO ===================
    with st.expander("🔍 Diagnóstico de Premissas", expanded=False):
        st.markdown(f"""
        **Segmento:** {segmento}  
        **Subcanal:** {subcanal}  
        **Tribo:** {tribo}  
        **ANOMES usado:** {anomes_usado}  

        | Item | Valor |
        |------|-------:|
        | Volume Transações (7.1) | {fmt_int(vol_trn_real)} |
        | Volume Usuários Únicos (4.1 - CPF) | {fmt_int(vol_user_real)} |
        | TX_UU_CPF Calculada (Trans/Usuários) | {tx_calc_real:.2f} |
        | TX_UU_CPF Usada no cálculo | {tx_uu_cpf:.2f} |
        | Origem | {origem_tx} |
        | CR Segmento | {cr_segmento*100:.2f}% |
        | % Retido Aplicado | {retido*100:.2f}% |
        """, unsafe_allow_html=True)

    # =================== CARD DE RESULTADO ===================
    st.markdown(
        f"""
        <div style="max-width:520px;margin:18px auto;padding:18px 22px;
        background:linear-gradient(90deg,#b31313 0%,#d01f1f 60%,#e23a3a 100%);
        border-radius:18px;box-shadow:0 8px 18px rgba(139,0,0,.25);color:#fff;">
        <div style="display:flex;justify-content:space-between;align-items:center">
        <div style="font-weight:700;font-size:20px;">Volume de CR Evitado Estimado</div>
        <div style="font-weight:800;font-size:30px;background:#fff;color:#b31313;
        padding:6px 16px;border-radius:12px;line-height:1">{fmt_int(vol_lig_ev_hum)}</div>
        </div></div>""", unsafe_allow_html=True)

    st.caption("Fórmulas: Acessos = Transações ÷ (Tx Transações/Acesso).  MAU = Transações ÷ (Transações/Usuários Únicos).  CR Evitado = Acessos × CR × %Retido.")

    # =================== PARETO ===================
    st.markdown("---")
    st.markdown("### 📄 Simulação - Todos os Subcanais")

    resultados=[]
    for sub in sorted(df["NM_SUBCANAL"].dropna().unique()):
        df_i=df[(df["SEGMENTO"]==segmento)&(df["NM_SUBCANAL"]==sub)&(df["TP_META"].str.lower()=="real")]
        tribo_i=df_i["NM_TORRE"].dropna().unique().tolist()[0] if not df_i.empty else "Indefinido"
        tx_i=tx_trn_por_acesso(df_i)
        tx_uu_i,_,_,_,_,_=tx_uu_cpf_dyn(df,segmento,sub,anomes_escolhido,tribo_i)
        ret_i=regra_retido_por_tribo(tribo_i)
        cr_seg_i=CR_SEGMENTO.get(segmento,0.50)
        vol_acc_i=volume_trans/tx_i
        mau_i=volume_trans/(tx_uu_i if tx_uu_i>0 else DEFAULT_TX_UU_CPF)
        est_i=np.floor((vol_acc_i*cr_seg_i*ret_i)+1e-9)
        resultados.append({
            "Subcanal":sub,"Tribo":tribo_i,"Transações / Acessos":round(tx_i,2),
            "% Lig. Humano":round(cr_seg_i*100,2),"↓ % Retido":round(ret_i*100,2),
            "Volume de Acessos":int(vol_acc_i),"MAU (CPF)":int(mau_i),
            "Volume de CR Evitado":int(est_i)})

    df_lote=pd.DataFrame(resultados)
    st.dataframe(df_lote,use_container_width=False)

    # Pareto
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_p=df_lote.sort_values("Volume de CR Evitado",ascending=False).reset_index(drop=True)
    tot=df_p["Volume de CR Evitado"].sum()
    if tot>0:
        df_p["Acumulado"]=df_p["Volume de CR Evitado"].cumsum()
        df_p["Acumulado %"]=100*df_p["Acumulado"]/tot
    else:
        df_p["Acumulado"]=0; df_p["Acumulado %"]=0.0
    df_p["Cor"]=np.where(df_p["Acumulado %"]<=80,"crimson","lightgray")
    fig=go.Figure()
    fig.add_trace(go.Bar(x=df_p["Subcanal"],y=df_p["Volume de CR Evitado"],
                         name="Volume de CR Evitado",marker_color=df_p["Cor"]))
    fig.add_trace(go.Scatter(x=df_p["Subcanal"],y=df_p["Acumulado %"],name="Acumulado %",
                             mode="lines+markers",marker=dict(color="royalblue"),yaxis="y2"))
    fig.update_layout(title="📈 Pareto - Volume de CR Evitado",
                      xaxis=dict(title="Subcanais"),
                      yaxis=dict(title="Volume de CR Evitado"),
                      yaxis2=dict(title="Acumulado %",overlaying="y",side="right",range=[0,100]),
                      legend=dict(x=0.7,y=1.15,orientation="h"),bargap=0.2,
                      margin=dict(l=10,r=10,t=60,b=80))
    st.plotly_chart(fig,use_container_width=False)

    df_top=df_p[df_p["Acumulado %"]<=80]
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top[["Subcanal","Tribo","Volume de CR Evitado","Acumulado %"]],
                 use_container_width=False)

    tot_ev=int(df_lote["Volume de CR Evitado"].sum())
    top_names=", ".join(df_top["Subcanal"].tolist())
    st.markdown(f"""**🧠 Insight Automático**  

- Volume total estimado de **CR evitado**: **{fmt_int(tot_ev)}**.  
- **{len(df_top)} subcanais** concentram **80 %** do potencial: **{top_names}**.  
- **Ação:** priorize estes subcanais para maximizar impacto.""")

    # Download
    buffer=io.BytesIO()
    with pd.ExcelWriter(buffer,engine="xlsxwriter") as w:
        df_lote.to_excel(w,sheet_name="Resultados",index=False)
        df_top.to_excel(w,sheet_name="Top_80_Pareto",index=False)
    st.download_button("📥 Baixar Excel Completo",buffer.getvalue(),
                       file_name="simulacao_cr.xlsx",
                       mime="application/vnd.ms-excel")
