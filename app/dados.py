"""Leitura dos CSVs de histórico gerados pela coleta.

Duas fontes (sem dependência do Streamlit — a configuração vem de fora):
- GitHub (produção): baixa dados/*.csv do repositório PRIVADO da coleta pela API do
  GitHub, com um fine-grained token só de leitura. Configurada pela seção [dados]
  dos secrets: repo, token e, opcionalmente, branch e pasta.
- Pasta local (desenvolvimento): variável DADOS_PASTA ou ./dados.
"""

import io
import os
from pathlib import Path

import pandas as pd
import requests

# Horários como vêm do sistema (a API devolve UTC) — sem conversão para Brasília
FUSO = "UTC"
PASTA_DADOS = Path(os.environ.get("DADOS_PASTA", Path(__file__).resolve().parents[1] / "dados"))

ARQUIVO_HISTORICO = "historico_sync.csv"
ARQUIVO_COLETAS = "coletas.csv"
URL_CONTEUDO = "https://api.github.com/repos/{repo}/contents/{caminho}"
TIMEOUT = 30

COLUNAS_NUMERICAS = ["number_of_affected_items", "request_time", "total_time"]


class ErroFonteDados(Exception):
    """Falha ao obter os CSVs (mensagem pronta para mostrar na tela)."""


def descrever_fonte(fonte):
    if not fonte:
        return f"pasta local `{PASTA_DADOS}`"
    return f"GitHub `{fonte.get('repo')}` (branch `{fonte.get('branch', 'main')}`)"


def _baixar_do_github(fonte, nome_arquivo):
    if not fonte.get("repo") or not fonte.get("token"):
        raise ErroFonteDados("A seção [dados] dos secrets precisa de `repo` e `token`.")

    caminho = f"{fonte.get('pasta', 'dados')}/{nome_arquivo}"
    branch = fonte.get("branch", "main")
    try:
        resposta = requests.get(
            URL_CONTEUDO.format(repo=fonte["repo"], caminho=caminho),
            headers={
                "Authorization": f"Bearer {fonte['token']}",
                "Accept": "application/vnd.github.raw+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"ref": branch},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise ErroFonteDados(f"Não foi possível conectar ao GitHub ({type(e).__name__}).") from e

    if resposta.status_code in (401, 403):
        raise ErroFonteDados(f"O GitHub recusou o token (HTTP {resposta.status_code}): ele pode ter expirado "
                             "ou não ter permissão Contents: Read-only no repositório de dados.")
    if resposta.status_code == 404:
        raise ErroFonteDados(f"`{caminho}` não encontrado em `{fonte['repo']}` (branch `{branch}`). "
                             "Confira o nome do repositório e se o token tem acesso a ele.")
    if resposta.status_code != 200:
        raise ErroFonteDados(f"Erro inesperado do GitHub ao baixar `{caminho}` (HTTP {resposta.status_code}).")
    return io.StringIO(resposta.content.decode("utf-8"))


def _abrir(nome_arquivo, fonte):
    if fonte:
        return _baixar_do_github(fonte, nome_arquivo)
    caminho = PASTA_DADOS / nome_arquivo
    if not caminho.exists():
        raise ErroFonteDados(f"Arquivo `{caminho}` não encontrado. Configure a seção [dados] dos secrets "
                             "ou aponte DADOS_PASTA para a pasta dados/ do repositório da coleta.")
    return caminho


def _ler_csv(nome_arquivo, fonte):
    return pd.read_csv(_abrir(nome_arquivo, fonte), dtype=str, keep_default_na=False, encoding="utf-8")


def _para_data_hora(serie):
    return pd.to_datetime(serie, utc=True, format="ISO8601").dt.tz_convert(FUSO)


def carregar_historico(fonte=None):
    df = _ler_csv(ARQUIVO_HISTORICO, fonte)
    df["id_sync"] = df["id_sync"].astype("int64")
    for coluna in ("created", "modified", "primeira_coleta_em", "ultima_coleta_em"):
        df[coluna] = _para_data_hora(df[coluna])
    for coluna in COLUNAS_NUMERICAS:
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    # Dia do sync pelo horário do sistema (UTC), independente de como o CSV gravou a data
    df["data_sync"] = df["created"].dt.strftime("%Y-%m-%d")
    return df


def carregar_coletas(fonte=None):
    df = _ler_csv(ARQUIVO_COLETAS, fonte)
    df["executado_em"] = _para_data_hora(df["executado_em"])
    df["qtd_registros"] = pd.to_numeric(df["qtd_registros"], errors="coerce")
    return df
