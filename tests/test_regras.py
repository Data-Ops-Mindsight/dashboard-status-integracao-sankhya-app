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
    ([(49, "success")], regras.SUCESSO),               # 2 dias sem sync ainda não conta
    ([(24 * 7 - 1, "success")], regras.SUCESSO),
    ([(24 * 7 + 1, "success")], regras.SEM_SYNC),      # mais de 7 dias
    ([(24 * 7 + 1, "error")], regras.SEM_SYNC),
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


def test_ordem_de_exibicao_tem_os_mesmos_estados():
    assert regras.ESTADOS_EXIBICAO == [regras.SUCESSO, regras.ERRO, regras.PENDENTE,
                                       regras.PENDENTE_PROBLEMA, regras.SEM_SYNC]
    assert sorted(regras.ESTADOS_EXIBICAO) == sorted(regras.ESTADOS)


def test_erro_predominante_so_quando_ultimo_sync_deu_erro():
    df = pd.DataFrame({
        "tenant": ["com_erro", "ok", "pendente", "sem_sync_com_erro", "nunca_sincronizou"],
        "status_ultimo": ["error", "success", "pending", "error", None],
        "tipo_erro_predominante": ["cpf_invalido"] * 5,
        "qtd_tipo_predominante": [3, 3, 3, 3, 3],
    })
    r = regras.so_quando_ultimo_sync_com_erro(df, ["tipo_erro_predominante", "qtd_tipo_predominante"]).set_index("tenant")

    assert r.loc["com_erro", "tipo_erro_predominante"] == "cpf_invalido"
    assert r.loc["sem_sync_com_erro", "qtd_tipo_predominante"] == 3   # último sync (antigo) foi erro
    for tenant in ("ok", "pendente", "nunca_sincronizou"):
        assert pd.isna(r.loc[tenant, "tipo_erro_predominante"])
        assert pd.isna(r.loc[tenant, "qtd_tipo_predominante"])
    assert df["tipo_erro_predominante"].tolist() == ["cpf_invalido"] * 5  # não altera o original


def test_agregar_por_dia_soma_e_preenche_dias_sem_registro():
    df = pd.DataFrame({
        "data_hora_utc": ["2026-09-28T10:00:00Z", "2026-09-28T18:30:00Z", "2026-09-30T02:00:00Z", "invalida"],
        "quantidade": [3, 2, 5, 99],
    })
    r = regras.agregar_por_dia(df, "data_hora_utc", "quantidade", "sum", preencher_dias_vazios=True)
    assert r["dia"].dt.strftime("%d/%m").tolist() == ["28/09", "29/09", "30/09"]
    assert r["valor"].tolist() == [5, 0, 5]          # 29/09 sem correção = 0; data inválida ignorada
    assert r["registros"].tolist() == [2, 0, 1]


def test_agregar_por_dia_media_mantem_dia_sem_execucao_sem_valor():
    df = pd.DataFrame({"data_hora_utc": ["2026-09-28T01:00:00Z", "2026-09-28T23:00:00Z", "2026-09-30T12:00:00Z"],
                       "duracao_min": [10, 20, 40]})
    r = regras.agregar_por_dia(df, "data_hora_utc", "duracao_min", "mean", preencher_dias_vazios=True)
    assert r["dia"].dt.strftime("%d/%m").tolist() == ["28/09", "29/09", "30/09"]
    assert r.loc[0, "valor"] == 15 and r.loc[2, "valor"] == 40
    assert pd.isna(r.loc[1, "valor"])                 # sem execução: sem barra (não é zero)
    assert r["registros"].tolist() == [2, 0, 1]

    sem_preencher = regras.agregar_por_dia(df, "data_hora_utc", "duracao_min", "mean")
    assert sem_preencher["dia"].dt.strftime("%d/%m").tolist() == ["28/09", "30/09"]


def test_agregar_por_dia_vazio():
    r = regras.agregar_por_dia(pd.DataFrame({"d": [], "v": []}), "d", "v")
    assert r.empty and list(r.columns) == ["dia", "valor", "registros"]
