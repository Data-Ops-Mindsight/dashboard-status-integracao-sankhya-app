"""Recarrega os módulos locais do app quando o arquivo mudou no disco.

No Streamlit Cloud, um deploy com o app aberto atualiza os arquivos, mas o processo
pode continuar com a versão antiga dos módulos auxiliares na memória — o script
principal (novo) passa a chamar funções que o módulo antigo não tem
(ex.: AttributeError). Chamada no topo do streamlit_app.py, antes dos outros imports.
"""

import hashlib
import importlib
import sys
from pathlib import Path

ATRIBUTO_ASSINATURA = "_assinatura_carregada"


def _assinatura(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def recarregar_modulos_alterados(nomes):
    """`nomes` em ordem de dependência (quem é importado primeiro vem antes).

    Se qualquer módulo já carregado estiver diferente do arquivo, recarrega TODOS
    os que estão carregados, nessa ordem — assim nenhum fica apontando para
    funções/classes da versão antiga de outro. Módulo carregado antes desta
    proteção existir (sem assinatura) conta como desatualizado.
    Retorna a lista de módulos recarregados.
    """
    carregados = [sys.modules[n] for n in nomes if getattr(sys.modules.get(n), "__file__", None)]
    desatualizado = any(
        getattr(m, ATRIBUTO_ASSINATURA, None) != _assinatura(m.__file__) for m in carregados
    )
    if not desatualizado:
        return []

    recarregados = []
    for modulo in carregados:
        modulo = importlib.reload(modulo)
        setattr(modulo, ATRIBUTO_ASSINATURA, _assinatura(modulo.__file__))
        recarregados.append(modulo.__name__)
    return recarregados


def registrar_assinaturas(nomes):
    """Marca os módulos recém-importados com a assinatura do arquivo atual."""
    for nome in nomes:
        modulo = sys.modules.get(nome)
        if getattr(modulo, "__file__", None) and not hasattr(modulo, ATRIBUTO_ASSINATURA):
            setattr(modulo, ATRIBUTO_ASSINATURA, _assinatura(modulo.__file__))
