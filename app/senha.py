"""Hash e verificação de senha (PBKDF2-SHA256). Só biblioteca padrão — usado pelo app,
pelo gerar_senha.py e pelos testes, sem depender do Streamlit."""

import base64
import hashlib
import hmac
import secrets

ALGORITMO = "pbkdf2_sha256"
ITERACOES = 600_000


def _b64(dados):
    return base64.b64encode(dados).decode()


def gerar_hash(senha, iteracoes=ITERACOES):
    salt = secrets.token_bytes(16)
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, iteracoes)
    return f"{ALGORITMO}${iteracoes}${_b64(salt)}${_b64(derivado)}"


def verificar_senha(senha, hash_armazenado):
    try:
        algoritmo, iteracoes, salt, esperado = hash_armazenado.split("$")
        if algoritmo != ALGORITMO:
            return False
        derivado = hashlib.pbkdf2_hmac("sha256", senha.encode(), base64.b64decode(salt), int(iteracoes))
        return hmac.compare_digest(derivado, base64.b64decode(esperado))
    except (ValueError, AttributeError, TypeError):
        return False


def credenciais_validas(usuario, senha, usuario_esperado, hash_armazenado):
    usuario_ok = hmac.compare_digest((usuario or "").strip().lower().encode(),
                                     (usuario_esperado or "").strip().lower().encode())
    senha_ok = verificar_senha(senha or "", hash_armazenado)  # sempre calcula, mesmo com usuário errado
    return usuario_ok and senha_ok
