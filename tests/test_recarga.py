import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import recarga  # noqa: E402


@pytest.fixture
def pacote(tmp_path, monkeypatch):
    """Dois módulos temporários: `base_tmp` e `usa_base_tmp` (que faz `from base_tmp import valor`)."""
    (tmp_path / "base_tmp.py").write_text("def valor():\n    return 1\n", encoding="utf-8")
    (tmp_path / "usa_base_tmp.py").write_text("from base_tmp import valor\n\ndef dobro():\n    return valor() * 2\n",
                                              encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for nome in ("base_tmp", "usa_base_tmp"):
        sys.modules.pop(nome, None)


NOMES = ["base_tmp", "usa_base_tmp"]


def test_sem_mudanca_nao_recarrega(pacote):
    import usa_base_tmp  # noqa: F401
    recarga.registrar_assinaturas(NOMES)
    assert recarga.recarregar_modulos_alterados(NOMES) == []


def test_arquivo_alterado_recarrega_todos_em_ordem(pacote):
    import base_tmp
    import usa_base_tmp
    recarga.registrar_assinaturas(NOMES)
    assert usa_base_tmp.dobro() == 2

    # "deploy": muda o módulo base e cria uma função nova (o caso do AttributeError)
    (pacote / "base_tmp.py").write_text("def valor():\n    return 10\n\ndef nova():\n    return 'ok'\n", encoding="utf-8")

    assert recarga.recarregar_modulos_alterados(NOMES) == NOMES
    assert base_tmp.nova() == "ok"                 # função nova disponível sem reiniciar o processo
    assert usa_base_tmp.dobro() == 20              # dependente também recarregado (não ficou com a função antiga)
    assert recarga.recarregar_modulos_alterados(NOMES) == []   # assinatura atualizada


def test_modulo_carregado_antes_da_protecao_conta_como_desatualizado(pacote):
    import base_tmp  # carregado sem assinatura (como no processo antigo do Streamlit Cloud)
    assert not hasattr(base_tmp, recarga.ATRIBUTO_ASSINATURA)
    assert recarga.recarregar_modulos_alterados(NOMES) == ["base_tmp"]   # usa_base_tmp ainda não carregado
