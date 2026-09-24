import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from senha import credenciais_validas, gerar_hash, verificar_senha  # noqa: E402

SENHA = "uma-senha-bem-longa-123"


@pytest.fixture(scope="module")
def hash_senha():
    return gerar_hash(SENHA, iteracoes=1_000)  # poucas iterações só para o teste ser rápido


def test_senha_correta(hash_senha):
    assert verificar_senha(SENHA, hash_senha)


@pytest.mark.parametrize("tentativa", ["uma-senha-bem-longa-12", "UMA-SENHA-BEM-LONGA-123", "", " " + SENHA])
def test_senha_errada(hash_senha, tentativa):
    assert not verificar_senha(tentativa, hash_senha)


def test_hash_nao_contem_a_senha_e_usa_salt():
    h1, h2 = gerar_hash(SENHA, iteracoes=1_000), gerar_hash(SENHA, iteracoes=1_000)
    assert SENHA not in h1
    assert h1 != h2  # salt aleatório
    assert verificar_senha(SENHA, h1) and verificar_senha(SENHA, h2)


@pytest.mark.parametrize("hash_invalido", ["", "texto-qualquer", "md5$1$abc$def", "pbkdf2_sha256$x$y$z", None])
def test_hash_malformado_nao_libera(hash_invalido):
    assert not verificar_senha(SENHA, hash_invalido)


def test_credenciais(hash_senha):
    assert credenciais_validas("mindsight", SENHA, "mindsight", hash_senha)
    assert credenciais_validas(" Mindsight ", SENHA, "mindsight", hash_senha)
    assert not credenciais_validas("outro", SENHA, "mindsight", hash_senha)
    assert not credenciais_validas("mindsight", "errada", "mindsight", hash_senha)
    assert not credenciais_validas("", "", "mindsight", hash_senha)
    assert not credenciais_validas(None, None, "mindsight", hash_senha)
