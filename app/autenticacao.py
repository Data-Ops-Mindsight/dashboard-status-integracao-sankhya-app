"""Login com usuário e senha únicos (compartilhados).

Configuração em .streamlit/secrets.toml (ver secrets.toml.example; gere com gerar_senha.py):
  [login]
  usuario = "mindsight"
  senha_hash = "pbkdf2_sha256$<iterações>$<salt>$<hash>"

Só o hash fica nos secrets — nunca a senha em texto.

Fail-closed: sem [login] configurado o app NÃO abre, a menos que a variável de
ambiente DASHBOARD_SEM_LOGIN=1 esteja definida (uso local).
"""

import os
import threading
import time

import streamlit as st

import tema
from senha import credenciais_validas

MAX_TENTATIVAS_SESSAO = 5
BLOQUEIO_SESSAO_S = 5 * 60
# Limite global (todas as sessões somadas), para quem abre sessões novas a cada tentativa
MAX_FALHAS_GLOBAIS = 20
JANELA_GLOBAL_S = 10 * 60


# =============================================================================
# Limite de tentativas
# =============================================================================

@st.cache_resource
def _falhas_globais():
    return {"instantes": [], "trava": threading.Lock()}


def _registrar_falha():
    st.session_state["_tentativas"] = st.session_state.get("_tentativas", 0) + 1
    if st.session_state["_tentativas"] >= MAX_TENTATIVAS_SESSAO:
        st.session_state["_bloqueado_ate"] = time.time() + BLOQUEIO_SESSAO_S
        st.session_state["_tentativas"] = 0
    registro = _falhas_globais()
    with registro["trava"]:
        registro["instantes"].append(time.time())


def _segundos_bloqueado():
    agora = time.time()
    restante_sessao = st.session_state.get("_bloqueado_ate", 0) - agora

    registro = _falhas_globais()
    with registro["trava"]:
        registro["instantes"] = [t for t in registro["instantes"] if agora - t < JANELA_GLOBAL_S]
        recentes = registro["instantes"]
        restante_global = (recentes[0] + JANELA_GLOBAL_S - agora) if len(recentes) >= MAX_FALHAS_GLOBAIS else 0

    return max(restante_sessao, restante_global, 0)


# =============================================================================
# Tela e fluxo
# =============================================================================

def _config_login():
    """Retorna (config, erro). Erro de sintaxe no secrets.toml não é tratado como 'sem login'."""
    try:
        login = st.secrets.get("login")
    except FileNotFoundError:
        return None, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if not login or not login.get("usuario") or not login.get("senha_hash"):
        return None, None
    return login, None


def _tela(titulo, texto):
    st.markdown(
        "<div class='ms-login'>"
        f"<img src='{tema.svg_base64('logo_roxo.svg')}' alt='mindsight by Sankhya'>"
        f"<h1>{titulo}</h1><p>{texto}</p></div>",
        unsafe_allow_html=True,
    )


def sair():
    st.session_state.pop("_usuario_logado", None)


def exigir_login():
    """Bloqueia a página até o login. Retorna o usuário (ou None em modo local sem login)."""
    config, erro = _config_login()
    if erro:
        _tela("Erro no arquivo de secrets",
              "O <code>.streamlit/secrets.toml</code> não pôde ser lido — verifique aspas e sintaxe TOML.")
        st.caption(erro.split("\n")[0][:200])
        st.stop()

    if config is None:
        if os.environ.get("DASHBOARD_SEM_LOGIN") == "1":
            if not st.session_state.get("_aviso_sem_login"):
                st.session_state["_aviso_sem_login"] = True
                st.toast("Login desativado (DASHBOARD_SEM_LOGIN=1) — use só localmente.", icon="🔓")
            return None
        _tela("Login não configurado",
              "Este app exige login, mas a seção <code>[login]</code> não foi encontrada nos secrets.")
        st.stop()

    if st.session_state.get("_usuario_logado"):
        return st.session_state["_usuario_logado"]

    _tela("Integrações Sankhya", "Acesso restrito. Entre com o usuário e a senha do dashboard.")
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        bloqueio = _segundos_bloqueado()
        if bloqueio:
            st.error(f"Muitas tentativas incorretas. Tente de novo em {int(bloqueio // 60) + 1} min.")
            st.stop()

        with st.form("login", border=False):
            usuario = st.text_input("Usuário", autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            enviou = st.form_submit_button("Entrar", type="primary", width="stretch")

        if enviou:
            if credenciais_validas(usuario, senha, config["usuario"], config["senha_hash"]):
                st.session_state["_usuario_logado"] = config["usuario"]
                st.session_state["_tentativas"] = 0
                st.rerun()
            _registrar_falha()
            st.error("Usuário ou senha incorretos.")
    st.stop()
