import pandas as pd, re, unicodedata

# ============ Normalização ============
def norm(x):
    if pd.isna(x): return ""
    s = str(x).replace("\u00A0", " ").replace("–", "-").replace("—", "-")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s.strip().lower())

# ============ Leitura ============
df = pd.read_excel("Tabela_Performance.xlsx", sheet_name="Tabela Performance")
df["VOL_KPI"] = pd.to_numeric(df["VOL_KPI"], errors="coerce").fillna(0)
df["ANOMES"] = pd.to_numeric(df["ANOMES"], errors="coerce")

# normaliza colunas
df["NM_KPI_NORM"] = df["NM_KPI"].map(norm)
df["NM_SUBCANAL_NORM"] = df["NM_SUBCANAL"].map(norm)

# ============ Parâmetros ============
anomes = 202508
subcanal = "app - res. hfc acesso rápido"

# ============ Filtro ============
filt = (df["ANOMES"] == anomes) & (df["NM_SUBCANAL_NORM"] == subcanal)
df_filt = df.loc[filt].copy()

print(f"Linhas encontradas: {len(df_filt)}")

# ============ Busca 7.1 e 4.1 ============
vol_71 = df_filt.loc[df_filt["NM_KPI_NORM"].str.contains("7.1") &
                     df_filt["NM_KPI_NORM"].str.contains("transa"), "VOL_KPI"].sum()

vol_41 = df_filt.loc[df_filt["NM_KPI_NORM"].str.contains("4.1") &
                     df_filt["NM_KPI_NORM"].str.contains("cpf"), "VOL_KPI"].sum()

print(f"Volume 7.1 - Transações: {vol_71:,.0f}")
print(f"Volume 4.1 - Usuários Únicos (CPF): {vol_41:,.0f}")
