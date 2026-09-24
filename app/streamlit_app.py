"""Dashboard de acompanhamento das integrações Sankhya."""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import autenticacao
import componentes as ui
import dados
import regras
import tema

st.set_page_config(page_title="Integrações Sankhya · Mindsight",
                   page_icon=str(Path(__file__).parent / "assets" / "icone_roxo.png"), layout="wide")
st.markdown(tema.CSS, unsafe_allow_html=True)
usuario = autenticacao.exigir_login()

INTERVALO_COLETA = pd.Timedelta(hours=4)
LIMITE_DIAS_MAPA_DIARIO = 60
ATALHOS_PERIODO = {"7 dias": 7, "14 dias": 14, "30 dias": 30, "Tudo": None}
ORDENACOES = {
    "Gravidade": (["estado", "taxa_erro_7d", "tenant"], [True, False, True]),
    "Cliente": (["tenant"], [True]),
    "Taxa de erro": (["taxa_erro_7d", "tenant"], [False, True]),
    "Último sync": (["ultimo_sync", "tenant"], [True, True]),
}

ESCALA_STATUS = alt.Scale(
    domain=list(tema.ROTULOS_STATUS.values()),
    range=[tema.cor(tema.ESTADO_DO_STATUS[s]) for s in tema.ROTULOS_STATUS],
)


def fonte_dados():
    """Seção [dados] dos secrets (GitHub) ou None (pasta local, para desenvolvimento)."""
    try:
        fonte = st.secrets.get("dados")
    except Exception:
        fonte = None
    return dict(fonte) if fonte else None


@st.cache_data(ttl=600, show_spinner="Carregando dados…")
def carregar(fonte):
    return dados.carregar_historico(fonte), dados.carregar_coletas(fonte)


def sem_fuso(serie):
    """Altair/Vega interpreta datas sem fuso como horário local do navegador."""
    return serie.dt.tz_localize(None)


# =============================================================================
# Dados
# =============================================================================

fonte = fonte_dados()
try:
    historico, coletas = carregar(fonte)
except dados.ErroFonteDados as e:
    st.error(f"Não foi possível carregar os dados ({dados.descrever_fonte(fonte)}): {e}")
    st.stop()

agora = pd.Timestamp.now(tz=dados.FUSO)
df_atual = regras.status_atual(historico, coletas, agora)
ultima_execucao = coletas["executado_em"].max()

ui.cabecalho(ultima_execucao, (agora - ultima_execucao) / pd.Timedelta(hours=1),
             atrasada=agora - ultima_execucao > INTERVALO_COLETA * 2)
if usuario:
    col_usuario, col_sair = st.columns([8, 1], vertical_alignment="center")
    col_usuario.markdown(f"<div class='ms-usuario'>Conectado como <b>{usuario}</b></div>", unsafe_allow_html=True)
    col_sair.button("Sair", on_click=autenticacao.sair, width="stretch")

aba_atual, aba_historico = st.tabs(["Status atual", "Histórico"])

# =============================================================================
# Aba 1 — Status atual
# =============================================================================

with aba_atual:
    contagem = df_atual["estado"].value_counts()
    ui.cartoes_estado(contagem, len(df_atual))

    col_status, col_cliente, col_ordem = st.columns([5, 3, 1.4], vertical_alignment="bottom")
    estados_filtro = col_status.pills(
        "Status", regras.ESTADOS, selection_mode="multi",
        format_func=lambda e: f"{e} ({int(contagem.get(e, 0))})",
    )
    clientes_filtro = col_cliente.multiselect("Cliente", sorted(df_atual["tenant"]), placeholder="Todos os clientes")
    ordem = col_ordem.selectbox("Ordenar por", list(ORDENACOES))

    tabela = df_atual
    if estados_filtro:
        tabela = tabela.loc[tabela["estado"].isin(estados_filtro)]
    if clientes_filtro:
        tabela = tabela.loc[tabela["tenant"].isin(clientes_filtro)]
    colunas, crescente = ORDENACOES[ordem]
    tabela = tabela.sort_values(colunas, ascending=crescente, na_position="last")

    ui.tabela_status(tabela)
    ui.nota(f"{len(tabela)} de {len(df_atual)} clientes · Erro 7d considera só syncs finalizados (pending fora da conta)"
            " · ⚠️ = a última coleta deste cliente falhou na API")

# =============================================================================
# Aba 2 — Histórico
# =============================================================================

with aba_historico:
    data_min = historico["created"].min().date()
    data_max = agora.date()

    def aplicar_atalho():
        dias = ATALHOS_PERIODO.get(st.session_state.get("atalho_periodo"))
        inicio = data_min if dias is None else max(data_min, data_max - pd.Timedelta(days=dias - 1).to_pytimedelta())
        st.session_state["periodo"] = (inicio, data_max)

    if "periodo" not in st.session_state:
        st.session_state["atalho_periodo"] = "30 dias"
        aplicar_atalho()

    col_atalho, col_datas, col_clientes = st.columns([2, 2, 3], vertical_alignment="bottom")
    col_atalho.segmented_control("Período", list(ATALHOS_PERIODO), key="atalho_periodo", on_change=aplicar_atalho)
    periodo = col_datas.date_input("Intervalo", key="periodo", min_value=data_min, max_value=data_max, format="DD/MM/YYYY")
    incluir_inativos = st.toggle("Incluir clientes fora da última coleta", value=False)

    base = historico if incluir_inativos else historico.loc[historico["tenant"].isin(df_atual["tenant"])]
    clientes_hist = col_clientes.multiselect("Clientes", sorted(base["tenant"].unique()), placeholder="Todos os clientes")

    inicio, fim = (periodo if len(periodo) == 2 else (periodo[0], data_max))
    datas_sync = pd.to_datetime(base["data_sync"]).dt.date
    hist = base.loc[(datas_sync >= inicio) & (datas_sync <= fim)]
    if clientes_hist:
        hist = hist.loc[hist["tenant"].isin(clientes_hist)]

    if hist.empty:
        st.info("Nenhum sync no período e clientes selecionados.")
        st.stop()

    # --- Mapa de calor: clientes x dias (ou x semanas, em períodos longos) ---
    semanal = (fim - inicio).days + 1 > LIMITE_DIAS_MAPA_DIARIO
    eixo_y = dict(title=None, axis=alt.Axis(ticks=False, domain=False, labelPadding=8, labelLimit=240))

    if not semanal:
        ui.secao("Status diário por cliente")
        ui.legenda_status()
        diario = regras.status_diario(hist)
        diario["Status"] = diario["status"].map(tema.ROTULOS_STATUS)
        diario["Glifo"] = diario["Status"].map(tema.GLIFOS_STATUS)
        diario["Dia"] = pd.to_datetime(diario["data_sync"])
        diario["Horário"] = diario["created"].dt.strftime("%d/%m %H:%M")

        ordem_tenants = (diario.assign(erro=diario["status"] == "error")
                         .groupby("tenant")["erro"].mean().sort_values(ascending=False).index.tolist())

        base_mapa = alt.Chart(diario).encode(
            x=alt.X("yearmonthdate(Dia):O", title=None,
                    axis=alt.Axis(format="%d/%m", labelAngle=0, labelOverlap=True, ticks=False, domain=False)),
            y=alt.Y("tenant:N", sort=ordem_tenants, **eixo_y),
            tooltip=[alt.Tooltip("tenant:N", title="Cliente"), alt.Tooltip("Horário:N", title="Último sync do dia"),
                     "Status:N", alt.Tooltip("number_of_affected_items:Q", title="Itens afetados", format=",.0f")],
        )
        celulas = base_mapa.mark_rect(cornerRadius=3, stroke=tema.OFF_WHITE, strokeWidth=2).encode(
            color=alt.Color("Status:N", scale=ESCALA_STATUS, legend=None),
        )
        glifos = base_mapa.mark_text(color="white", fontSize=12, fontWeight=600).encode(text="Glifo:N")
        # Períodos curtos: célula de largura fixa (não esticar 4 dias pela tela toda)
        largura_fixa = diario["data_sync"].nunique() * 30 < 900
        mapa = (celulas + glifos).properties(
            height=alt.Step(24),
            **({"width": alt.Step(30)} if largura_fixa else {}),
        )
        nota_mapa = ("Cada célula é o último sync do dia (× = erro, – = pendente). "
                     "Clientes ordenados pela proporção de dias com erro no período. Célula vazia = nenhum sync naquele dia.")
    else:
        ui.secao("Taxa de erro semanal por cliente")
        ui.legenda_gradiente(tema.RAMPA_ERRO, "0% de erro", "100% de erro")
        semanas = regras.taxa_erro_semanal(hist)
        semanas["Semana"] = semanas["semana"]
        semanas["Período"] = (semanas["semana"].dt.strftime("%d/%m/%y") + " a "
                              + (semanas["semana"] + pd.Timedelta(days=6)).dt.strftime("%d/%m/%y"))
        semanas["Resumo"] = (semanas["erros"].astype(int).astype(str) + " erros de "
                             + semanas["finalizados"].astype(int).astype(str) + " syncs finalizados")

        totais = semanas.groupby("tenant")[["erros", "finalizados"]].sum()
        ordem_tenants = (totais["erros"] / totais["finalizados"]).fillna(0).sort_values(ascending=False).index.tolist()

        mapa = alt.Chart(semanas.dropna(subset=["taxa_erro"])).mark_rect(
            cornerRadius=2, stroke=tema.OFF_WHITE, strokeWidth=1,
        ).encode(
            x=alt.X("yearmonthdate(Semana):O", title=None,
                    axis=alt.Axis(format="%m/%y", labelAngle=0, labelOverlap=True, ticks=False, domain=False)),
            y=alt.Y("tenant:N", sort=ordem_tenants, **eixo_y),
            color=alt.Color("taxa_erro:Q", legend=None,
                            scale=alt.Scale(domain=[0, 1 / 3, 2 / 3, 1], range=tema.RAMPA_ERRO)),
            tooltip=[alt.Tooltip("tenant:N", title="Cliente"), alt.Tooltip("Período:N", title="Semana"),
                     alt.Tooltip("taxa_erro:Q", title="Taxa de erro", format=".0%"),
                     alt.Tooltip("Resumo:N", title="Syncs"), alt.Tooltip("pendentes:Q", title="Pendentes")],
        ).properties(height=alt.Step(24))
        largura_fixa = False
        nota_mapa = ("Cada célula é uma semana (segunda a domingo); a cor é a proporção de syncs com erro entre os "
                     f"finalizados. Períodos acima de {LIMITE_DIAS_MAPA_DIARIO} dias são agrupados por semana. "
                     "Clientes ordenados pela taxa de erro no período. Célula vazia = nenhum sync finalizado na semana.")

    st.altair_chart(tema.configurar_grafico(mapa), width="content" if largura_fixa else "stretch", theme=None)
    ui.nota(nota_mapa)

    # --- Detalhe de um cliente ---
    ui.secao("Detalhe do cliente")
    tenant = st.selectbox("Cliente", ordem_tenants, label_visibility="collapsed")
    syncs = hist.loc[hist["tenant"] == tenant].sort_values(["created", "id_sync"], ascending=False)
    syncs_todos = historico.loc[historico["tenant"] == tenant].sort_values(["created", "id_sync"], ascending=False)

    estado_atual = df_atual.loc[df_atual["tenant"] == tenant, "estado"]
    ultimo_ok = regras.ultimo_sucesso(syncs_todos)
    taxa = regras.taxa_erro(syncs_todos, agora)
    ui.cartoes_metricas([
        ("Status atual", estado_atual.iloc[0] if not estado_atual.empty else "fora da coleta", None),
        ("Taxa de erro (7 dias)", f"{taxa:.0%}" if pd.notna(taxa) else "—", "entre syncs finalizados"),
        ("Erros seguidos", regras.erros_seguidos(syncs_todos), "a partir do mais recente"),
        ("Último sucesso", ui.formatar_data_hora(ultimo_ok),
         ui.formatar_ha_quanto((agora - ultimo_ok) / pd.Timedelta(hours=1)) if pd.notna(ultimo_ok) else "nenhum no histórico"),
        ("Syncs no período", len(syncs), f"{inicio:%d/%m} a {fim:%d/%m}"),
    ])

    linha_tempo = syncs.assign(
        Status=syncs["status"].map(tema.ROTULOS_STATUS),
        Criado=sem_fuso(syncs["created"]),
        Horário=syncs["created"].dt.strftime("%d/%m %H:%M"),
    )
    base_linha = alt.Chart(linha_tempo).encode(
        x=alt.X("Criado:T", title=None, axis=alt.Axis(format="%d/%m", grid=False, labelOverlap=True)),
        y=alt.Y("number_of_affected_items:Q", title="Itens afetados", axis=alt.Axis(tickCount=4, domain=False, ticks=False)),
    )
    trilha = base_linha.mark_line(color=tema.BORDA, strokeWidth=2)
    pontos = base_linha.mark_circle(size=110, opacity=1, stroke="white", strokeWidth=2).encode(
        color=alt.Color("Status:N", scale=ESCALA_STATUS),
        tooltip=["Horário:N", "Status:N", alt.Tooltip("number_of_affected_items:Q", title="Itens afetados", format=",.0f"),
                 alt.Tooltip("total_time:Q", title="Tempo total (s)", format=".0f"), alt.Tooltip("stage:N", title="Etapa")],
    )
    st.altair_chart(tema.configurar_grafico((trilha + pontos).properties(height=260)), width="stretch", theme=None)

    st.dataframe(
        pd.DataFrame({
            "Sync": syncs["id_sync"],
            "Criado": syncs["created"].map(ui.formatar_data_hora),
            "Status": syncs["status"].map(tema.ROTULOS_STATUS),
            "Etapa": syncs["stage"],
            "Itens afetados": syncs["number_of_affected_items"],
            "Tempo total (s)": syncs["total_time"].round(0),
            "Tipo": syncs["sync_type"],
        }),
        hide_index=True,
        width="stretch",
        column_config={"Sync": st.column_config.NumberColumn(format="%d"),
                       "Itens afetados": st.column_config.NumberColumn(format="localized")},
    )

ui.rodape("Coleta automática a cada 4h · dados do histórico de sync da plataforma")
