# app_calculadora_ganhos.py — Subcanal1 first, MAU/CPF fix, diagnóstico completo
import io, base64
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------- Config ----------------
st.set_page_config(page_title="🖩 Calculadora de Ganhos", page_icon="📶", layout="wide")

# ---------------- Login -----------------
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

# ---------------- Logotipo --------------
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

# ---------------- Parâmetros fixos ------
RETIDO = {"App":0.9169,"Bot":0.8835,"Web":0.9027}
CR_SEG = {"Móvel":0.4947, "Residencial":0.4989}
DEFAULT_TX_UU = 12.28

# ---------------- Base -------------------
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
    # normalizações
    if "TP_META" in df:
        df = df[df["TP_META"].astype(str).str.lower().eq("real")]
    for c in ("VOL_KPI",):
        if c in df: df[c] = pd.to_numeric(df[c], errors="coerce")
    if "ANOMES" in df:
        df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce").astype("Int64")
    # coluna de subcanal preferida
    if "Subcanal1" in df.columns:
        df["__SUB__"] = df["Subcanal1"]
    elif "NM_SUBCANAL" in df.columns:
        df["__SUB__"] = df["NM_SUBCANAL"]
    else:
        st.error("A base não possui as colunas Subcanal1/NM_SUBCANAL.")
        st.stop()
    return df

# fonte de dados: upload (prioritário) ou URL
up = st.file_uploader("📄 Opcional: envie a planilha Tabela_Performance.xlsx", type=["xlsx"])
try:
    if up is not None:
        raw = up.read()
        df_raw = load_df_from_bytes(raw)
    else:
        df_raw = load_df_from_url()
except Exception:
    st.error("❌ Falha ao abrir a planilha. Envie o arquivo pelo upload acima.")
    st.stop()

df = prep_df(df_raw)

# ---------------- Helpers ----------------
def fmt_int(x): 
    try: return f"{np.floor(float(x)+1e-9):,.0f}".replace(",",".")
    except Exception: return "0"

def kpi_sum(df_scope: pd.DataFrame, pattern: str) -> float:
    """Soma VOL_KPI com NM_KPI contendo exatamente o pattern (regex)."""
    if df_scope.empty or "NM_KPI" not in df_scope: return 0.0
    m = df_scope["NM_KPI"].str.contains(pattern, case=False, na=False, regex=True)
    return float(df_scope.loc[m, "VOL_KPI"].sum())

def tx_trn_por_acesso(df_scope):
    vt = kpi_sum(df_scope, r"7\.1\s*-\s*Transa")
    va = kpi_sum(df_scope, r"6\s*-\s*Acessos?")
    if va <= 0: return 1.0
    return max(vt/va, 1.0)

def retido_72h(tribo:str) -> float:
    if str(tribo).strip().lower()=="dma":  # regra: DMA usa retido do Bot
        return RETIDO["Bot"]
    return RETIDO.get(tribo, RETIDO["Web"])

def get_tx_uu_cpf(df_all: pd.DataFrame, anomes:int, segmento:str, subcanal:str, tribo:str):
    """Lê Transações (7.1) e Usuários Únicos (4.1 - CPF) com os MESMOS filtros."""
    d = df_all[
        (df_all["ANOMES"] == anomes) &
        (df_all["SEGMENTO"] == segmento) &
        (df_all["__SUB__"] == subcanal) &
        (df_all["NM_TORRE"] == tribo)
    ]
    vt = kpi_sum(d, r"7\.1\s*-\s*Transa")
    vu = kpi_sum(d, r"4\.1\s*-\s*Usuários?\s*Únicos?\s*\(CPF\)")
    tx_calc = (vt / vu) if vt > 0 and vu > 0 else None
    tx_used = tx_calc if (tx_calc and tx_calc>0) else DEFAULT_TX_UU
    origem = "Calculada" if tx_calc else "Fallback"
    return tx_calc, tx_used, vt, vu, origem

# ---------------- Filtros ----------------
st.markdown("### 🔎 Filtros de Cenário")
colS, colM, colSub = st.columns(3)

segmentos = sorted(df["SEGMENTO"].dropna().unique().tolist())
segmento = colS.selectbox("📊 Segmento", segmentos)

# meses legíveis
anomes_vals = sorted(df["ANOMES"].dropna().astype(int).unique().tolist())
meses_pt = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
labels = [f"{meses_pt[int(str(a)[4:])]}/{str(a)[:4]}" for a in anomes_vals]
lab2ano = dict(zip(labels, anomes_vals))
mes_sel = colM.selectbox("🗓️ Mês", labels, index=len(labels)-1)
anomes = lab2ano[mes_sel]

subcanais = sorted(df.loc[df["SEGMENTO"]==segmento, "__SUB__"].dropna().unique().tolist())
subcanal = colSub.selectbox("📌 Subcanal", subcanais)

df_scope = df[(df["SEGMENTO"]==segmento) & (df["__SUB__"]==subcanal) & (df["ANOMES"]==anomes)]
tribo = df_scope["NM_TORRE"].dropna().unique().tolist()[0] if not df_scope.empty else "Indefinido"

m1,m2,m3,m4 = st.columns(4)
m1.metric("Tribo", tribo)
m2.metric("Canal", tribo)
m3.metric("Segmento", segmento)
m4.metric("Subcanal", subcanal)

# ---------------- Entrada ----------------
st.markdown("---")
st.markdown("### ➗ Parâmetros de Simulação")
vol_trans = st.number_input("📥 Volume de Transações", min_value=0, value=10_000, step=1000)

# ---------------- Cálculos ---------------
if st.button("🚀 Calcular Ganhos Potenciais"):
    if df_scope.empty:
        st.warning("❌ Nenhum dado encontrado com os filtros selecionados.")
        st.stop()

    cr = CR_SEG.get(segmento, 0.50)
    tx_trn_acc = tx_trn_por_acesso(df_scope)
    ret = retido_72h(tribo)

    # Tx UU/CPF a partir dos MESMOS filtros
    tx_calc, tx_used, vol_trn_real, vol_uu_real, origem_tx = get_tx_uu_cpf(df, anomes, segmento, subcanal, tribo)

    vol_acessos = vol_trans / tx_trn_acc
    mau_cpf = vol_trans / tx_used
    cr_evit = vol_acessos * cr * ret
    cr_evit_floor = np.floor(cr_evit + 1e-9)

    # --------- Resultados (cards) --------
    st.markdown("---")
    st.markdown("### 📊 Resultados Detalhados (Fórmulas)")
    cA,cB,cC = st.columns(3)
    cA.metric("Volume de Transações", fmt_int(vol_trans))
    cB.metric("Taxa de Transação × Acesso", f"{tx_trn_acc:.2f}")
    cC.metric("% Ligação Direcionada Humano", f"{cr*100:.2f}%")
    cD,cE,cF = st.columns(3)
    cD.metric("Retido Digital 72h", f"{ret*100:.2f}%")
    cE.metric("Volume de Acessos", fmt_int(vol_acessos))
    cF.metric("MAU (CPF)", fmt_int(mau_cpf))

    # --------- Diagnóstico ---------------
    with st.expander("🔎 Diagnóstico de Premissas", expanded=False):
        st.markdown(f"""
**Segmento:** {segmento}  
**Subcanal:** {subcanal}  
**Tribo:** {tribo}  
**ANOMES usado:** {anomes}

| Item | Valor |
|---|---:|
| Volume Transações (7.1) | {fmt_int(vol_trn_real)} |
| Volume Usuários Únicos (4.1 - CPF) | {fmt_int(vol_uu_real)} |
| **TX_UU_CPF Calculada (Trans/Usuários)** | {("0.00" if not tx_calc else f"{tx_calc:.2f}")} |
| **TX_UU_CPF Usada no cálculo** | {tx_used:.2f} |
| Origem | {origem_tx} |
| CR Segmento | {cr*100:.2f}% |
| % Retido Aplicado | {ret*100:.2f}% |
        """, unsafe_allow_html=True)

    # --------- Card KPI ------------------
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

    # --------- Pareto (todos subcanais do segmento) ----------
    st.markdown("---")
    st.markdown("### 📄 Simulação - Todos os Subcanais (Pareto)")

    resultados=[]
    for sub in sorted(df.loc[df["SEGMENTO"]==segmento,"__SUB__"].dropna().unique()):
        di = df[(df["SEGMENTO"]==segmento) & (df["__SUB__"]==sub) & (df["ANOMES"]==anomes)]
        tribo_i = di["NM_TORRE"].dropna().unique().tolist()[0] if not di.empty else "Indefinido"

        tx_i = tx_trn_por_acesso(di)
        tx_calc_i, tx_used_i, _, _, _ = get_tx_uu_cpf(df, anomes, segmento, sub, tribo_i)
        ret_i = retido_72h(tribo_i)
        cr_i  = CR_SEG.get(segmento, 0.50)

        vol_acc_i = vol_trans / tx_i
        mau_i = vol_trans / tx_used_i
        est_i = np.floor((vol_acc_i * cr_i * ret_i) + 1e-9)

        resultados.append({
            "Subcanal": sub,
            "Tribo": tribo_i,
            "Transações / Acessos": round(tx_i,2),
            "% Lig. Humano": round(cr_i*100,2),
            "↓ % Retido": round(ret_i*100,2),
            "Volume de Acessos": int(vol_acc_i),
            "MAU (CPF)": int(mau_i),
            "Volume de CR Evitado": int(est_i),
        })

    df_lote = pd.DataFrame(resultados)
    st.dataframe(df_lote, use_container_width=False)

    # Pareto
    st.markdown("### 🔎 Análise de Pareto - Potencial de Ganho")
    df_p = df_lote.sort_values("Volume de CR Evitado", ascending=False).reset_index(drop=True)
    tot = df_p["Volume de CR Evitado"].sum()
    if tot>0:
        df_p["Acumulado"] = df_p["Volume de CR Evitado"].cumsum()
        df_p["Acumulado %"] = 100 * df_p["Acumulado"]/tot
    else:
        df_p["Acumulado"] = 0; df_p["Acumulado %"] = 0.0
    df_p["Cor"] = np.where(df_p["Acumulado %"]<=80, "crimson", "lightgray")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_p["Subcanal"], y=df_p["Volume de CR Evitado"],
                         name="Volume de CR Evitado", marker_color=df_p["Cor"]))
    fig.add_trace(go.Scatter(x=df_p["Subcanal"], y=df_p["Acumulado %"], name="Acumulado %",
                             mode="lines+markers", marker=dict(color="royalblue"), yaxis="y2"))
    fig.update_layout(
        title="📈 Pareto - Volume de CR Evitado",
        xaxis=dict(title="Subcanais"),
        yaxis=dict(title="Volume de CR Evitado"),
        yaxis2=dict(title="Acumulado %", overlaying="y", side="right", range=[0,100]),
        legend=dict(x=0.70, y=1.15, orientation="h"),
        bargap=0.2, margin=dict(l=10,r=10,t=60,b=80)
    )
    st.plotly_chart(fig, use_container_width=False)

    # Top 80 + insight
    df_top = df_p[df_p["Acumulado %"]<=80]
    st.markdown("### 🏆 Subcanais Prioritários (Top 80%)")
    st.dataframe(df_top[["Subcanal","Tribo","Volume de CR Evitado","Acumulado %"]], use_container_width=False)

    total_ev = int(df_lote["Volume de CR Evitado"].sum())
    nomes = ", ".join(df_top["Subcanal"].tolist())
    st.markdown(f"""**🧠 Insight Automático**

- Volume total estimado de **CR evitado**: **{fmt_int(total_ev)}**.  
- **{len(df_top)} subcanais** concentram **80%** do potencial: **{nomes}**.  
- **Ação:** priorize esses subcanais para maximizar impacto.
""")

    # Download Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as w:
        df_lote.to_excel(w, sheet_name="Resultados", index=False)
        df_top.to_excel(w, sheet_name="Top_80_Pareto", index=False)
    st.download_button("📥 Baixar Excel Completo", buffer.getvalue(),
                       file_name="simulacao_cr.xlsx",
                       mime="application/vnd.ms-excel")
