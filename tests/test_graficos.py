import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import graficos  # noqa: E402
import tema  # noqa: E402


def test_cores_por_categoria_sao_estaveis_e_distintas():
    cores = graficos.cores_por_categoria(["b", "a", "c", "a"])
    assert list(cores) == ["a", "b", "c"] and len(set(cores.values())) == 3
    assert graficos.cores_por_categoria(["c", "b", "a"]) == cores          # independe da ordem de chegada
    assert all(c in tema.PALETA_CATEGORIAS for c in cores.values())


def test_graficos_geram_especificacao_valida():
    dia = pd.DataFrame({"dia": pd.to_datetime(["2026-10-16", "2026-10-17"]), "valor": [3.0, 5.0], "registros": [1, 2]})
    graficos.barras_por_dia(dia, "Correções", tema.ROXO).to_dict()
    por_tipo = pd.DataFrame({"dia": pd.to_datetime(["2026-10-16", "2026-10-16"]), "tipo": ["a", "b"], "valor": [1, 2]})
    graficos.barras_por_dia_e_tipo(por_tipo, graficos.cores_por_categoria(["a", "b"])).to_dict()
    serie = pd.Series({"x": 3, "y": 5})
    graficos.barras_horizontais(serie, "Correções", cor=tema.ROXO).to_dict()
    graficos.barras_horizontais(serie, "Correções", cores=graficos.cores_por_categoria(serie.index)).to_dict()
    taxas = pd.DataFrame({"sucesso": [2, 1], "falha": [0, 1]}, index=["x", "y"])
    graficos.sucesso_falha_por_tenant(taxas).to_dict()
    graficos.barra_de_cobertura(3, 5, tema.ACENTO_CREDENCIAIS).to_dict()


def test_grafico_de_pct_por_periodo_e_empilhado_mensal_geram_especificacao_valida():
    df = pd.DataFrame({"dia": pd.to_datetime(["2026-10-01", "2026-11-01"]), "registros": [100.0, 0.0],
                       "erros": [5, 0], "pct": [5.0, float("nan")]})
    graficos.linha_pct_por_periodo(df, tema.ACENTO_ERROS, "%m/%Y").to_dict()
    por_tipo = pd.DataFrame({"dia": pd.to_datetime(["2026-10-01"]), "tipo": ["a"], "valor": [3]})
    spec = graficos.barras_por_dia_e_tipo(por_tipo, {"a": "#7321E8"}, "%m/%Y", "Linhas de erro").to_dict()
    assert "Linhas de erro" in str(spec)


def test_so_os_tipos_de_maior_volume_ganham_cor_e_o_resto_vira_outros():
    volume = pd.Series({f"t{i}": 100 - i for i in range(12)})
    cores, destaque = graficos.cores_em_destaque(volume, n=7)
    assert destaque == [f"t{i}" for i in range(7)]
    assert len({cores[t] for t in destaque}) == 7                       # nenhuma cor repetida entre os destacados
    assert {cores[f"t{i}"] for i in range(7, 12)} == {tema.COR_OUTROS}
    df = pd.DataFrame({"dia": pd.to_datetime(["2026-10-01"] * 4), "tipo": ["t0", "t8", "t9", "t0"], "valor": [5, 2, 3, 1]})
    agrupado = graficos.agrupar_em_outros(df, "tipo", destaque)
    assert {(r.tipo, r.valor) for r in agrupado.itertuples()} == {("t0", 6), (graficos.OUTROS, 5)}
