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
        return worksheet.get_all_records()
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


def erro_predominante_por_tenant(classificacao: Iterable[dict]) -> dict[str, dict]:
    """Pra cada tenant, soma `quantidade` por `tipo_erro` (todas as
    execuções publicadas na aba "Classificacao") e devolve o `tipo_erro`
    com mais ocorrências -- uma tag simples de "onde está a maior parte
    dos erros desse cliente", pra priorização (ver "Status atual" no
    dashboard). Usa `classificacao` (todo tipo_erro DETECTADO), não
    `correcoes` (só o automatizado), justamente pra não esconder os tipos
    que ainda caem em revisao_manual.

    `{tenant: {"tipo_erro_predominante": str, "quantidade_predominante": int,
    "quantidade_total": int}}` -- tenant sem nenhuma linha não aparece."""
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
        }
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


def duracao_media_por_tenant(resumo: Iterable[dict]) -> dict[str, float]:
    """Média de `duracao_tenant_s` por tenant, entre as execuções que têm
    esse valor registrado -- linhas sem o campo são ignoradas, nunca
    contam como zero (senão puxariam a média pra baixo artificialmente)."""
    somas: dict[str, float] = {}
    contagens: dict[str, int] = {}
    for linha in resumo:
        valor = linha.get("duracao_tenant_s")
        if valor in (None, ""):
            continue
        tenant = linha.get("tenant")
        somas[tenant] = somas.get(tenant, 0.0) + float(valor)
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
