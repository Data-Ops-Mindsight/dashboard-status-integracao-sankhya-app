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
