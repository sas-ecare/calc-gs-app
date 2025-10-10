# app_calculadora_ganhos.py — MAU/CPF fix (vol_by_kpi robusto, Subcanal1 prioridade)
import io, base64, re
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ====================== CONFIG ======================
st.set_page_config(page_title="🖩 Calculadora de Ganhos", page_icon="📶", layout="wide")

# ====================== LOGIN ======================
def check_password():
    def ok():
        st.session_state["auth"] = (st.session_state.get("pwd") == "claro@123")
        if not st.session_state["auth"]:
            st.error("Senha incorreta. Tente novamente.")
    if "auth" not in st.session_state:
        st.session_state["auth"] = False
    if not st.session_state["auth"]:
        st.text_input("🔐 Insira a senha:", type="password", on_change=ok, key="pwd")
        st.stop()
check_password()

# ====================== LOGO ======================
def _find_asset_bytes(names=("claro_logo","logo_claro","claro")):
    for d in (Path.cwd(), Path.cwd()/ "assets", Path.cwd()/ "static"):
        for base in names:
            for ext in (".png",".jpg",".jpeg",".webp"):
                p=(d/f"{base}{ext}")
                if p.exists(): return p.read_bytes()
    return None

logo=_find_asset_bytes()
if logo:
    b64=base64.b64encode(logo).decode()
    st.markdown(f"""
    <h1 style='text-align:center;color:#8B0000;font-size:54px;'>
      <img src='data:image/png;base64,{b64}' style='height:70px;vertical-align:middle;margin-right:10px'>
      Calculadora de Ganhos
    </h1>""", unsafe_allow_html=True)
else:
    st.markdown("<h1 style='text-align:center;color:#8B0000;'>🖩 Calculadora de Ganhos</h1>", unsafe_allow_html=True)

# ====================== CONSTANTES ======================
RETIDO = {"App":0.9169,"Bot":0.8835,"Web":0.9027}
CR_SEG = {"Móvel":0.4947, "Residencial":0.4989}
DEFAULT_TX_UU = 12.28

# ====================== NORMALIZAÇÃO ======================
def _norm_txt(s):
    if not isinstance(s,str):
        s = str(s) if s is not None else ""
    s = s.lower()
    s = re.sub(r"[\s\-_]+"," ",s)
    s = s.replace("ç","c").replace("ã","a").replace("õ","o")
    return s.strip()

# ====================== CONSTANTES DE KPI ======================
KPI_TRANS    = _norm_txt("7.1 - Transações")
KPI_ACESSOS  = _norm_txt("6 - Acessos Usuários")
KPI_UU_CPF   = _norm_txt("4.1 - CPF")

# ====================== BASE ======================
URL_RAW = "https://raw.githubusercontent.com/gustavo3-freitas/base_calculadora/main/Tabela_Performance.xlsx"

@st.cache_data(show_spinner=True)
def load_df_from_bytes(file_bytes: bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    df = pd.read_excel(xls, sheet_name="Tabela Performance")
    return df

@st.cache_data(show_spinner=True)
def load_df_from_url():
    return pd.read_excel(URL_RAW, sheet_name="Tabela Performance")

def prep_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "TP_META" in df:
        df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    if "VOL_KPI" in df:
        df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce")
    if "ANOMES" in df:
        df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype("Int64")
    # Subcanal prioritário
    if "Subcanal1" in df.columns:
        df["__SUB__"] = df["Subcanal1"]
    elif "NM_SUBCANAL" in df.columns:
        df["__SUB__"] = df["NM_SUBCANAL"]
    else:
        st.error("A base não possui as colunas Subcanal1/NM_SUBCANAL.")
        st.stop()
    # Colunas normalizadas
    for col in ["NM_KPI","SEGMENTO","__SUB__","NM_TORRE"]:
        if col in df.columns:
            df[f"{col}_KEY"] = df[col].astype(str).map(_norm_txt)
    return df

up = st.file_uploader("📄 Opcional: envie a planilha Tabela_Performance.xlsx", type=["xlsx"])
try:
    df_raw = load_df_from_bytes(up.read()) if up else load_df_from_url()
except Exception:
    st.error("❌ Falha ao abrir a planilha.")
    st.stop()
df = prep_df(df_raw)

# ====================== FUNÇÕES KPI ======================
def vol_by_kpi(df_scope: pd.DataFrame, kpi_key: str) -> float:
    """
    Igualdade exata + fallback tolerante (7.1, 4.1 CPF, 6 Acessos)
    """
    if df_scope.empty: return 0.0
    vol = df_scope.loc[df_scope["NM_KPI_KEY"].eq(kpi_key),"VOL_KPI"].sum()
    # Fallbacks
    if vol == 0 and ("4.1" in kpi_key or "cpf" in kpi_key):
        vol = df_scope.loc[
            df_scope["NM_KPI_KEY"].str.contains(r"4\.1") &
            df_scope["NM_KPI_KEY"].str.contains("cpf"),
            "VOL_KPI"
        ].sum()
    if vol == 0 and ("7.1" in kpi_key or "transa" in kpi_key):
        vol = df_scope.loc[
            df_scope["NM_KPI_KEY"].str.contains(r"7\.1") &
            df_scope["NM_KPI_KEY"].str.contains("transa"),
            "VOL_KPI"
        ].sum()
    if vol == 0 and ("6" in kpi_key or "acess" in kpi_key):
        vol = df_scope.loc[
            df_scope["NM_KPI_KEY"].str.contains(r"\b6\b") &
            df_scope["NM_KPI_KEY"].str.contains("acess"),
            "VOL_KPI"
        ].sum()
    return float(vol)

def tx_trn_por_acesso(df_scope: pd.DataFrame) -> float:
    vt = vol_by_kpi(df_scope, KPI_TRANS)
    va = vol_by_kpi(df_scope, KPI_ACESSOS)
    if va <= 0: return 1.0
    return vt / va

def tx_uu_cpf_dyn(df_all, segmento, subcanal, anomes, tribo):
    seg_key=_norm_txt(segmento)
    sub_key=_norm_txt(subcanal)
    tor_key=_norm_txt(tribo)
    df_f = df_all[
        (df_all["ANOMES"]==anomes) &
        (df_all["SEGMENTO_KEY"]==seg_key) &
        (df_all["__SUB___KEY"]==sub_key if "__SUB___KEY" in df_all else df_all["__SUB___KEY"]) &
        (df_all["NM_TORRE_KEY"]==tor_key)
    ].copy()
    vt = vol_by_kpi(df_f, KPI_TRANS)
    vu = vol_by_kpi(df_f, KPI_UU_CPF)
    if vt>0 and vu>0:
        tx_calc = vt/vu
        return tx_calc, vt, vu, "NM_SUBCANAL", anomes, tx_calc
    # fallback segmento
    df_seg = df_all[(df_all["ANOMES"]==anomes)&(df_all["SEGMENTO_KEY"]==seg_key)]
    vt_s = vol_by_kpi(df_seg, KPI_TRANS)
    vu_s = vol_by_kpi(df_seg, KPI_UU_CPF)
    if vt_s>0 and vu_s>0:
        tx_calc = vt_s/vu_s
        return tx_calc, vt_s, vu_s, "SEGMENTO", anomes, tx_calc
    return DEFAULT_TX_UU, vt, vu, "Fallback", anomes, 0.0

def retido_72h(tribo:str)->float:
    if str(tribo).strip().lower()=="dma": return RETIDO["Bot"]
    return RETIDO.get(tribo, RETIDO["Web"])

def fmt_int(x):
    try: return f"{np.floor(float(x)+1e-9):,.0f}".replace(",",".")
    except: return "0"

# ====================== FILTROS ======================
st.markdown("### 🔎 Filtros de Cenário")
c1,c2,c3 = st.columns(3)
segmentos=sorted(df["SEGMENTO"].dropna().unique())
segmento=c1.selectbox("📊 Segmento",segmentos)

anomes_vals=sorted(df["ANOMES"].dropna().astype(int).unique())
meses={1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
labels=[f"{meses[int(str(a)[4:])]}/{str(a)[:4]}" for a in anomes_vals]
map_lab=dict(zip(labels,anomes_vals))
lab=c2.selectbox("🗓️ Mês",labels,index=len(labels)-1)
anomes=map_lab[lab]

subs=sorted(df.loc[df["SEGMENTO"]==segmento,"__SUB__"].dropna().unique())
subcanal=c3.selectbox("📌 Subcanal",subs)

df_scope=df[(df["SEGMENTO"]==segmento)&(df["__SUB__"]==subcanal)&(df["ANOMES"]==anomes)]
tribo=df_scope["NM_TORRE"].dropna().unique().tolist()[0] if not df_scope.empty else "Indefinido"

m1,m2,m3,m4=st.columns(4)
m1.metric("Tribo",tribo)
m2.metric("Canal",tribo)
m3.metric("Segmento",segmento)
m4.metric("Subcanal",subcanal)

# ====================== INPUT ======================
st.markdown("---")
st.markdown("### ➗ Parâmetros de Simulação")
volume_trans=st.number_input("📥 Volume de Transações",min_value=0,value=10_000,step=1000)

# ====================== CÁLCULOS ======================
if st.button("🚀 Calcular Ganhos Potenciais"):
    if df_scope.empty:
        st.warning("❌ Nenhum dado encontrado.")
        st.stop()

    cr=CR_SEG.get(segmento,0.5)
    tx_trn_acc=tx_trn_por_acesso(df_scope)
    ret=retido_72h(tribo)
    tx_uu_cpf,vt_real,vu_real,origem_tx,anomes_usado,tx_calc_real=tx_uu_cpf_dyn(df,segmento,subcanal,anomes,tribo)

    vol_acessos=volume_trans/tx_trn_acc
    mau_cpf=volume_trans/(tx_uu_cpf if tx_uu_cpf>0 else DEFAULT_TX_UU)
    cr_evit=vol_acessos*cr*ret
    cr_evit_floor=np.floor(cr_evit+1e-9)

    # ---------------- RESULTADOS ----------------
    st.markdown("---")
    st.markdown("### 📊 Resultados Detalhados (Fórmulas)")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Volume de Transações (7.1)",fmt_int(vt_real))
    c2.metric("Volume de Usuários Únicos (4.1 - CPF)",fmt_int(vu_real))
    c3.metric("Tx UU por CPF (7.1 ÷ 4.1)",f"{(vt_real/vu_real) if (vt_real>0 and vu_real>0) else 0:.2f}")
    c4.metric("MAU por CPF (estimado)",fmt_int(mau_cpf))

    with st.expander("🔍 Diagnóstico de Premissas",expanded=False):
        st.markdown(f"""
**Segmento:** {segmento}  
**Subcanal:** {subcanal}  
**Tribo:** {tribo}  
**ANOMES usado:** {anomes_usado}  

| Item | Valor |
|---|---:|
| Volume Transações (7.1) | {fmt_int(vt_real)} |
| Volume Usuários Únicos (4.1 - CPF) | {fmt_int(vu_real)} |
| TX_UU_CPF Calculada | {("0.00" if not tx_calc_real else f"{tx_calc_real:.2f}")} |
| TX_UU_CPF Usada no cálculo | {tx_uu_cpf:.2f} |
| Origem | {origem_tx} |
| CR Segmento | {cr*100:.2f}% |
| % Retido Aplicado | {ret*100:.2f}% |
        """,unsafe_allow_html=True)

    st.markdown(
        f"""
        <div style="max-width:520px;margin:18px auto;padding:18px 22px;
        background:linear-gradient(90deg,#b31313 0%,#d01f1f 60%,#e23a3a 100%);
        border-radius:18px;box-shadow:0 8px 18px rgba(139,0,0,.25);color:#fff;">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="font-weight:700;font-size:20px;">Volume de CR Evitado Estimado</div>
            <div style="font-weight:800;font-size:30px;background:#fff;color:#b31313;
                        padding:6px 16px;border-radius:12px;line-height:1">{fmt_int(cr_evit_floor)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Fórmulas: Acessos = Transações ÷ (Tx Transações/Acesso).  MAU = Transações ÷ TX_UU_CPF.  CR Evitado = Acessos × CR × %Retido.")
