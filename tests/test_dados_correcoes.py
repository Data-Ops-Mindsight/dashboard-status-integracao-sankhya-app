"""Testes das funções puras de agregação de dados_correcoes.py -- sem
rede, sem credencial real (a leitura do Sheets em si e a consulta ao
HubSpot não são cobertas por testes unitários, mesma convenção de
tests/test_dados.py).

Dados fictícios (nenhum tenant/e-mail real).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import dados_correcoes  # noqa: E402

# Só os testes de carregar_cobertura_credenciais precisam disto -- import
# de triagem_agente.io.cliente_hubspot só funciona quando este app roda de
# dentro do monorepo (dois níveis acima de tests/), não no repositório
# público separado (ver docstring de carregar_cobertura_credenciais).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_agregar_quantidade_por_chave_soma_por_tenant():
    correcoes = [
        {"tenant": "acme", "tipo_erro": "email_duplicado", "quantidade": 3},
        {"tenant": "acme", "tipo_erro": "email_invalido", "quantidade": 1},
        {"tenant": "outra", "tipo_erro": "email_duplicado", "quantidade": 5},
    ]

    assert dados_correcoes.agregar_quantidade_por_chave(correcoes, "tenant") == {"acme": 4, "outra": 5}


def test_agregar_quantidade_por_chave_soma_por_tipo_erro():
    correcoes = [
        {"tenant": "acme", "tipo_erro": "email_duplicado", "quantidade": 3},
        {"tenant": "outra", "tipo_erro": "email_duplicado", "quantidade": 5},
        {"tenant": "outra", "tipo_erro": "email_invalido", "quantidade": 2},
    ]

    assert dados_correcoes.agregar_quantidade_por_chave(correcoes, "tipo_erro") == {
        "email_duplicado": 8,
        "email_invalido": 2,
    }


def test_agregar_quantidade_por_chave_lista_vazia():
    assert dados_correcoes.agregar_quantidade_por_chave([], "tenant") == {}


def test_matriz_tenant_por_tipo_erro():
    correcoes = [
        {"tenant": "acme", "tipo_erro": "email_duplicado", "quantidade": 3},
        {"tenant": "acme", "tipo_erro": "email_invalido", "quantidade": 1},
        {"tenant": "acme", "tipo_erro": "email_duplicado", "quantidade": 2},  # 2a execução, mesmo par
        {"tenant": "outra", "tipo_erro": "email_duplicado", "quantidade": 5},
    ]

    matriz = dados_correcoes.matriz_tenant_por_tipo_erro(correcoes)

    assert matriz == {
        "acme": {"email_duplicado": 5, "email_invalido": 1},
        "outra": {"email_duplicado": 5},
    }


def test_erro_predominante_por_tenant_escolhe_o_tipo_com_mais_ocorrencias():
    classificacao = [
        {"tenant": "acme", "tipo_erro": "email_invalido", "quantidade": 3},
        {"tenant": "acme", "tipo_erro": "multiplos_registros_ativos", "quantidade": 7},
        {"tenant": "acme", "tipo_erro": "multiplos_registros_ativos", "quantidade": 2},  # 2a execução
        {"tenant": "outra", "tipo_erro": "cpf_invalido", "quantidade": 1},
    ]

    predominantes = dados_correcoes.erro_predominante_por_tenant(classificacao)

    assert predominantes == {
        "acme": {"tipo_erro_predominante": "multiplos_registros_ativos", "quantidade_predominante": 9, "quantidade_total": 12},
        "outra": {"tipo_erro_predominante": "cpf_invalido", "quantidade_predominante": 1, "quantidade_total": 1},
    }


def test_erro_predominante_por_tenant_lista_vazia():
    assert dados_correcoes.erro_predominante_por_tenant([]) == {}


def test_carregar_classificacao_erros_aba_inexistente_devolve_lista_vazia(monkeypatch):
    import gspread

    class _PlanilhaFake:
        def worksheet(self, nome):
            raise gspread.WorksheetNotFound(nome)

    class _ClienteFake:
        def open_by_key(self, spreadsheet_id):
            return _PlanilhaFake()

    monkeypatch.setattr(dados_correcoes, "_cliente_sheets", lambda credenciais_json: _ClienteFake())

    assert dados_correcoes.carregar_classificacao_erros("fake-credencial") == []


def test_taxa_sucesso_por_tenant_conta_qualquer_status_diferente_de_sucesso_como_falha():
    resumo = [
        {"tenant": "acme", "status": "sucesso"},
        {"tenant": "acme", "status": "sucesso"},
        {"tenant": "acme", "status": "falhou_login"},
        {"tenant": "outra", "status": "falhou_processamento"},
        {"tenant": "outra", "status": "sessao_expirou"},
    ]

    taxas = dados_correcoes.taxa_sucesso_por_tenant(resumo)

    assert taxas == {
        "acme": {"sucesso": 2, "falha": 1, "taxa_sucesso_pct": 66.7},
        "outra": {"sucesso": 0, "falha": 2, "taxa_sucesso_pct": 0.0},
    }


def test_taxa_sucesso_por_tenant_lista_vazia():
    assert dados_correcoes.taxa_sucesso_por_tenant([]) == {}


def test_duracao_media_por_tenant_calcula_media_entre_execucoes():
    resumo = [
        {"tenant": "acme", "duracao_tenant_s": 10.0},
        {"tenant": "acme", "duracao_tenant_s": 20.0},
        {"tenant": "outra", "duracao_tenant_s": 5.0},
    ]

    assert dados_correcoes.duracao_media_por_tenant(resumo) == {"acme": 15.0, "outra": 5.0}


def test_duracao_media_por_tenant_ignora_linhas_sem_o_campo():
    """Linhas publicadas antes de duracao_tenant_s existir não podem
    contar como zero -- puxaria a média pra baixo sem motivo."""
    resumo = [
        {"tenant": "acme", "duracao_tenant_s": 10.0},
        {"tenant": "acme"},  # execução antiga, sem o campo
        {"tenant": "acme", "duracao_tenant_s": ""},  # célula vazia no Sheets
    ]

    assert dados_correcoes.duracao_media_por_tenant(resumo) == {"acme": 10.0}


def test_duracao_media_por_tenant_lista_vazia():
    assert dados_correcoes.duracao_media_por_tenant([]) == {}


def test_cliente_sheets_sem_credencial_levanta_erro_claro():
    try:
        dados_correcoes._cliente_sheets("")
        assert False, "deveria ter levantado ErroFonteDados"
    except dados_correcoes.ErroFonteDados as erro:
        assert "sheets" in str(erro) or "GOOGLE_SHEETS_CREDENTIALS_JSON" in str(erro)


def test_carregar_correcoes_aba_inexistente_devolve_lista_vazia(monkeypatch):
    import gspread

    class _PlanilhaFake:
        def worksheet(self, nome):
            raise gspread.WorksheetNotFound(nome)

    class _ClienteFake:
        def open_by_key(self, spreadsheet_id):
            return _PlanilhaFake()

    monkeypatch.setattr(dados_correcoes, "_cliente_sheets", lambda credenciais_json: _ClienteFake())

    assert dados_correcoes.carregar_correcoes("fake-credencial") == []


def test_carregar_cobertura_credenciais_cruza_hubspot_com_arquivo(monkeypatch, tmp_path):
    caminho = tmp_path / "tenants_credenciais.json"
    caminho.write_text('{"acme": {"client_id": "x", "client_secret": "y"}}', encoding="utf-8")

    import triagem_agente.io.cliente_hubspot as cliente_hubspot

    monkeypatch.setattr(cliente_hubspot, "listar_tenants_com_integracao_ativa", lambda: ["acme", "outra", "terceira"])

    cobertura = dados_correcoes.carregar_cobertura_credenciais(caminho_credenciais=str(caminho))

    assert cobertura == {
        "total_ativos": 3,
        "com_credencial": ["acme"],
        "sem_credencial": ["outra", "terceira"],
    }


def test_carregar_cobertura_credenciais_sem_arquivo_trata_como_ninguem_tem_credencial(monkeypatch, tmp_path):
    caminho_inexistente = tmp_path / "nao_existe.json"

    import triagem_agente.io.cliente_hubspot as cliente_hubspot

    monkeypatch.setattr(cliente_hubspot, "listar_tenants_com_integracao_ativa", lambda: ["acme"])

    cobertura = dados_correcoes.carregar_cobertura_credenciais(caminho_credenciais=str(caminho_inexistente))

    assert cobertura == {"total_ativos": 1, "com_credencial": [], "sem_credencial": ["acme"]}
