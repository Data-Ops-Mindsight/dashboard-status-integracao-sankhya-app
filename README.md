# Dashboard de status das integrações Sankhya

App Streamlit com três abas:

- **Status atual** e **Histórico** — status do sync Folha Sankhya por cliente: visão atual, mapa de
  calor (diário até 60 dias, semanal acima disso) e detalhe por cliente. Os dados **não ficam neste
  repositório**: são gerados por uma coleta automática em um repositório privado e lidos pelo app via
  API do GitHub, com um token só de leitura.
- **Correções aplicadas** — indicadores da triagem/automação de correção (erros corrigidos por
  cliente/tipo, taxa de sucesso, tempo de execução, cobertura de credenciais), migrados do antigo
  `dashboard/` do repositório `triagem_integracao_sankhya`. Lê direto do Google Sheets que
  `automacao/aplicador/relatorio_sheets.py` publica -- **não** depende do repositório privado da
  coleta.

## Rodar localmente

```bash
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # preencha [login], [dados] e [sheets]
streamlit run app/streamlit_app.py
```

- `[login]` — usuário e hash da senha do dashboard. Gere com `python gerar_senha.py` (a senha é
  digitada sem aparecer; só o hash é impresso).
- `[dados]` — repositório privado dos CSVs e um *fine-grained token* com acesso **somente** a ele
  e permissão **Contents: Read-only**.
- `[sheets]` — JSON de uma conta de serviço do Google Cloud com acesso de leitura na planilha de
  indicadores (aba "Correções aplicadas"). Sem isso, essa aba mostra um erro claro, mas as outras
  duas continuam funcionando normalmente.
- Sem `[dados]`, o app lê de uma pasta local (`DADOS_PASTA` ou `./dados`, ignorada pelo git).
- Sem `[login]`, o app não abre. Para desenvolver sem login: `DASHBOARD_SEM_LOGIN=1`.

A aba "Correções aplicadas" também calcula, ao vivo, a cobertura de credenciais
(`tenants_credenciais.json` × tenants ativos no HubSpot) -- só funciona quando este app roda de
dentro do monorepo `triagem_integracao_sankhya` (com `triagem_agente/` ao lado e
`HUBSPOT_ACCESS_TOKEN` no ambiente); no deploy público, separado deste repositório, a seção
aparece como indisponível, sem quebrar o resto do app.

## Deploy (Streamlit Community Cloud)

- Main file path: `app/streamlit_app.py` · Python 3.13
- Em **Advanced settings → Secrets**, cole os blocos `[login]`, `[dados]` e `[sheets]`.
- O token do GitHub tem validade: ao expirar, o app mostra "O GitHub recusou o token" — gere outro
  e atualize os secrets.

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/streamlit_app.py` | layout e filtros das três abas |
| `app/regras.py` | regras de status (último sync por cliente, pendente com problema, sem sync há mais de 7 dias, taxa de erro) |
| `app/dados.py` | leitura dos CSVs de status (GitHub ou pasta local) |
| `app/dados_correcoes.py` | leitura da planilha de indicadores de correção (Google Sheets) e cobertura de credenciais |
| `app/autenticacao.py`, `app/senha.py` | login por usuário e senha (hash PBKDF2, limite de tentativas) |
| `app/tema.py`, `app/componentes.py`, `.streamlit/config.toml` | identidade visual Mindsight 3.0 |

```bash
python -m pytest tests
```
