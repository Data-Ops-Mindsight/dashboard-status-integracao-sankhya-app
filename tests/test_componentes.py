import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import componentes  # noqa: E402


def _linha(tenant, estado, **extra):
    base = {"tenant": tenant, "estado": estado, "falha_coleta": False, "itens": 100.0, "erros_seguidos": 2,
            "ultimo_sync": pd.Timestamp("2026-10-06T10:00:00Z"), "horas_desde": 3.0,
            "ultimos_syncs": ["error", "error"]}
    return {**base, **extra}


def _html(monkeypatch, linhas):
    capturado = []
    monkeypatch.setattr(componentes, "_render", capturado.append)
    componentes.tabela_status(pd.DataFrame(linhas))
    return capturado[0]


def test_coluna_qtd_de_erros_aparece_antes_de_erros_seguidos_com_milhar_e_traco(monkeypatch):
    html = _html(monkeypatch, [
        _linha("alfa", "Erro", qtd_erros_ultimo_sync=1234.0),
        _linha("beta", "Sucesso", qtd_erros_ultimo_sync=None),
    ])
    nomes = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", html)
    assert nomes == ["Cliente", "Status", "Último sync", "Itens afetados", "Qtd. de erros", "Erros seguidos",
                     "Últimos 7 syncs"]
    assert "<td class='ms-num'>1.234</td>" in html          # milhar com ponto
    assert html.count("<td class='ms-num'>—</td>") == 1       # cliente sem erro no último sync
    assert "title='Registros com erro no ÚLTIMO sync" in html  # dica no cabeçalho


def test_sem_a_coluna_de_dados_a_tabela_continua_igual(monkeypatch):
    html = _html(monkeypatch, [_linha("alfa", "Erro")])
    assert "Qtd. de erros" not in html and "Erro predominante" not in html
