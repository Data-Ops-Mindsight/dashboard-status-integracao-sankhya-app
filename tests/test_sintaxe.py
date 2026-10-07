import py_compile
from pathlib import Path

import pytest

ARQUIVOS = sorted((Path(__file__).resolve().parents[1] / "app").glob("*.py"))


@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda a: a.name)
def test_arquivo_do_app_compila(arquivo, tmp_path):
    """Pega erros de sintaxe em arquivos que os outros testes não importam (ex.: streamlit_app.py)."""
    py_compile.compile(str(arquivo), cfile=str(tmp_path / "saida.pyc"), doraise=True)
