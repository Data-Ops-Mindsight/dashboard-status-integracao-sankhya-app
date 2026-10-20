"""Responsável por agir em cada tipo de erro (arquivo mapeamento_erros.toml)."""

import tomllib
from pathlib import Path

ARQUIVO = Path(__file__).with_name("mapeamento_erros.toml")
MINDSIGHT, CLIENTE, A_DEFINIR = "Mindsight", "Cliente", "A definir"
RESPONSAVEIS = (MINDSIGHT, CLIENTE, A_DEFINIR)


def carregar(caminho=ARQUIVO):
    """{tipo_erro: responsável}; arquivo ausente = tudo "A definir"."""
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    dados = tomllib.loads(caminho.read_text(encoding="utf-8")).get("responsavel", {})
    return {str(tipo): str(responsavel) for tipo, responsavel in dados.items()}


def responsavel_do_tipo(tipo, mapa):
    return mapa.get(tipo, A_DEFINIR)
