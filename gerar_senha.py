"""Gera o bloco [login] para o .streamlit/secrets.toml (ou para os Secrets do Streamlit Cloud).

Uso:  python gerar_senha.py
A senha é digitada sem aparecer na tela; só o hash é impresso.
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from senha import gerar_hash  # noqa: E402

TAMANHO_MINIMO = 8

usuario = input("Usuário do dashboard [mindsight]: ").strip() or "mindsight"
senha = getpass.getpass(f"Senha (mínimo {TAMANHO_MINIMO} caracteres): ")
if len(senha) < TAMANHO_MINIMO:
    sys.exit(f"Senha muito curta: use pelo menos {TAMANHO_MINIMO} caracteres.")
if getpass.getpass("Repita a senha: ") != senha:
    sys.exit("As senhas não conferem.")

print("\nCole no .streamlit/secrets.toml (ou em Settings > Secrets no Streamlit Cloud):\n")
print("[login]")
print(f'usuario = "{usuario}"')
print(f'senha_hash = "{gerar_hash(senha)}"')
