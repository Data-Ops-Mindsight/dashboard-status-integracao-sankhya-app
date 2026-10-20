"""Regras de status e métricas do dashboard (sem dependência do Streamlit)."""

import pandas as pd

LIMITE_SEM_SYNC = pd.Timedelta(days=7)
LIMITE_PENDENTE = pd.Timedelta(hours=24)
JANELA_TAXA_ERRO = pd.Timedelta(days=7)
QTD_ULTIMOS_SYNCS = 7

SEM_SYNC = "7d sem sync"
ERRO = "Erro"
PENDENTE_PROBLEMA = "Pendente com problema"
PENDENTE = "Pendente"
SUCESSO = "Sucesso"

# Ordem de gravidade (usada para ordenar a tabela)
ESTADOS = [SEM_SYNC, ERRO, PENDENTE_PROBLEMA, PENDENTE, SUCESSO]
# Ordem de exibição dos cartões e dos filtros
ESTADOS_EXIBICAO = [SUCESSO, ERRO, PENDENTE, PENDENTE_PROBLEMA, SEM_SYNC]

RESULTADOS_FALHA = {"erro_http", "erro_conexao"}


def ultima_coleta(coletas):
    """Linhas da execução mais recente do script (uma por tenant monitorado)."""
    if coletas.empty:
        return coletas
    return coletas.loc[coletas["executado_em"] == coletas["executado_em"].max()]


def classificar(syncs_tenant, agora):
    """Estado de um tenant a partir dos seus syncs ordenados do mais recente para o mais antigo."""
    if syncs_tenant.empty:
        return SEM_SYNC

    ultimo = syncs_tenant.iloc[0]
    if agora - ultimo["created"] > LIMITE_SEM_SYNC:
        return SEM_SYNC
    if ultimo["status"] == "error":
        return ERRO
    if ultimo["status"] == "pending":
        anterior_pendente = len(syncs_tenant) > 1 and syncs_tenant.iloc[1]["status"] == "pending"
        if agora - ultimo["created"] > LIMITE_PENDENTE or anterior_pendente:
            return PENDENTE_PROBLEMA
        return PENDENTE
    return SUCESSO


def taxa_erro(syncs_tenant, agora, janela=JANELA_TAXA_ERRO):
    """Fração de syncs com erro na janela, entre os finalizados (pending não entra na conta)."""
    recentes = syncs_tenant.loc[syncs_tenant["created"] >= agora - janela]
    finalizados = recentes.loc[recentes["status"].isin(["success", "error"])]
    if finalizados.empty:
        return float("nan")
    return (finalizados["status"] == "error").mean()


def dias_seguidos_com_erro(syncs_tenant):
    """Quantos DIAS (UTC) distintos tem a sequência atual de syncs com erro, contada a partir do
    sync mais recente e parando no primeiro que não deu erro.

    Dois syncs com erro no mesmo dia (reprocessamento) contam um dia só; dia sem nenhum sync no meio
    da sequência não conta (não houve erro naquele dia, mas também não houve sucesso que a quebrasse).
    `syncs_tenant` vem ordenado do mais recente para o mais antigo."""
    dias = set()
    for status, criado in zip(syncs_tenant["status"], syncs_tenant["created"]):
        if status != "error":
            break
        dias.add(criado.tz_convert("UTC").date())
    return len(dias)


def ultimo_sucesso(syncs_tenant):
    sucessos = syncs_tenant.loc[syncs_tenant["status"] == "success", "created"]
    return sucessos.max() if not sucessos.empty else pd.NaT


def _ordenar_syncs(historico):
    return historico.sort_values(["tenant", "created", "id_sync"], ascending=[True, False, False])


def status_atual(historico, coletas, agora):
    """Uma linha por tenant monitorado na última coleta."""
    monitorados = ultima_coleta(coletas)[["tenant", "resultado"]]
    syncs_por_tenant = dict(tuple(_ordenar_syncs(historico).groupby("tenant")))
    vazio = historico.iloc[0:0]

    linhas = []
    for tenant, resultado in monitorados.itertuples(index=False):
        syncs = syncs_por_tenant.get(tenant, vazio)
        ultimo = syncs.iloc[0] if not syncs.empty else None
        linhas.append({
            "tenant": tenant,
            "id_ultimo_sync": int(ultimo["id_sync"]) if ultimo is not None else None,
            "estado": classificar(syncs, agora),
            "status_ultimo": ultimo["status"] if ultimo is not None else None,
            "ultimo_sync": ultimo["created"] if ultimo is not None else pd.NaT,
            "horas_desde": (agora - ultimo["created"]) / pd.Timedelta(hours=1) if ultimo is not None else float("nan"),
            "itens": ultimo["number_of_affected_items"] if ultimo is not None else float("nan"),
            "taxa_erro_7d": taxa_erro(syncs, agora),
            "dias_seguidos_erro": dias_seguidos_com_erro(syncs),
            "ultimo_sucesso": ultimo_sucesso(syncs),
            "ultimos_syncs": syncs["status"].head(QTD_ULTIMOS_SYNCS).tolist()[::-1],
            "falha_coleta": resultado in RESULTADOS_FALHA,
        })

    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["estado"] = pd.Categorical(df["estado"], categories=ESTADOS, ordered=True)
    return df.sort_values(["estado", "taxa_erro_7d", "tenant"], ascending=[True, False, True]).reset_index(drop=True)


def taxa_erro_semanal(historico):
    """Por tenant e semana (segunda a domingo): syncs, erros, pendentes e taxa de erro entre os finalizados."""
    df = historico.assign(
        semana=pd.to_datetime(historico["data_sync"]).dt.to_period("W-SUN").dt.start_time,
        erro=historico["status"] == "error",
        finalizado=historico["status"].isin(["success", "error"]),
        pendente=historico["status"] == "pending",
    )
    semanal = df.groupby(["tenant", "semana"], as_index=False).agg(
        syncs=("id_sync", "size"), erros=("erro", "sum"),
        finalizados=("finalizado", "sum"), pendentes=("pendente", "sum"),
    )
    semanal["taxa_erro"] = (semanal["erros"] / semanal["finalizados"]).where(semanal["finalizados"] > 0)
    return semanal


def status_diario(historico):
    """Status do último sync de cada tenant em cada dia (base do mapa de calor)."""
    ordenado = historico.sort_values(["tenant", "data_sync", "created", "id_sync"])
    return ordenado.groupby(["tenant", "data_sync"], as_index=False).last()


def so_quando_ultimo_sync_com_erro(df, colunas):
    """Esvazia `colunas` nas linhas cujo último sync não terminou em erro.

    Ex.: o erro predominante só faz sentido para quem está com erro agora —
    um cliente cujo último sync deu certo não deve mostrar um tipo de erro.
    """
    df = df.copy()
    com_erro = df["status_ultimo"] == "error"
    for coluna in colunas:
        df[coluna] = df[coluna].where(com_erro)  # where converte o tipo (int -> float/NaN) também no pandas 3
    return df


def agregar_por_dia(df, coluna_data, coluna_valor, agregacao="sum", preencher_dias_vazios=False):
    """Uma linha por dia (UTC): colunas `dia` (Timestamp à meia-noite), `valor` e `registros`.

    preencher_dias_vazios=True mantém no eixo os dias sem registro: com valor 0 numa soma
    (ex.: dia sem correção) e sem valor numa média (ex.: dia sem execução, sem barra).
    """
    datas = pd.to_datetime(df[coluna_data], errors="coerce", utc=True)
    base = pd.DataFrame({
        "dia": datas.dt.tz_localize(None).dt.normalize(),
        "valor": pd.to_numeric(df[coluna_valor], errors="coerce"),
    }).dropna(subset=["dia", "valor"])
    if base.empty:
        return pd.DataFrame(columns=["dia", "valor", "registros"])

    por_dia = base.groupby("dia").agg(valor=("valor", agregacao), registros=("valor", "size"))
    if preencher_dias_vazios:
        todos = pd.date_range(por_dia.index.min(), por_dia.index.max(), freq="D", name="dia")
        por_dia = por_dia.reindex(todos)
        por_dia["registros"] = por_dia["registros"].fillna(0).astype(int)
        if agregacao == "sum":
            por_dia["valor"] = por_dia["valor"].fillna(0)
    return por_dia.reset_index()


def agregar_por_dia_e_tipo(df, coluna_data, coluna_tipo, coluna_valor):
    """Soma por dia (UTC) e por tipo: colunas `dia`, `tipo` e `valor`, com todos os dias do período
    presentes (valor 0 onde não houve correção daquele tipo), para as barras empilhadas."""
    datas = pd.to_datetime(df[coluna_data], errors="coerce", utc=True)
    base = pd.DataFrame({
        "dia": datas.dt.tz_localize(None).dt.normalize(),
        "tipo": df[coluna_tipo].astype(str),
        "valor": pd.to_numeric(df[coluna_valor], errors="coerce"),
    }).dropna(subset=["dia", "valor"])
    if base.empty:
        return pd.DataFrame(columns=["dia", "tipo", "valor"])
    soma = base.groupby(["dia", "tipo"])["valor"].sum().unstack("tipo", fill_value=0)
    soma = soma.reindex(pd.date_range(soma.index.min(), soma.index.max(), freq="D", name="dia"), fill_value=0)
    return soma.stack().rename("valor").reset_index()


def erro_predominante_do_ultimo_sync(erros_sync, ids_ultimo_sync):
    """Por cliente, o tipo de erro com mais ocorrências no ÚLTIMO sync.

    `erros_sync`: DataFrame (tenant, id_sync, tipo_erro, quantidade, coletado_em) gerado pela coleta.
    `ids_ultimo_sync`: {tenant: id do último sync}. Só entram linhas desse sync — dado de um sync
    antigo nunca aparece. Empate: o tipo de nome menor (resultado estável).

    Retorna {tenant: {"tipo_erro_predominante", "quantidade_predominante", "quantidade_total",
    "coletado_em"}}; cliente sem registros no último sync não aparece.
    """
    resultado = {}
    if erros_sync.empty:
        return resultado
    for tenant, id_sync in ids_ultimo_sync.items():
        if id_sync is None or pd.isna(id_sync):
            continue
        linhas = erros_sync[(erros_sync["tenant"] == tenant) & (erros_sync["id_sync"] == id_sync)]
        if linhas.empty:
            continue
        melhor = linhas.sort_values(["quantidade", "tipo_erro"], ascending=[False, True]).iloc[0]
        resultado[tenant] = {
            "tipo_erro_predominante": melhor["tipo_erro"],
            "quantidade_predominante": int(melhor["quantidade"]),
            "quantidade_total": int(linhas["quantidade"].sum()),
            "coletado_em": linhas["coletado_em"].max(),
        }
    return resultado



# =============================================================================
# Aba "Erros": linhas de erro por período, tipo e cliente
# =============================================================================

GRANULARIDADES = ("Dia", "Semana", "Mês")


def _inicio_do_periodo(datas, granularidade):
    """Data (sem fuso) do início do dia/semana (segunda)/mês de cada data UTC."""
    dia = datas.dt.tz_localize(None).dt.normalize()
    if granularidade == "Semana":
        return dia - pd.to_timedelta(dia.dt.dayofweek, unit="D")
    if granularidade == "Mês":
        return dia.dt.to_period("M").dt.to_timestamp()
    return dia


def erros_por_sync(erros_sync, historico):
    """Linhas de erro (tenant, id_sync, tipo_erro, quantidade) com o dia (UTC) e o `created` do sync.

    Só entram contagens de syncs que estão no histórico; quantidade zero é descartada."""
    colunas = ["tenant", "id_sync", "tipo_erro", "quantidade", "created"]
    if erros_sync.empty or historico.empty:
        return pd.DataFrame(columns=colunas)
    syncs = historico[["tenant", "id_sync", "created"]]
    return erros_sync.loc[erros_sync["quantidade"] > 0, ["tenant", "id_sync", "tipo_erro", "quantidade"]].merge(
        syncs, on=["tenant", "id_sync"], how="inner")[colunas]


def erros_por_periodo_e_tipo(erros, granularidade="Dia"):
    """Soma de linhas de erro por período e tipo: colunas `dia` (início do período), `tipo` e `valor`."""
    if erros.empty:
        return pd.DataFrame(columns=["dia", "tipo", "valor"])
    base = pd.DataFrame({"dia": _inicio_do_periodo(erros["created"], granularidade),
                         "tipo": erros["tipo_erro"], "valor": erros["quantidade"]})
    return base.groupby(["dia", "tipo"], as_index=False)["valor"].sum()


def erros_e_registros_por_periodo(erros, historico, granularidade="Dia"):
    """Por período: `registros` (soma de number_of_data_items dos syncs), `erros` (linhas de erro) e `pct`
    (erros ÷ registros, em %; vazio quando não há registros). Períodos sem sync não aparecem."""
    if historico.empty:
        return pd.DataFrame(columns=["dia", "registros", "erros", "pct"])
    registros = (historico.assign(dia=_inicio_do_periodo(historico["created"], granularidade))
                 .groupby("dia")["number_of_data_items"].sum(min_count=1).fillna(0).rename("registros"))
    linhas = (erros.assign(dia=_inicio_do_periodo(erros["created"], granularidade)).groupby("dia")["quantidade"].sum()
              if not erros.empty else pd.Series(dtype="int64")).rename("erros")
    resultado = pd.concat([registros, linhas], axis=1).fillna(0).reset_index()
    resultado["erros"] = resultado["erros"].astype("int64")
    resultado["pct"] = (100 * resultado["erros"] / resultado["registros"]).where(resultado["registros"] > 0)
    return resultado.sort_values("dia").reset_index(drop=True)


def erros_por_cliente(erros, historico):
    """Por cliente: `registros`, `linhas` de erro, `pct` e `syncs_com_erro`; do cliente com mais erros ao menor."""
    registros = historico.groupby("tenant")["number_of_data_items"].sum(min_count=1).fillna(0).rename("registros")
    if erros.empty:
        return pd.DataFrame(columns=["tenant", "registros", "linhas", "pct", "syncs_com_erro"])
    agrupado = erros.groupby("tenant").agg(
        linhas=("quantidade", "sum"), syncs_com_erro=("id_sync", "nunique"))
    resultado = agrupado.join(registros, how="left").fillna({"registros": 0}).reset_index()
    resultado["pct"] = (100 * resultado["linhas"] / resultado["registros"]).where(resultado["registros"] > 0)
    colunas = ["tenant", "registros", "linhas", "pct", "syncs_com_erro"]
    if "responsavel" in erros.columns:  # quantas dessas linhas cabem a cada responsável
        por_responsavel = erros.pivot_table(index="tenant", columns="responsavel", values="quantidade",
                                            aggfunc="sum", fill_value=0)
        for responsavel in ("Mindsight", "Cliente"):
            resultado[f"linhas_{responsavel.lower()}"] = resultado["tenant"].map(
                por_responsavel[responsavel] if responsavel in por_responsavel else {}).fillna(0).astype("int64")
            colunas.append(f"linhas_{responsavel.lower()}")
    return (resultado[colunas].sort_values(["linhas", "tenant"], ascending=[False, True]).reset_index(drop=True))


def resolucao_do_cliente(correcoes, erros_cliente, inicio, fim):
    """Quanto da automação resolveu dos erros de UM cliente no período [inicio, fim] (datas UTC).

    `correcoes`: DataFrame do cliente (data_hora_utc, tipo_erro, quantidade), só execuções aplicadas.
    `erros_cliente`: linhas de erro do cliente (tipo_erro, quantidade, created), de `erros_por_sync`.
    Retorna {"corrigidos", "total", "por_tipo"}; `por_tipo` tem tipo, corrigidos e erros (linhas de erro)."""
    if correcoes is not None and len(correcoes):
        dia = pd.to_datetime(correcoes["data_hora_utc"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
        no_periodo = correcoes.loc[(dia >= pd.Timestamp(inicio)) & (dia <= pd.Timestamp(fim))]
        corrigidos = pd.to_numeric(no_periodo["quantidade"], errors="coerce").groupby(no_periodo["tipo_erro"]).sum()
    else:
        corrigidos = pd.Series(dtype="float64")
    if len(erros_cliente):
        dia_erro = erros_cliente["created"].dt.tz_localize(None).dt.normalize()
        erros = erros_cliente.loc[(dia_erro >= pd.Timestamp(inicio)) & (dia_erro <= pd.Timestamp(fim))]
        linhas = erros.groupby("tipo_erro")["quantidade"].sum()
    else:
        linhas = pd.Series(dtype="int64")
    por_tipo = (pd.concat([corrigidos.rename("corrigidos"), linhas.rename("erros")], axis=1).fillna(0).astype("int64")
                .rename_axis("tipo").reset_index())
    por_tipo = por_tipo.sort_values(["erros", "corrigidos", "tipo"], ascending=[False, False, True]).reset_index(drop=True)
    return {"corrigidos": int(por_tipo["corrigidos"].sum()), "total": int(por_tipo["erros"].sum()), "por_tipo": por_tipo}
