# Dashboard de status das integrações Sankhya

App Streamlit que mostra o status do sync Folha Sankhya por cliente: visão atual, mapa de calor
(diário até 60 dias, semanal acima disso) e detalhe por cliente.

Os dados **não ficam neste repositório**: são gerados por uma coleta automática em um repositório
privado e lidos pelo app via API do GitHub, com um token só de leitura.

## Rodar localmente

```bash
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # preencha [login] e [dados]
streamlit run app/streamlit_app.py
```

- `[login]` — usuário e hash da senha do dashboard. Gere com `python gerar_senha.py` (a senha é
  digitada sem aparecer; só o hash é impresso).
- `[dados]` — repositório privado dos CSVs e um *fine-grained token* com acesso **somente** a ele
  e permissão **Contents: Read-only**.
- Sem `[dados]`, o app lê de uma pasta local (`DADOS_PASTA` ou `./dados`, ignorada pelo git).
- Sem `[login]`, o app não abre. Para desenvolver sem login: `DASHBOARD_SEM_LOGIN=1`.

## Deploy (Streamlit Community Cloud)

- Main file path: `app/streamlit_app.py` · Python 3.13
- Em **Advanced settings → Secrets**, cole os blocos `[login]` e `[dados]`.
- O token tem validade: ao expirar, o app mostra "O GitHub recusou o token" — gere outro e
  atualize os secrets.

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/streamlit_app.py` | layout e filtros |
| `app/regras.py` | regras de status (último sync por cliente, pendente com problema, sem sync > 48h, taxa de erro) |
| `app/dados.py` | leitura dos CSVs (GitHub ou pasta local) |
| `app/autenticacao.py`, `app/senha.py` | login por usuário e senha (hash PBKDF2, limite de tentativas) |
| `app/tema.py`, `app/componentes.py`, `.streamlit/config.toml` | identidade visual Mindsight 3.0 |

```bash
python -m pytest tests
```
