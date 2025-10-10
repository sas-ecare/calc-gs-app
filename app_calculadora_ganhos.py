def tx_uu_cpf_dyn(df_all, segmento, subcanal, anomes, tribo):
    """Aplica filtros exatos e busca 7.1 e 4.1 em blocos separados"""
    base_filter = (
        (df_all["TP_META"].str.lower() == "real") &
        (df_all["ANOMES"] == anomes) &
        (df_all["SEGMENTO"] == segmento) &
        (df_all["NM_SUBCANAL"] == subcanal) &
        (df_all["NM_TORRE"] == tribo)
    )

    # Filtro de transações (7.1)
    df_trn = df_all[base_filter & df_all["NM_KPI"].str.contains("7.1 - Transações", case=False, na=False)]
    vt = df_trn["VOL_KPI"].sum()

    # Filtro de usuários únicos (4.1)
    df_usr = df_all[base_filter & df_all["NM_KPI"].str.contains("4.1 - Usuários Únicos (CPF)", case=False, na=False)]
    vu = df_usr["VOL_KPI"].sum()

    if vt > 0 and vu > 0:
        return (vt/vu, vt, vu, "NM_SUBCANAL", anomes)
    else:
        return (DEFAULT_TX_UU_CPF, vt, vu, "Fallback", anomes)
