import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import regras  # noqa: E402

FUSO = "America/Sao_Paulo"
AGORA = pd.Timestamp("2026-09-23 12:00", tz=FUSO)


def syncs(*itens, tenant="alfa"):
    """itens: (horas atrás, status), do mais recente para o mais antigo."""
    linhas = [{
        "tenant": tenant,
        "id_sync": 100 - i,
        "status": status,
        "created": AGORA - pd.Timedelta(hours=horas),
        "number_of_affected_items": 10,
    } for i, (horas, status) in enumerate(itens)]
    df = pd.DataFrame(linhas, columns=["tenant", "id_sync", "status", "created", "number_of_affected_items"])
    df["created"] = pd.to_datetime(df["created"])
    return df


def coletas(*tenants, resultado="ok"):
    return pd.DataFrame({
        "executado_em": [AGORA] * len(tenants),
        "tenant": list(tenants),
        "resultado": [resultado] * len(tenants),
    })


@pytest.mark.parametrize("itens, esperado", [
    ([(2, "success")], regras.SUCESSO),
    ([(2, "error"), (26, "success")], regras.ERRO),
    ([(23, "pending"), (47, "success")], regras.PENDENTE),
    ([(25, "pending"), (49, "success")], regras.PENDENTE_PROBLEMA),
    ([(1, "pending"), (25, "pending")], regras.PENDENTE_PROBLEMA),
    ([(49, "success")], regras.SEM_SYNC),
    ([(49, "error")], regras.SEM_SYNC),
    ([], regras.SEM_SYNC),
])
def test_classificar(itens, esperado):
    assert regras.classificar(syncs(*itens), AGORA) == esperado


def test_taxa_erro_7d_ignora_pending_e_syncs_antigos():
    df = syncs((1, "error"), (25, "success"), (49, "pending"), (73, "error"), (24 * 8, "error"))
    # na janela: error, success, error (pending fora da conta; o de 8 dias fora da janela)
    assert regras.taxa_erro(df, AGORA) == pytest.approx(2 / 3)


def test_taxa_erro_sem_syncs_finalizados_e_nan():
    assert pd.isna(regras.taxa_erro(syncs((1, "pending")), AGORA))


def test_erros_seguidos():
    assert regras.erros_seguidos(syncs((1, "error"), (25, "error"), (49, "success"), (73, "error"))) == 2
    assert regras.erros_seguidos(syncs((1, "success"), (25, "error"))) == 0


def test_status_atual_so_tenants_da_ultima_coleta():
    historico = pd.concat([syncs((1, "error"), tenant="alfa"), syncs((1, "success"), tenant="antigo")])
    antiga = coletas("alfa", "antigo").assign(executado_em=AGORA - pd.Timedelta(hours=4))
    recente = pd.concat([coletas("alfa"), coletas("novo", resultado="erro_http")])

    df = regras.status_atual(historico, pd.concat([antiga, recente]), AGORA)

    assert sorted(df["tenant"]) == ["alfa", "novo"]
    novo = df.set_index("tenant").loc["novo"]
    assert novo["estado"] == regras.SEM_SYNC
    assert novo["falha_coleta"]


def test_status_atual_ordena_por_gravidade():
    historico = pd.concat([
        syncs((1, "success"), tenant="a_ok"),
        syncs((1, "error"), tenant="b_erro"),
        syncs((1, "pending"), tenant="c_pendente"),
    ])
    df = regras.status_atual(historico, coletas("a_ok", "b_erro", "c_pendente", "d_sem"), AGORA)
    assert df["tenant"].tolist() == ["d_sem", "b_erro", "c_pendente", "a_ok"]


def test_status_diario_pega_ultimo_sync_do_dia():
    df = syncs((1, "success"), (5, "error"))
    df["data_sync"] = "2026-09-23"
    diario = regras.status_diario(df)
    assert len(diario) == 1
    assert diario.iloc[0]["status"] == "success"


def test_taxa_erro_semanal_agrupa_de_segunda_a_domingo():
    df = pd.DataFrame({
        "tenant": ["alfa"] * 5,
        "id_sync": [1, 2, 3, 4, 5],
        # 21/09/2026 é segunda; 27/09 é domingo (mesma semana); 28/09 já é a semana seguinte
        "data_sync": ["2026-09-21", "2026-09-23", "2026-09-27", "2026-09-27", "2026-09-28"],
        "status": ["error", "success", "error", "pending", "success"],
    })
    semanal = regras.taxa_erro_semanal(df).set_index("semana")

    s1 = semanal.loc[pd.Timestamp("2026-09-21")]
    assert (s1["syncs"], s1["erros"], s1["finalizados"], s1["pendentes"]) == (4, 2, 3, 1)
    assert s1["taxa_erro"] == pytest.approx(2 / 3)
    assert semanal.loc[pd.Timestamp("2026-09-28"), "taxa_erro"] == 0


def test_taxa_erro_semanal_so_pendentes_e_nan():
    df = pd.DataFrame({"tenant": ["alfa"], "id_sync": [1], "data_sync": ["2026-09-21"], "status": ["pending"]})
    assert pd.isna(regras.taxa_erro_semanal(df).iloc[0]["taxa_erro"])
