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


def test_dias_seguidos_com_erro():
    assert regras.dias_seguidos_com_erro(syncs((1, "error"), (25, "error"), (49, "success"), (73, "error"))) == 2
    assert regras.dias_seguidos_com_erro(syncs((1, "success"), (25, "error"))) == 0
    assert regras.dias_seguidos_com_erro(syncs()) == 0


def test_dias_seguidos_conta_dias_distintos_e_nao_syncs():
    # 3 syncs com erro em 2 dias (UTC) + um sucesso antes: reprocessamento no mesmo dia conta um dia só
    mesmo_dia = syncs((1, "error"), (2, "error"), (25, "error"), (49, "success"))
    assert regras.dias_seguidos_com_erro(mesmo_dia) == 2

    # dia sem nenhum sync no meio (sem sync há 2 dias entre os erros) não conta como dia com erro
    com_buraco = syncs((1, "error"), (73, "error"), (97, "success"))
    assert regras.dias_seguidos_com_erro(com_buraco) == 2


def test_dias_seguidos_usa_o_dia_utc_e_nao_o_de_brasilia():
    # 22h30 e 23h30 de Brasília do dia 22 são 01h30 e 02h30 UTC do dia 23: o mesmo dia UTC
    df = pd.DataFrame({"tenant": ["a", "a"], "id_sync": [2, 1], "status": ["error", "error"],
                       "created": [pd.Timestamp("2026-09-22 23:30", tz=FUSO), pd.Timestamp("2026-09-22 22:30", tz=FUSO)]})
    assert regras.dias_seguidos_com_erro(df) == 1


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


def _erros(*linhas):
    df = pd.DataFrame(linhas, columns=["tenant", "id_sync", "tipo_erro", "quantidade", "coletado_em"])
    df["coletado_em"] = pd.to_datetime(df["coletado_em"], utc=True)
    return df


def test_erro_predominante_do_ultimo_sync_escolhe_o_tipo_com_mais_ocorrencias():
    erros = _erros(
        ("alfa", 10, "email_duplicado", 3, "2026-10-06T10:00:00Z"),
        ("alfa", 10, "conflito_timespan", 8, "2026-10-06T10:00:00Z"),
        ("alfa", 10, "cpf_invalido", 1, "2026-10-06T10:00:00Z"),
    )
    r = regras.erro_predominante_do_ultimo_sync(erros, {"alfa": 10})
    assert r["alfa"]["tipo_erro_predominante"] == "conflito_timespan"
    assert r["alfa"]["quantidade_predominante"] == 8          # só desse tipo, não o total
    assert r["alfa"]["quantidade_total"] == 12
    assert r["alfa"]["coletado_em"] == pd.Timestamp("2026-10-06T10:00:00Z")


def test_erro_predominante_ignora_dados_de_sync_antigo():
    erros = _erros(
        ("alfa", 9, "cpf_invalido", 50, "2026-10-05T10:00:00Z"),            # sync anterior: não conta
        ("alfa", 10, "email_invalido", 2, "2026-10-06T10:00:00Z"),
        ("beta", 7, "cpf_invalido", 4, "2026-10-05T10:00:00Z"),            # último sync de beta é 8 (sem linhas)
    )
    r = regras.erro_predominante_do_ultimo_sync(erros, {"alfa": 10, "beta": 8, "gama": 1, "sem_sync": None})
    assert r["alfa"]["tipo_erro_predominante"] == "email_invalido"
    assert set(r) == {"alfa"}                                              # beta/gama/sem_sync: sem dado


def test_erro_predominante_empate_e_estavel():
    erros = _erros(
        ("alfa", 10, "pendente:change_salaries", 5, "2026-10-06T10:00:00Z"),
        ("alfa", 10, "conflito_timespan", 5, "2026-10-06T10:00:00Z"),
    )
    assert regras.erro_predominante_do_ultimo_sync(erros, {"alfa": 10})["alfa"]["tipo_erro_predominante"] == "conflito_timespan"
    assert regras.erro_predominante_do_ultimo_sync(_erros(), {"alfa": 10}) == {}


def test_status_atual_traz_o_id_do_ultimo_sync():
    historico = syncs((30, "error"), (2, "success"), tenant="alfa")       # o último sync (mais recente) é o de 2h
    df = regras.status_atual(historico, coletas("alfa", "novo"), AGORA).set_index("tenant")
    assert df.loc["alfa", "id_ultimo_sync"] == historico.sort_values("created").iloc[-1]["id_sync"]
    assert pd.isna(df.loc["novo", "id_ultimo_sync"])
