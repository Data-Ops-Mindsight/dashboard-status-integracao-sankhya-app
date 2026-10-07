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


def erros_seguidos(syncs_tenant):
    """Quantidade de erros consecutivos a partir do sync mais recente."""
    contagem = 0
    for status in syncs_tenant["status"]:
        if status != "error":
            break
        contagem += 1
    return contagem


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
            "erros_seguidos": erros_seguidos(syncs),
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

