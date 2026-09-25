import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import dados  # noqa: E402

CSV_HISTORICO = (
    "tenant,id_sync,action,status,stage,trigger_type,sync_type,number_of_affected_items,request_time,"
    "total_time,created,modified,data_sync,primeira_coleta_em,ultima_coleta_em\n"
    "alfa,1,sync_all,error,FINISHED,scheduled,incremental,10,1.5,2.5,2026-09-23T01:00:00-03:00,"
    "2026-09-23T01:05:00-03:00,2026-09-23,2026-09-23T08:00:00-03:00,2026-09-23T08:00:00-03:00\n"
)
CSV_COLETAS = "executado_em,tenant,resultado,http_status,qtd_registros\n2026-09-23T08:00:00-03:00,alfa,ok,200,1\n"
FONTE = {"repo": "org/repo-dados", "token": "token-de-teste", "branch": "main"}


class RespostaFalsa:
    def __init__(self, status_code, texto=""):
        self.status_code = status_code
        self.content = texto.encode("utf-8")


@pytest.fixture
def chamadas(monkeypatch):
    registro = []

    def get_falso(url, headers=None, params=None, timeout=None):
        registro.append({"url": url, "headers": headers, "params": params})
        return RespostaFalsa(200, CSV_HISTORICO if url.endswith("historico_sync.csv") else CSV_COLETAS)

    monkeypatch.setattr(dados.requests, "get", get_falso)
    return registro


def test_le_do_github_com_token_e_formato_raw(chamadas):
    historico = dados.carregar_historico(FONTE)
    coletas = dados.carregar_coletas(FONTE)

    assert len(historico) == 1 and historico.loc[0, "id_sync"] == 1
    assert historico.loc[0, "created"].tz is not None
    assert len(coletas) == 1

    chamada = chamadas[0]
    assert chamada["url"] == "https://api.github.com/repos/org/repo-dados/contents/dados/historico_sync.csv"
    assert chamada["headers"]["Authorization"] == "Bearer token-de-teste"
    assert chamada["headers"]["Accept"] == "application/vnd.github.raw+json"
    assert chamada["params"] == {"ref": "main"}


@pytest.mark.parametrize("status, trecho", [(401, "token"), (403, "token"), (404, "não encontrado"), (500, "HTTP 500")])
def test_erros_do_github_viram_mensagem_clara(monkeypatch, status, trecho):
    monkeypatch.setattr(dados.requests, "get", lambda *a, **k: RespostaFalsa(status))
    with pytest.raises(dados.ErroFonteDados, match=trecho):
        dados.carregar_historico(FONTE)


def test_falha_de_conexao(monkeypatch):
    def falha(*a, **k):
        raise requests.ConnectionError("sem rede")
    monkeypatch.setattr(dados.requests, "get", falha)
    with pytest.raises(dados.ErroFonteDados, match="conectar"):
        dados.carregar_coletas(FONTE)


def test_config_incompleta():
    with pytest.raises(dados.ErroFonteDados, match="repo"):
        dados.carregar_historico({"repo": "org/repo-dados"})


def test_pasta_local(tmp_path, monkeypatch):
    (tmp_path / "historico_sync.csv").write_text(CSV_HISTORICO, encoding="utf-8")
    monkeypatch.setattr(dados, "PASTA_DADOS", tmp_path)
    assert len(dados.carregar_historico()) == 1
    with pytest.raises(dados.ErroFonteDados, match="não encontrado"):
        dados.carregar_coletas()


def test_horarios_ficam_em_utc_como_no_sistema(tmp_path, monkeypatch):
    # sync às 23h30 UTC do dia 25 (em Brasília seriam 20h30): o dia e o horário seguem o sistema
    csv = CSV_HISTORICO.replace("2026-09-23T01:00:00-03:00", "2026-09-25T23:30:00Z")
    (tmp_path / "historico_sync.csv").write_text(csv, encoding="utf-8")
    monkeypatch.setattr(dados, "PASTA_DADOS", tmp_path)
    h = dados.carregar_historico()
    assert h.loc[0, "created"].strftime("%d/%m %H:%M") == "25/09 23:30"
    assert h.loc[0, "data_sync"] == "2026-09-25"
