import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import mapeamento  # noqa: E402
import regras  # noqa: E402


def test_arquivo_de_mapeamento_traz_so_responsaveis_validos():
    mapa = mapeamento.carregar()
    assert mapa and set(mapa.values()) <= {mapeamento.MINDSIGHT, mapeamento.CLIENTE}
    assert mapa["email_duplicado"] == mapeamento.CLIENTE and mapa["conflito_timespan"] == mapeamento.MINDSIGHT
    assert mapa["intervalo_invertido"] == mapeamento.MINDSIGHT


def test_tipo_fora_do_mapa_fica_a_definir(tmp_path):
    assert mapeamento.responsavel_do_tipo("tipo_novo", mapeamento.carregar()) == mapeamento.A_DEFINIR
    assert mapeamento.carregar(tmp_path / "nao_existe.toml") == {}
    arquivo = tmp_path / "m.toml"
    arquivo.write_text('[responsavel]\n"pendente:x" = "Cliente"\n', encoding="utf-8")
    assert mapeamento.carregar(arquivo) == {"pendente:x": "Cliente"}
