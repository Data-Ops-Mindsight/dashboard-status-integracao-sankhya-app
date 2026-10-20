import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import componentes  # noqa: E402


def _linha(tenant, estado, **extra):
    base = {"tenant": tenant, "estado": estado, "falha_coleta": False, "itens": 100.0, "dias_seguidos_erro": 2,
            "ultimo_sync": pd.Timestamp("2026-10-06T10:00:00Z"), "horas_desde": 3.0,
            "ultimos_syncs": ["error", "error"]}
    return {**base, **extra}


def _html(monkeypatch, linhas):
    capturado = []
    monkeypatch.setattr(componentes, "_render", capturado.append)
    componentes.tabela_status(pd.DataFrame(linhas))
    return capturado[0]


def test_coluna_qtd_de_erros_aparece_antes_de_dias_seguidos_com_milhar_e_traco(monkeypatch):
    html = _html(monkeypatch, [
        _linha("alfa", "Erro", qtd_erros_ultimo_sync=1234.0),
        _linha("beta", "Sucesso", qtd_erros_ultimo_sync=None),
    ])
    nomes = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", html)
    assert nomes == ["Cliente", "Status", "Último sync", "Itens afetados", "Qtd. de erros", "Dias seguidos com erro",
                     "Últimos 7 syncs"]
    assert "<td class='ms-num'>1.234</td>" in html          # milhar com ponto
    assert html.count("<td class='ms-num'>—</td>") == 1       # cliente sem erro no último sync
    assert "title='Registros com erro no ÚLTIMO sync" in html  # dica no cabeçalho


def test_sem_a_coluna_de_dados_a_tabela_continua_igual(monkeypatch):
    html = _html(monkeypatch, [_linha("alfa", "Erro")])
    assert "Qtd. de erros" not in html and "Erro predominante" not in html


def test_subtitulo_com_a_geometria_do_conflito_timespan(monkeypatch):
    html = _html(monkeypatch, [
        _linha("alfa", "Erro", qtd_erros_ultimo_sync=5.0, tipo_erro_predominante="conflito_timespan",
               qtd_tipo_predominante=5.0,
               geometria_conflito={"geometria": "sobreposicao", "quantidade": 3, "outras": 1}),
        _linha("beta", "Erro", qtd_erros_ultimo_sync=2.0, tipo_erro_predominante="email_invalido",
               qtd_tipo_predominante=2.0, geometria_conflito=None),
    ])
    assert html.count("sobreposicao (3) +1") == 1               # só no conflito_timespan
    assert "email_invalido (2)</span></td>" in html             # sem subtítulo nos outros tipos


def test_cartoes_metricas_usam_a_cor_informada_ou_variam_pela_paleta(monkeypatch):
    capturado = []
    monkeypatch.setattr(componentes, "_render", capturado.append)
    componentes.cartoes_metricas([("a", 1, None), ("b", 2, "det"), ("c", 3, None, "#123456")])
    cores = re.findall(r"--cor:(#[0-9A-Fa-f]{6})", capturado[0])
    assert cores[0] != cores[1] and cores[2] == "#123456"


def _html_da_explicacao(monkeypatch):
    capturado = []
    monkeypatch.setattr(componentes, "_render", capturado.append)
    componentes.explicacao_das_colunas()
    return capturado[0]


def test_todas_as_colunas_tem_explicacao_no_cabecalho_e_no_quadro(monkeypatch):
    html = _html(monkeypatch, [_linha("alfa", "Erro", qtd_erros_ultimo_sync=3.0, tipo_erro_predominante="x",
                                      qtd_tipo_predominante=3.0)])
    cabecalhos = re.findall(r"<th(\s[^>]*)?>(.*?)</th>", html)
    assert len(cabecalhos) == 8
    assert all(" title='" in (atributos or "") for atributos, _ in cabecalhos)      # tooltip em TODAS as colunas
    explicacao_das_colunas_html = _html_da_explicacao(monkeypatch)
    assert all(f"<b>{nome}:</b>" in explicacao_das_colunas_html for _, nome in cabecalhos)


def test_caixas_de_explicacao_usam_sempre_o_roxo_da_marca(monkeypatch):
    capturado = []
    monkeypatch.setattr(componentes, "_render", capturado.append)
    componentes.intro("a")
    componentes.intro("b", "#D9531E")                 # a cor pedida é ignorada de propósito
    componentes.explicacao_das_colunas("#0E9AA7")
    assert all(f"--cor:{componentes.tema.ROXO}" in html for html in capturado) and len(capturado) == 3
