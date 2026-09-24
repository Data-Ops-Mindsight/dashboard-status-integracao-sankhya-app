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
        "<div class='ms-coleta'>Última coleta"
        f"<b>{formatar_data_hora(ultima_execucao)}</b>"
        f"{formatar_ha_quanto(horas_desde)}{alerta}</div>"
        "</div>"
    )


def secao(titulo):
    _render(f"<div class='ms-secao'>{escape(titulo)}</div>")


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


def cartoes_estado(contagem, total):
    itens = []
    for estado in regras.ESTADOS_EXIBICAO:
        qtd = int(contagem.get(estado, 0))
        pct = f"{qtd / total:.0%} dos clientes" if total else ""
        itens.append(
            f"<div class='ms-cartao{' ms-zerado' if qtd == 0 else ''}' style='--cor:{tema.cor(estado)}'>"
            f"<div class='ms-rotulo'><span class='ms-ponto' style='--cor:{tema.cor(estado)}'></span>{escape(estado)}</div>"
            f"<div class='ms-valor'>{qtd}</div><div class='ms-detalhe'>{pct}</div></div>"
        )
    _render(f"<div class='ms-cartoes'>{''.join(itens)}</div>")


def cartoes_metricas(metricas):
    """metricas: lista de (rótulo, valor, detalhe)."""
    itens = [
        f"<div class='ms-cartao' style='--cor:{tema.LILAS}'><div class='ms-rotulo'>{escape(rotulo)}</div>"
        f"<div class='ms-valor'>{escape(str(valor))}</div><div class='ms-detalhe'>{escape(detalhe or '')}</div></div>"
        for rotulo, valor, detalhe in metricas
    ]
    _render(f"<div class='ms-cartoes'>{''.join(itens)}</div>")


def _trilha_syncs(status_lista, qtd=regras.QTD_ULTIMOS_SYNCS):
    vazios = "<span class='ms-quadro ms-vazio' title='sem sync'></span>" * (qtd - len(status_lista))
    quadros = "".join(
        f"<span class='ms-quadro' style='--cor:{tema.cor(tema.ESTADO_DO_STATUS.get(s, regras.SEM_SYNC))}' "
        f"title='{tema.ROTULOS_STATUS.get(s, s)}'></span>"
        for s in status_lista
    )
    return f"<span class='ms-trilha' title='Mais antigo → mais recente'>{vazios}{quadros}</span>"


def _barra_erro(taxa):
    if pd.isna(taxa):
        return "<span class='ms-quando'>—</span>"
    return (f"<span class='ms-barra'><span class='ms-trilho'><span class='ms-preenche' style='width:{taxa:.0%}'></span></span>"
            f"<span>{taxa:.0%}</span></span>")


def tabela_status(df):
    if df.empty:
        _render("<div class='ms-tabela-wrap'><p class='ms-nota' style='padding:18px'>Nenhum cliente com esses filtros.</p></div>")
        return

    linhas = []
    for linha in df.itertuples(index=False):
        aviso = ("<span class='ms-aviso' title='A última coleta deste cliente falhou na API — o status pode estar desatualizado'>⚠️</span>"
                 if linha.falha_coleta else "")
        itens = "—" if pd.isna(linha.itens) else f"{int(linha.itens):,}".replace(",", ".")
        linhas.append(
            "<tr>"
            f"<td class='ms-cliente'>{escape(linha.tenant)}{aviso}</td>"
            f"<td>{selo(linha.estado)}</td>"
            f"<td>{formatar_data_hora(linha.ultimo_sync)} <span class='ms-quando'>{formatar_ha_quanto(linha.horas_desde)}</span></td>"
            f"<td class='ms-num'>{itens}</td>"
            f"<td>{_barra_erro(linha.taxa_erro_7d)}</td>"
            f"<td class='ms-num'>{linha.erros_seguidos or '—'}</td>"
            f"<td>{_trilha_syncs(linha.ultimos_syncs)}</td>"
            "</tr>"
        )

    cabecalhos = ["Cliente", "Status", "Último sync", "Itens afetados", "Erro 7d", "Erros seguidos", "Últimos 7 syncs"]
    ths = "".join(f"<th{' class=ms-num' if c in ('Itens afetados', 'Erros seguidos') else ''}>{c}</th>" for c in cabecalhos)
    _render(f"<div class='ms-tabela-wrap'><table class='ms-tabela'><thead><tr>{ths}</tr></thead>"
            f"<tbody>{''.join(linhas)}</tbody></table></div>")


def rodape(texto):
    _render(f"<div class='ms-rodape'><span>{texto}</span>"
            f"<img src='{tema.svg_base64('logo_preto.svg')}' alt='mindsight by Sankhya'></div>")
