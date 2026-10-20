"""Leitura do relatório que `automacao/aplicador/relatorio_sheets.py`
publica no Google Sheets (abas "Resumo", "Correcoes", "Classificacao" e
"CoberturaCredenciais") -- indicadores da triagem/automação de correção,
migrados do antigo `dashboard/` do repositório de origem
(`triagem_integracao_sankhya`).

Sem dependência do Streamlit (mesma filosofia de `dados.py`, o módulo já
existente que lê os CSVs de status): a credencial vem de fora, como
parâmetro -- quem chama decide se ela vem da seção `[sheets]` dos secrets
(produção) ou de uma variável de ambiente (desenvolvimento local), sem
este módulo precisar saber a diferença.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, Optional

ESCOPOS_LEITURA = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

ID_PLANILHA_PADRAO = "1NQcosjqQDRD4PrMLgaRDQEz-iiNbl3M7K9Ih4Z6XwUc"
GID_ABA_RESUMO = 0
NOME_ABA_CORRECOES = "Correcoes"
NOME_ABA_CLASSIFICACAO = "Classificacao"
NOME_ABA_COBERTURA_CREDENCIAIS = "CoberturaCredenciais"


class ErroFonteDados(Exception):
    """Falha ao ler a planilha (mensagem pronta para mostrar na tela) --
    mesmo nome/papel de `dados.ErroFonteDados`, pro app tratar as duas
    fontes (CSVs de status e planilha de correções) da mesma forma."""


def _cliente_sheets(credenciais_json: str):
    """Import tardio (só quando de fato for ler)."""
    import gspread
    from google.oauth2.service_account import Credentials

    if not credenciais_json:
        raise ErroFonteDados(
            "Credencial do Google Sheets não configurada (seção [sheets] dos secrets, "
            "ou GOOGLE_SHEETS_CREDENTIALS_JSON no ambiente)."
        )
    try:
        info = json.loads(credenciais_json)
        credenciais = Credentials.from_service_account_info(info, scopes=ESCOPOS_LEITURA)
        return gspread.authorize(credenciais)
    except ErroFonteDados:
        raise
    except Exception as e:
        raise ErroFonteDados(f"Credencial do Google Sheets inválida: {e}") from e


def carregar_resumo(
    credenciais_json: str,
    spreadsheet_id: str = ID_PLANILHA_PADRAO,
    gid: int = GID_ABA_RESUMO,
) -> list[dict]:
    """Todas as linhas da aba "Resumo" -- uma por tenant processado em
    cada execução do pipeline. Lista vazia se a aba ainda não tiver dados."""
    cliente = _cliente_sheets(credenciais_json)
    try:
        planilha = cliente.open_by_key(spreadsheet_id)
        worksheet = planilha.get_worksheet_by_id(gid)
        return worksheet.get_all_records(numericise_ignore=["all"])  # "11,7" (pt-BR) viraria 117 na conversão automática
    except ErroFonteDados:
        raise
    except Exception as e:
        raise ErroFonteDados(f'Não foi possível ler a aba "Resumo": {e}') from e


def carregar_correcoes(
    credenciais_json: str,
    spreadsheet_id: str = ID_PLANILHA_PADRAO,
    nome_aba: str = NOME_ABA_CORRECOES,
) -> list[dict]:
    """Todas as linhas da aba "Correcoes" -- uma por (tenant, tipo_erro)
    em cada execução. Lista vazia se a aba ainda não existir."""
    import gspread

    cliente = _cliente_sheets(credenciais_json)
    try:
        planilha = cliente.open_by_key(spreadsheet_id)
        try:
            worksheet = planilha.worksheet(nome_aba)
        except gspread.WorksheetNotFound:
            return []
        return worksheet.get_all_records()
    except ErroFonteDados:
        raise
    except Exception as e:
        raise ErroFonteDados(f'Não foi possível ler a aba "Correcoes": {e}') from e


def carregar_classificacao_erros(
    credenciais_json: str,
    spreadsheet_id: str = ID_PLANILHA_PADRAO,
    nome_aba: str = NOME_ABA_CLASSIFICACAO,
) -> list[dict]:
    """Todas as linhas da aba "Classificacao" -- uma por (tenant, tipo_erro)
    DETECTADO em cada execução, ao contrário de `carregar_correcoes` (só o
    que foi automaticamente aplicado): inclui também o que caiu em
    revisao_manual (`multiplos_registros_ativos`, `transferencia_incompleta`,
    "pendente:X"). Lista vazia se a aba ainda não existir."""
    import gspread

    cliente = _cliente_sheets(credenciais_json)
    try:
        planilha = cliente.open_by_key(spreadsheet_id)
        try:
            worksheet = planilha.worksheet(nome_aba)
        except gspread.WorksheetNotFound:
            return []
        return worksheet.get_all_records()
    except ErroFonteDados:
        raise
    except Exception as e:
        raise ErroFonteDados(f'Não foi possível ler a aba "Classificacao": {e}') from e


def agregar_quantidade_por_chave(correcoes: Iterable[dict], chave: str) -> dict[str, int]:
    """Soma `quantidade` agrupando por um campo (`tenant` ou `tipo_erro`)."""
    totais: dict[str, int] = {}
    for linha in correcoes:
        valor_chave = linha.get(chave)
        quantidade = int(linha.get("quantidade") or 0)
        totais[valor_chave] = totais.get(valor_chave, 0) + quantidade
    return totais


def matriz_tenant_por_tipo_erro(correcoes: Iterable[dict]) -> dict[str, dict[str, int]]:
    """`{tenant: {tipo_erro: quantidade}}`."""
    matriz: dict[str, dict[str, int]] = {}
    for linha in correcoes:
        tenant = linha.get("tenant")
        tipo_erro = linha.get("tipo_erro")
        quantidade = int(linha.get("quantidade") or 0)
        matriz.setdefault(tenant, {})
        matriz[tenant][tipo_erro] = matriz[tenant].get(tipo_erro, 0) + quantidade
    return matriz


def _instante_execucao(valor) -> tuple:
    """Chave de ordenação de `data_hora_utc` (ISO 8601). Valores que não forem
    ISO válidos ficam por último na comparação, mas sem derrubar o cálculo."""
    texto = str(valor or "").strip()
    try:
        return (1, datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(timezone.utc), texto)
    except ValueError:
        return (0, datetime.min.replace(tzinfo=timezone.utc), texto)


def ultima_execucao_por_tenant(classificacao: Iterable[dict]) -> list[dict]:
    """Só as linhas da execução MAIS RECENTE de cada tenant (maior
    `data_hora_utc` daquele tenant). Cada execução do pipeline publica todas as
    linhas de um tenant com o mesmo `data_hora_utc`."""
    linhas = list(classificacao)
    mais_recente: dict = {}
    for linha in linhas:
        tenant = linha.get("tenant")
        instante = _instante_execucao(linha.get("data_hora_utc"))
        if tenant not in mais_recente or instante > mais_recente[tenant]:
            mais_recente[tenant] = instante
    return [l for l in linhas if _instante_execucao(l.get("data_hora_utc")) == mais_recente[l.get("tenant")]]


def erro_predominante_por_tenant(classificacao: Iterable[dict]) -> dict[str, dict]:
    """Pra cada tenant, soma `quantidade` por `tipo_erro` (todas as
    execuções publicadas na aba "Classificacao") e devolve o `tipo_erro`
    com mais ocorrências -- uma tag simples de "onde está a maior parte
    dos erros desse cliente", pra priorização (ver "Status atual" no
    dashboard). Usa `classificacao` (todo tipo_erro DETECTADO), não
    `correcoes` (só o automatizado), justamente pra não esconder os tipos
    que ainda caem em revisao_manual.

    `{tenant: {"tipo_erro_predominante": str, "quantidade_predominante": int,
    "quantidade_total": int, "data_execucao": str}}` -- tenant sem nenhuma linha não aparece.
    Para olhar só a execução mais recente, filtre antes com `ultima_execucao_por_tenant`."""
    classificacao = list(classificacao)
    matriz = matriz_tenant_por_tipo_erro(classificacao)
    resultado: dict[str, dict] = {}
    for tenant, contagem in matriz.items():
        if not contagem:
            continue
        tipo_predominante = max(contagem, key=contagem.get)
        resultado[tenant] = {
            "tipo_erro_predominante": tipo_predominante,
            "quantidade_predominante": contagem[tipo_predominante],
            "quantidade_total": sum(contagem.values()),
            "data_execucao": max((str(l.get("data_hora_utc") or "") for l in classificacao
                                  if l.get("tenant") == tenant), key=_instante_execucao, default=""),
        }
    return resultado


def geometria_do_conflito_por_tenant(classificacao: Iterable[dict]) -> dict[str, dict]:
    """Geometria predominante do `conflito_timespan` de cada tenant, na execução MAIS RECENTE da
    triagem (coluna `geometria` da aba "Classificacao", publicada pela triagem -- não vem da API
    do controle). `{tenant: {"geometria", "quantidade", "outras"}}`; "outras" é quantas geometrias
    diferentes existem além da predominante. Tenant sem conflito, ou cujas linhas ainda não têm
    geometria (execuções anteriores à coluna), não aparece."""
    contagem: dict[str, dict[str, int]] = {}
    for linha in ultima_execucao_por_tenant(classificacao):
        geometria = str(linha.get("geometria") or "").strip()
        if linha.get("tipo_erro") != "conflito_timespan" or not geometria:
            continue
        por_geometria = contagem.setdefault(linha.get("tenant"), {})
        por_geometria[geometria] = por_geometria.get(geometria, 0) + int(linha.get("quantidade") or 0)
    resultado = {}
    for tenant, por_geometria in contagem.items():
        predominante = min(por_geometria, key=lambda g: (-por_geometria[g], g))
        resultado[tenant] = {"geometria": predominante, "quantidade": por_geometria[predominante],
                             "outras": len(por_geometria) - 1}
    return resultado


def taxa_sucesso_por_tenant(resumo: Iterable[dict]) -> dict[str, dict]:
    """`{tenant: {"sucesso": N, "falha": M, "taxa_sucesso_pct": ...}}` --
    qualquer status diferente de "sucesso" conta como falha (falhou_login,
    sessao_expirou, limite_atingido, falhou_processamento)."""
    contagem: dict[str, dict[str, int]] = {}
    for linha in resumo:
        tenant = linha.get("tenant")
        status = linha.get("status")
        contagem.setdefault(tenant, {"sucesso": 0, "falha": 0})
        if status == "sucesso":
            contagem[tenant]["sucesso"] += 1
        else:
            contagem[tenant]["falha"] += 1

    resultado = {}
    for tenant, valores in contagem.items():
        total = valores["sucesso"] + valores["falha"]
        taxa = round(100 * valores["sucesso"] / total, 1) if total else 0.0
        resultado[tenant] = {**valores, "taxa_sucesso_pct": taxa}
    return resultado


def somente_aplicadas(linhas: Iterable[dict]) -> list[dict]:
    """Descarta as linhas de execuções de teste (`modo` = dry_run): só o que foi de fato aplicado conta.
    Linhas sem a coluna `modo` (anteriores a ela) são tratadas como aplicadas."""
    return [l for l in linhas if str(l.get("modo") or "aplicar").strip() == "aplicar"]


def numero(valor):
    """float de um valor da planilha, aceitando vírgula decimal ("11,7", locale pt-BR); None se vazio/inválido."""
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip().replace(",", "."))
    except ValueError:
        return None


def duracao_por_execucao_min(resumo: Iterable[dict]) -> dict[str, float]:
    """`{data_hora_utc: minutos}`, uma entrada por execução (o resumo tem uma linha por tenant em cada uma).

    Lê `duracao_execucao_min` (atual) ou, em linhas antigas, `duracao_execucao_s` / 60."""
    resultado: dict[str, float] = {}
    for linha in resumo:
        minutos = numero(linha.get("duracao_execucao_min"))
        if minutos is None:
            segundos = numero(linha.get("duracao_execucao_s"))
            minutos = None if segundos is None else segundos / 60
        if minutos is not None:
            resultado.setdefault(linha.get("data_hora_utc"), minutos)
    return resultado


def duracao_media_por_tenant(resumo: Iterable[dict]) -> dict[str, float]:
    """Média, EM MINUTOS, do tempo de cada tenant (`duracao_tenant_min`; em linhas antigas,
    `duracao_tenant_s` / 60), entre as execuções que têm esse valor registrado -- linhas sem o
    campo são ignoradas, nunca contam como zero (senão puxariam a média pra baixo artificialmente)."""
    somas: dict[str, float] = {}
    contagens: dict[str, int] = {}
    for linha in resumo:
        valor = numero(linha.get("duracao_tenant_min"))
        if valor is None:
            segundos = numero(linha.get("duracao_tenant_s"))
            valor = None if segundos is None else segundos / 60
        if valor is None:
            continue
        tenant = linha.get("tenant")
        somas[tenant] = somas.get(tenant, 0.0) + valor
        contagens[tenant] = contagens.get(tenant, 0) + 1
    return {tenant: round(somas[tenant] / contagens[tenant], 1) for tenant in somas}


def carregar_cobertura_credenciais(
    credenciais_json: str,
    spreadsheet_id: str = ID_PLANILHA_PADRAO,
    nome_aba: str = NOME_ABA_COBERTURA_CREDENCIAIS,
) -> Optional[dict]:
    """Snapshot publicado por `automacao/aplicador/pipeline.py`
    (`relatorio_sheets.publicar_cobertura_credenciais`) -- quais tenants
    ativos no HubSpot já têm credencial OAuth cadastrada
    (`tenants_credenciais.json`).

    Lê da planilha em vez de consultar o HubSpot/arquivo de credenciais
    diretamente -- funciona em qualquer lugar que já lê a planilha de
    indicadores (mesma credencial de `carregar_resumo`/`carregar_correcoes`),
    inclusive o deploy público deste app, que nunca teve acesso a
    `triagem_agente/` nem ao arquivo de credenciais (essa versão antiga,
    que consultava ao vivo, só funcionava rodando de dentro do monorepo --
    substituída por isso).

    `None` se a aba ainda não existir (nenhuma execução publicou ainda)."""
    import gspread

    cliente = _cliente_sheets(credenciais_json)
    try:
        planilha = cliente.open_by_key(spreadsheet_id)
        try:
            worksheet = planilha.worksheet(nome_aba)
        except gspread.WorksheetNotFound:
            return None
        linhas = worksheet.get_all_records()
    except ErroFonteDados:
        raise
    except Exception as e:
        raise ErroFonteDados(f'Não foi possível ler a aba "CoberturaCredenciais": {e}') from e

    if not linhas:
        return None

    com_credencial = [
        linha["tenant"] for linha in linhas if str(linha.get("tem_credencial")).strip().upper() == "TRUE"
    ]
    sem_credencial = [
        linha["tenant"] for linha in linhas if str(linha.get("tem_credencial")).strip().upper() != "TRUE"
    ]
    return {
        "total_ativos": len(linhas),
        "com_credencial": com_credencial,
        "sem_credencial": sem_credencial,
    }
