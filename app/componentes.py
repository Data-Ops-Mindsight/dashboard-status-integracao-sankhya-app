"""Componentes HTML do dashboard (cartões, selos, tabela).

O HTML é montado sem quebras de linha/indentação porque st.markdown interpreta
linhas indentadas como bloco de código.
"""

from html import escape

import pandas as pd
import streamlit as st

import regras
import tema


def _render(html):
    st.markdown(html, unsafe_allow_html=True)


def formatar_data_hora(valor):
    return valor.strftime("%d/%m %H:%M") if pd.notna(valor) else "—"


def formatar_ha_quanto(horas):
    if pd.isna(horas):
        return ""
    if horas < 1:
        return "agora há pouco"
    if horas < 48:
        return f"há {horas:.0f}h"
    return f"há {horas / 24:.0f} dias"


def cabecalho(ultima_execucao, horas_desde, atrasada):
    alerta = "<div class='ms-alerta'>⚠ coleta atrasada — verifique o agendamento</div>" if atrasada else ""
    _render(
        "<div class='ms-cabecalho'>"
        "<div class='ms-marca'>"
        f"<img src='{tema.svg_base64('logo_roxo.svg')}' alt='mindsight by Sankhya'>"
        "<div><h1>Integrações Sankhya</h1>"
        "<div class='ms-sub'>Acompanhamento do sync Folha Sankhya por cliente</div></div>"
        "</div>"
        "<div class='ms-coleta'>Última coleta (Brasília)"
        f"<b>{formatar_data_hora(ultima_execucao)}</b>"
        f"{formatar_ha_quanto(horas_desde)}{alerta}</div>"
        "</div>"
    )


def secao(titulo):
    _render(f"<div class='ms-secao'>{escape(titulo)}</div>")


def intro(texto, cor=None):
    """Caixa de introdução de uma aba/seção: o que ela responde e como usar (aceita <b> no texto).

    Todas as caixas usam o roxo da marca, a mesma da primeira do painel; `cor` é ignorado de propósito
    (as seções mantêm o acento nos cartões e gráficos, não nas explicações)."""
    _render(f"<div class='ms-intro' style='--cor:{tema.ROXO}'>{texto}</div>")


def descricao(responde, como_ler=None):
    """Explicação de um gráfico/seção, no mesmo quadro roxo da introdução (fonte menor): a pergunta que ele
    responde e, opcionalmente, como lê-lo."""
    partes = [f"<b>Responde:</b> {responde}"]
    if como_ler:
        partes.append(f"<b>Como ler:</b> {como_ler}")
    _render(f"<div class='ms-intro ms-menor' style='--cor:{tema.ROXO}'>{'<br>'.join(partes)}</div>")


def nota(texto):
    _render(f"<p class='ms-nota'>{texto}</p>")


def legenda_status():
    itens = "".join(
        f"<span><span class='ms-quadro' style='--cor:{tema.cor(tema.ESTADO_DO_STATUS[s])}'>{tema.GLIFOS_STATUS[r]}</span>{r}</span>"
        for s, r in tema.ROTULOS_STATUS.items()
    )
    _render(f"<div class='ms-legenda'>{itens}</div>")


def legenda_gradiente(cores, rotulo_min, rotulo_max):
    _render(f"<div class='ms-legenda'><span class='ms-gradiente'>{escape(rotulo_min)}"
            f"<span class='ms-faixa' style='background:linear-gradient(90deg,{','.join(cores)})'></span>"
            f"{escape(rotulo_max)}</span></div>")


def selo(estado):
    return (f"<span class='ms-selo' style='--cor:{tema.cor(estado)};--texto:{tema.cor(estado, 'texto')}'>"
            f"<span class='ms-ponto'></span>{escape(estado)}</span>")


AJUDA_ESTADOS = {
    regras.SUCESSO: "Clientes cujo ÚLTIMO sync terminou com sucesso.",
    regras.ERRO: "Clientes cujo ÚLTIMO sync terminou em erro.",
    regras.PENDENTE: "Clientes cujo último sync ainda está pendente (em andamento ou aguardando), sem sinal de problema.",
    regras.PENDENTE_PROBLEMA: "Clientes com sync pendente há mais de 24 horas, ou com 2 syncs pendentes seguidos: "
                              "provavelmente travado, não só em andamento.",
    regras.SEM_SYNC: "Clientes sem nenhum sync há mais de 7 dias (ou nunca coletados).",
}


def cartoes_estado(contagem, total):
    itens = []
    for estado in regras.ESTADOS_EXIBICAO:
        qtd = int(contagem.get(estado, 0))
        pct = f"{qtd / total:.0%} dos clientes" if total else ""
        itens.append(
            f"<div class='ms-cartao{' ms-zerado' if qtd == 0 else ''}' style='--cor:{tema.cor(estado)}' "
            f"title='{escape(AJUDA_ESTADOS[estado], quote=True)}'>"
            f"<div class='ms-rotulo'><span class='ms-ponto' style='--cor:{tema.cor(estado)}'></span>{escape(estado)}"
            f" <span class='ms-info'>ⓘ</span></div>"
            f"<div class='ms-valor'>{qtd}</div><div class='ms-detalhe'>{pct}</div></div>"
        )
    _render(f"<div class='ms-cartoes'>{''.join(itens)}</div>")


def cartoes_metricas(metricas):
    """metricas: lista de (rótulo, valor, detalhe[, cor[, ajuda]]).

    Sem cor explícita, cada cartão ganha uma cor da paleta (em ordem), para não ficarem todos iguais.
    `ajuda` (texto) vira o balão ao passar o mouse sobre o cartão: o que ele responde e como é calculado."""
    itens = []
    for i, metrica in enumerate(metricas):
        rotulo, valor, detalhe = metrica[:3]
        cor = metrica[3] if len(metrica) > 3 and metrica[3] else tema.PALETA_CATEGORIAS[i % len(tema.PALETA_CATEGORIAS)]
        ajuda = metrica[4] if len(metrica) > 4 else None
        dica = f" title='{escape(ajuda, quote=True)}'" if ajuda else ""
        info = " <span class='ms-info'>ⓘ</span>" if ajuda else ""
        itens.append(
            f"<div class='ms-cartao ms-acento' style='--cor:{cor}'{dica}>"
            f"<div class='ms-rotulo'>{escape(rotulo)}{info}</div>"
            f"<div class='ms-valor'>{escape(str(valor))}</div><div class='ms-detalhe'>{escape(detalhe or '')}</div></div>"
        )
    _render(f"<div class='ms-cartoes'>{''.join(itens)}</div>")


def _trilha_syncs(status_lista, qtd=regras.QTD_ULTIMOS_SYNCS):
    vazios = "<span class='ms-quadro ms-vazio' title='sem sync'></span>" * (qtd - len(status_lista))
    quadros = "".join(
        f"<span class='ms-quadro' style='--cor:{tema.cor(tema.ESTADO_DO_STATUS.get(s, regras.SEM_SYNC))}' "
        f"title='{tema.ROTULOS_STATUS.get(s, s)}'></span>"
        for s in status_lista
    )
    return f"<span class='ms-trilha' title='Mais antigo → mais recente'>{vazios}{quadros}</span>"


def _tag_erro_predominante(tipo_erro, quantidade_total):
    # df_atual vem de um merge (tenant sem classificação publicada ainda) --
    # a coluna fica com NaN (float), não None, então `pd.isna` é
    # obrigatório aqui (`not tipo_erro` não pega NaN, que é truthy).
    if pd.isna(tipo_erro) or not tipo_erro:
        return "<span class='ms-quando'>—</span>"
    qtd = "" if pd.isna(quantidade_total) else f" ({int(quantidade_total)})"
    return f"<span class='ms-selo' style='--cor:{tema.GRAFITE};--texto:{tema.GRAFITE}'>{escape(tipo_erro)}{qtd}</span>"


def _subtitulo_geometria(geometria):
    """Linha menor sob o erro predominante: geometria do conflito_timespan (dict ou vazio/NaN)."""
    if not isinstance(geometria, dict) or not geometria.get("geometria"):
        return ""
    outras = geometria.get("outras") or 0
    mais = f" +{outras}" if outras else ""
    return (f"<div class='ms-quando' title='Geometria do conflito (última triagem)'>"
            f"{escape(geometria['geometria'])} ({int(geometria['quantidade'])}){mais}</div>")


def _titulo_erro_predominante(data_coleta):
    quando = ""
    instante = pd.to_datetime(data_coleta, utc=True, errors="coerce") if pd.notna(data_coleta) else pd.NaT
    if pd.notna(instante):
        quando = f" (coleta de {formatar_data_hora(instante)} UTC)"
    return escape("Tipo de erro com mais ocorrências no ÚLTIMO sync deste cliente" + quando
                  + ". Só aparece quando o último sync deu erro.", quote=True)


COLUNA_QTD_ERROS = "Qtd. de erros"
COLUNA_DIAS_SEGUIDOS = "Dias seguidos com erro"
COLUNA_ERRO_PREDOMINANTE = "Erro predominante"
DICAS_COLUNAS = {
    "Cliente": "Nome do cliente (tenant) com integração Folha Sankhya ativa. O ⚠️ ao lado indica que a última "
               "coleta deste cliente falhou na API, então o status pode estar desatualizado.",
    "Status": "Estado do ÚLTIMO sync do cliente: Sucesso, Erro, Pendente, Pendente com problema (pendente há mais "
              "de 24h ou 2 pendentes seguidos) ou 7d sem sync (nenhum sync há mais de 7 dias).",
    "Último sync": "Quando o sync mais recente do cliente foi criado (horário UTC, como no sistema) e há quanto "
                   "tempo isso foi.",
    "Itens afetados": "Quantos registros (colaboradores/itens) o último sync processou.",
    COLUNA_QTD_ERROS: "Registros com erro no ÚLTIMO sync do cliente (sync_history_items + sync_datas). "
                      "Só aparece quando o último sync deu erro.",
    COLUNA_DIAS_SEGUIDOS: "Há quantos dias seguidos o cliente está com erro: dias distintos (UTC) da sequência atual "
                          "de syncs com erro, até o mais recente. Syncs repetidos no mesmo dia contam um dia só.",
    "Últimos 7 syncs": "Um quadrado por sync, do mais antigo (esquerda) ao mais recente (direita): verde = sucesso, "
                       "vermelho = erro, laranja = pendente, vazio = ainda sem sync.",
    COLUNA_ERRO_PREDOMINANTE: "Tipo de erro mais frequente no ÚLTIMO sync (só aparece quando ele deu erro). Quando "
                              "é conflito_timespan, a linha menor traz a geometria do conflito (o motivo do choque "
                              "de períodos), vinda da última triagem; +N indica quantas outras geometrias existem.",
}


COLUNAS_QUE_QUEBRAM_LINHA = (COLUNA_DIAS_SEGUIDOS,)


def _th(titulo, numerica, dica=None):
    classes = (["ms-num"] if numerica else []) + (["ms-quebra"] if titulo in COLUNAS_QUE_QUEBRAM_LINHA else [])
    classe = f" class='{' '.join(classes)}'" if classes else ""
    atributo_dica = f" title='{escape(dica, quote=True)}'" if dica else ""
    return f"<th{classe}{atributo_dica}>{titulo}</th>"


def _formatar_qtd(valor):
    return "—" if pd.isna(valor) else f"{int(valor):,}".replace(",", ".")


def explicacao_das_colunas(cor=None):
    """Caixa roxa (mesmo estilo da introdução, fonte menor) explicando cada coluna da tabela de status.

    Usa as mesmas dicas dos cabeçalhos (DICAS_COLUNAS), então os dois textos nunca divergem."""
    itens = "".join(f"<li><b>{escape(coluna)}:</b> {escape(dica)}</li>" for coluna, dica in DICAS_COLUNAS.items())
    _render(f"<div class='ms-intro ms-menor' style='--cor:{tema.ROXO}'>"
            f"<b>Entenda cada coluna</b><ul>{itens}</ul></div>")


def tabela_status(df):
    if df.empty:
        _render("<div class='ms-tabela-wrap'><p class='ms-nota' style='padding:18px'>Nenhum cliente com esses filtros.</p></div>")
        return

    tem_classificacao = "tipo_erro_predominante" in df.columns
    tem_qtd_erros = "qtd_erros_ultimo_sync" in df.columns
    linhas = []
    for linha in df.itertuples(index=False):
        aviso = ("<span class='ms-aviso' title='A última coleta deste cliente falhou na API — o status pode estar desatualizado'>⚠️</span>"
                 if linha.falha_coleta else "")
        itens = "—" if pd.isna(linha.itens) else f"{int(linha.itens):,}".replace(",", ".")
        coluna_qtd_erros = (
            f"<td class='ms-num'>{_formatar_qtd(linha.qtd_erros_ultimo_sync)}</td>" if tem_qtd_erros else ""
        )
        coluna_classificacao = (
            f"<td title='{_titulo_erro_predominante(getattr(linha, 'data_tipo_erro', None))}'>"
            f"{_tag_erro_predominante(linha.tipo_erro_predominante, linha.qtd_tipo_predominante)}"
            f"{_subtitulo_geometria(getattr(linha, 'geometria_conflito', None))}</td>"
            if tem_classificacao else ""
        )
        linhas.append(
            "<tr>"
            f"<td class='ms-cliente'>{escape(linha.tenant)}{aviso}</td>"
            f"<td>{selo(linha.estado)}</td>"
            f"<td>{formatar_data_hora(linha.ultimo_sync)} <span class='ms-quando'>{formatar_ha_quanto(linha.horas_desde)}</span></td>"
            f"<td class='ms-num'>{itens}</td>"
            f"{coluna_qtd_erros}"
            f"<td class='ms-num'>{linha.dias_seguidos_erro or '—'}</td>"
            f"<td>{_trilha_syncs(linha.ultimos_syncs)}</td>"
            f"{coluna_classificacao}"
            "</tr>"
        )

    cabecalhos = ["Cliente", "Status", "Último sync", "Itens afetados"]
    if tem_qtd_erros:
        cabecalhos.append(COLUNA_QTD_ERROS)
    cabecalhos += [COLUNA_DIAS_SEGUIDOS, "Últimos 7 syncs"]
    if tem_classificacao:
        cabecalhos.append(COLUNA_ERRO_PREDOMINANTE)
    numericas = ("Itens afetados", COLUNA_QTD_ERROS, COLUNA_DIAS_SEGUIDOS)
    ths = "".join(_th(c, c in numericas, DICAS_COLUNAS.get(c)) for c in cabecalhos)
    _render(f"<div class='ms-tabela-wrap'><table class='ms-tabela'><thead><tr>{ths}</tr></thead>"
            f"<tbody>{''.join(linhas)}</tbody></table></div>")


def rodape(texto):
    _render(f"<div class='ms-rodape'><span>{texto}</span>"
            f"<img src='{tema.svg_base64('logo_preto.svg')}' alt='mindsight by Sankhya'></div>")
