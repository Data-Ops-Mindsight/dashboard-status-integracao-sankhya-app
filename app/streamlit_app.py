"""Dashboard de acompanhamento das integrações Sankhya."""

import os
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import recarga

# Módulos locais em ordem de dependência (quem é importado por outro vem antes).
# Se um deploy atualizou algum arquivo com o app aberto, recarrega todos antes de usar.
MODULOS_LOCAIS = ["senha", "regras", "tema", "graficos", "mapeamento", "dados", "dados_correcoes", "componentes",
                  "autenticacao"]
recarga.recarregar_modulos_alterados(MODULOS_LOCAIS)

import autenticacao  # noqa: E402
import componentes as ui  # noqa: E402
import dados  # noqa: E402
import dados_correcoes  # noqa: E402
import graficos  # noqa: E402
import mapeamento  # noqa: E402
import regras  # noqa: E402
import tema  # noqa: E402

recarga.registrar_assinaturas(MODULOS_LOCAIS)

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
    "Taxa de erro (7 dias)": (["taxa_erro_7d", "tenant"], [False, True]),
    "Último sync": (["ultimo_sync", "tenant"], [True, True]),
    "Quantidade de erros": (["qtd_erros_ultimo_sync", "tenant"], [False, True]),
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


def credenciais_sheets():
    """Credencial (JSON de conta de serviço) pra ler a planilha de
    correções: seção [sheets] dos secrets (produção) ou
    GOOGLE_SHEETS_CREDENTIALS_JSON no ambiente (desenvolvimento local) --
    mesma credencial que `automacao/aplicador/relatorio_sheets.py` usa pra
    publicar, só que com escopo de leitura."""
    try:
        secao = st.secrets.get("sheets")
    except Exception:
        secao = None
    if secao and secao.get("credentials_json"):
        return secao["credentials_json"]
    return os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")


@st.cache_data(ttl=600, show_spinner="Carregando dados…")
def carregar(fonte):
    return dados.carregar_historico(fonte), dados.carregar_coletas(fonte)


@st.cache_data(ttl=300, show_spinner="Carregando indicadores de correção…")
def carregar_correcoes(credenciais_json):
    return dados_correcoes.carregar_resumo(credenciais_json), dados_correcoes.carregar_correcoes(credenciais_json)


@st.cache_data(ttl=300, show_spinner="Carregando cobertura de credenciais…")
def carregar_cobertura_credenciais_cacheada(credenciais_json):
    return dados_correcoes.carregar_cobertura_credenciais(credenciais_json)


@st.cache_data(ttl=600, show_spinner=False)
def carregar_erros_sync_cacheado(fonte):
    """Tipos de erro do último sync de cada cliente (gerados pela coleta). Silencioso e nunca
    propaga erro: só ENRIQUECE a aba "Status atual"; se falhar, a tabela continua funcionando,
    só sem a coluna "Erro predominante"."""
    try:
        return dados.carregar_erros_sync(fonte)
    except dados.ErroFonteDados:
        return pd.DataFrame(columns=["tenant", "id_sync", "tipo_erro", "quantidade", "coletado_em"])


@st.cache_data(ttl=600, show_spinner=False)
def carregar_geometrias_cacheado(credenciais_json):
    """Geometria do conflito_timespan por cliente (publicada pela triagem na planilha). Só ENRIQUECE
    a tabela: sem credencial, sem a coluna ou com falha, a tabela funciona normalmente sem o subtítulo."""
    if not credenciais_json:
        return {}
    try:
        return dados_correcoes.geometria_do_conflito_por_tenant(
            dados_correcoes.carregar_classificacao_erros(credenciais_json))
    except dados_correcoes.ErroFonteDados:
        return {}


def recarregar():
    """Descarta o cache (para todos os usuários) e busca os CSVs/a planilha
    de novo no próximo carregamento."""
    carregar.clear()
    carregar_correcoes.clear()
    carregar_cobertura_credenciais_cacheada.clear()
    carregar_erros_sync_cacheado.clear()
    carregar_geometrias_cacheado.clear()


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
    st.button("Tentar de novo", on_click=recarregar)
    st.stop()

if historico.empty:
    st.info("O histórico foi reiniciado e ainda não há nenhuma coleta. Os dados aparecem após a próxima coleta (a cada 4 horas).")
    st.button("Atualizar", on_click=recarregar)
    st.stop()

agora = pd.Timestamp.now(tz=dados.FUSO)
df_atual = regras.status_atual(historico, coletas, agora)
ultima_execucao = coletas["executado_em"].max()

# Tipo de erro predominante por cliente, no ÚLTIMO sync (gerado pela coleta a cada 4h,
# casado com o id do último sync de cada cliente). Enriquece "Status atual" sem depender
# dele: sem o arquivo ou com falha, a tabela funciona normalmente, só sem essa coluna.
erros_sync = carregar_erros_sync_cacheado(fonte)
predominantes = regras.erro_predominante_do_ultimo_sync(
    erros_sync, dict(zip(df_atual["tenant"], df_atual["id_ultimo_sync"]))
)
df_atual["tipo_erro_predominante"] = df_atual["tenant"].map(
    lambda t: predominantes.get(t, {}).get("tipo_erro_predominante")
)
# Quantidade DESSE tipo (não o total de erros do último sync do cliente)
df_atual["qtd_tipo_predominante"] = df_atual["tenant"].map(
    lambda t: predominantes.get(t, {}).get("quantidade_predominante")
)
df_atual["data_tipo_erro"] = df_atual["tenant"].map(lambda t: predominantes.get(t, {}).get("coletado_em"))
# Quantidade de erros do último sync: soma de todos os tipos desse sync
df_atual["qtd_erros_ultimo_sync"] = df_atual["tenant"].map(lambda t: predominantes.get(t, {}).get("quantidade_total"))
# Geometria do conflito_timespan (subtítulo do "Erro predominante"), só quando é esse o tipo predominante
geometrias = carregar_geometrias_cacheado(credenciais_sheets())
df_atual["geometria_conflito"] = [
    geometrias.get(t) if tipo == "conflito_timespan" else None
    for t, tipo in zip(df_atual["tenant"], df_atual["tipo_erro_predominante"])
]
# Só para quem está com erro agora: se o último sync deu certo (ou está pendente),
# a coluna fica vazia.
df_atual = regras.so_quando_ultimo_sync_com_erro(
    df_atual, ["tipo_erro_predominante", "qtd_tipo_predominante", "data_tipo_erro", "qtd_erros_ultimo_sync",
                "geometria_conflito"]
)

# Correções da automação (planilha da triagem): só enriquece o detalhe do cliente; sem credencial ou com falha, some
try:
    _resumo_auto, _correcoes_auto = carregar_correcoes(credenciais_sheets())
except dados_correcoes.ErroFonteDados:
    _correcoes_auto = []
correcoes_auto = pd.DataFrame(dados_correcoes.somente_aplicadas(_correcoes_auto))
erros_por_sync_todos = regras.erros_por_sync(erros_sync, historico)

ui.cabecalho(ultima_execucao.tz_convert(dados.FUSO_COLETA), (agora - ultima_execucao) / pd.Timedelta(hours=1),
             atrasada=agora - ultima_execucao > INTERVALO_COLETA * 2)
col_usuario, col_recarregar, col_sair = st.columns([6.4, 1.6, 1], vertical_alignment="center")
if usuario:
    col_usuario.markdown(f"<div class='ms-usuario'>Conectado como <b>{usuario}</b></div>", unsafe_allow_html=True)
    col_sair.button("Sair", on_click=autenticacao.sair, width="stretch")
col_recarregar.button("↻ Recarregar dados", on_click=recarregar, width="stretch",
                      help="Busca os dados mais recentes agora (normalmente atualizam sozinhos a cada 10 min)")

aba_status, aba_erros, aba_automacao = st.tabs(["Status", "Erros", "Automação"])
with aba_status:
    sub_atual, sub_mapa, sub_detalhe = st.tabs(["Visão atual", "Mapa por período", "Detalhe do cliente"])

# =============================================================================
# Aba 1 — Status (sub-abas: Visão atual, Mapa por período e Detalhe do cliente)
# =============================================================================

with sub_atual:
    ui.intro("<b>Como está a integração de cada cliente agora?</b> Cada cliente é classificado pelo estado do seu "
             "<b>último sync</b> com o Sankhya. Os cartões contam quantos clientes estão em cada estado (passe o mouse "
             "para ver a regra) e a tabela abaixo mostra o detalhe de cada um.")
    ui.explicacao_das_colunas()
    contagem = df_atual["estado"].value_counts()
    ui.cartoes_estado(contagem, len(df_atual))

    col_status, col_cliente, col_ordem = st.columns([4, 3, 2.6], vertical_alignment="bottom")
    estados_filtro = col_status.pills(
        "Status", regras.ESTADOS_EXIBICAO, selection_mode="multi",
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
    ui.nota(f"{len(tabela)} de {len(df_atual)} clientes · a ordenação por taxa de erro (7 dias) considera só syncs finalizados (pending fora da conta)"
            " · ⚠️ = a última coleta deste cliente falhou na API")

# =============================================================================
# Mapa por período (sub-aba de Status)
# =============================================================================

with sub_mapa:
    ui.intro("<b>Como cada cliente se comportou ao longo do tempo?</b> Escolha o período e os clientes nos filtros: "
             "o mapa mostra o resultado dos syncs por cliente e dia (ou por semana, em períodos longos). Para ver "
             "todos os syncs de um cliente, use a sub-aba <b>Detalhe do cliente</b>.", tema.ACENTO_EXECUCOES)
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
    else:

        # --- Mapa de calor: clientes x dias (ou x semanas, em períodos longos) ---
        semanal = (fim - inicio).days + 1 > LIMITE_DIAS_MAPA_DIARIO
        eixo_y = dict(title=None, axis=alt.Axis(ticks=False, domain=False, labelPadding=8, labelLimit=240))

        if not semanal:
            ui.secao("Status diário por cliente")
            ui.descricao("em quais dias cada cliente teve erro ou ficou pendente?",
                         "cada linha é um cliente e cada coluna um dia; a célula mostra o <b>último sync daquele dia</b>. "
                         "Quanto mais vermelho no topo, mais problemas no período.")
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
            ui.descricao("quais clientes tiveram mais erros, e em que semanas?",
                         "cada célula é uma semana; a cor é a <b>proporção de syncs com erro</b> entre os finalizados "
                         "(quanto mais escura, mais erros). Em períodos longos o mapa é agrupado por semana para caber.")
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


# =============================================================================
# Detalhe do cliente (sub-aba de Status)
# =============================================================================

with sub_detalhe:
    ui.intro("<b>Como foi o histórico de um cliente específico?</b> Escolha o cliente e o período: os cartões "
             "resumem o estado atual e o período, o gráfico mostra cada sync como um ponto (altura = itens afetados, "
             "cor = status) e a tabela lista todos eles.", tema.ACENTO_EXECUCOES)
    col_cliente_d, col_periodo_d = st.columns([3, 3], vertical_alignment="bottom")
    tenant = col_cliente_d.selectbox("Cliente", sorted(df_atual["tenant"]), key="cliente_detalhe")
    atalho_d = col_periodo_d.segmented_control("Período", list(ATALHOS_PERIODO), default="30 dias",
                                               key="atalho_periodo_detalhe") or "Tudo"
    syncs_todos = historico.loc[historico["tenant"] == tenant].sort_values(["created", "id_sync"], ascending=False)
    fim = agora.date()
    dias_d = ATALHOS_PERIODO[atalho_d]
    inicio = (syncs_todos["created"].min().date() if dias_d is None or syncs_todos.empty
              else fim - pd.Timedelta(days=dias_d - 1).to_pytimedelta())
    syncs = syncs_todos.loc[syncs_todos["created"].dt.date >= inicio]

    resolucao = regras.resolucao_do_cliente(
        correcoes_auto.loc[correcoes_auto["tenant"] == tenant] if len(correcoes_auto) else correcoes_auto,
        erros_por_sync_todos.loc[erros_por_sync_todos["tenant"] == tenant], inicio, fim)
    if resolucao["total"] or resolucao["corrigidos"]:
        pct_resolvido = (f"{resolucao['corrigidos'] / resolucao['total']:.0%} dos erros do período"
                         if resolucao["total"] else "sem erros no período")
    else:
        pct_resolvido = "nenhuma correção no período"
    estado_atual = df_atual.loc[df_atual["tenant"] == tenant, "estado"]
    ultimo_ok = regras.ultimo_sucesso(syncs_todos)
    taxa = regras.taxa_erro(syncs_todos, agora)
    ui.cartoes_metricas([
        ("Status atual", estado_atual.iloc[0] if not estado_atual.empty else "fora da coleta", None,
         tema.cor(estado_atual.iloc[0] if not estado_atual.empty else regras.SEM_SYNC),
         "Responde: como está o cliente agora? Cálculo: estado do ÚLTIMO sync (sucesso, erro, pendente, "
         "pendente com problema ou 7d sem sync). Não depende do período selecionado."),
        ("Taxa de erro (7 dias)", f"{taxa:.0%}" if pd.notna(taxa) else "—", "entre syncs finalizados", None,
         "Responde: com que frequência os syncs recentes dão erro? Cálculo: syncs com erro ÷ syncs finalizados "
         "(sucesso + erro) nos últimos 7 dias. Pendentes não entram na conta."),
        ("Dias seguidos com erro", regras.dias_seguidos_com_erro(syncs_todos), "até o sync mais recente", None,
         "Responde: há quanto tempo o cliente está com problema? Cálculo: dias (UTC) distintos da sequência atual "
         "de syncs com erro, até o mais recente. Zero se o último sync não deu erro."),
        ("Último sucesso", ui.formatar_data_hora(ultimo_ok),
         ui.formatar_ha_quanto((agora - ultimo_ok) / pd.Timedelta(hours=1)) if pd.notna(ultimo_ok) else "nenhum no histórico",
         None, "Responde: quando foi a última vez que este cliente sincronizou com sucesso? "
               "Cálculo: o sync com status sucesso mais recente de todo o histórico (UTC)."),
        ("Syncs no período", len(syncs), f"{inicio:%d/%m} a {fim:%d/%m}", None,
         "Responde: quantos syncs o cliente teve no período filtrado? Cálculo: contagem de syncs criados entre "
         "as datas escolhidas."),
        ("Corrigidos pela automação", f"{resolucao['corrigidos']} de {resolucao['total']}", pct_resolvido,
         tema.ACENTO_CORRECOES,
         "Responde: quanto do erro deste cliente a automação já resolveu? Cálculo: correções aplicadas pela "
         "triagem no período (planilha de correções, só execuções reais) ÷ linhas de erro do cliente no período "
         "(coleta de 4h). As duas fontes medem coisas parecidas, não idênticas: o percentual é uma referência."),
    ])

    if len(resolucao["por_tipo"]):
        ui.secao("Resolvido pela automação, por tipo de erro")
        ui.descricao("de cada tipo de erro deste cliente, quanto a automação já corrigiu?",
                     "<b>Corrigidos</b> são as correções aplicadas pela triagem no período; <b>Linhas de erro</b> são "
                     "os erros registrados nos syncs do período. Tipos que a automação ainda não corrige ficam com zero.")
        tabela_resolucao = resolucao["por_tipo"].rename(columns={
            "tipo": "Tipo de erro", "corrigidos": "Corrigidos", "erros": "Linhas de erro"})
        tabela_resolucao["% resolvido"] = (100 * tabela_resolucao["Corrigidos"] / tabela_resolucao["Linhas de erro"]
                                           ).where(tabela_resolucao["Linhas de erro"] > 0)
        st.dataframe(tabela_resolucao, hide_index=True, width="stretch",
                     column_config={"% resolvido": st.column_config.NumberColumn(format="%.0f%%")})


    linha_tempo = syncs.assign(
        Status=syncs["status"].map(tema.ROTULOS_STATUS),
        Criado=sem_fuso(syncs["created"]),
        Horário=syncs["created"].dt.strftime("%d/%m %H:%M"),
        tempo_total_min=syncs["total_time"] / 60,
    )
    base_linha = alt.Chart(linha_tempo).encode(
        x=alt.X("Criado:T", title=None, axis=alt.Axis(format="%d/%m", grid=False, labelOverlap=True)),
        y=alt.Y("number_of_affected_items:Q", title="Itens afetados", axis=alt.Axis(tickCount=4, domain=False, ticks=False)),
    )
    trilha = base_linha.mark_line(color=tema.BORDA, strokeWidth=2)
    pontos = base_linha.mark_circle(size=110, opacity=1, stroke="white", strokeWidth=2).encode(
        color=alt.Color("Status:N", scale=ESCALA_STATUS),
        tooltip=["Horário:N", "Status:N", alt.Tooltip("number_of_affected_items:Q", title="Itens afetados", format=",.0f"),
                 alt.Tooltip("tempo_total_min:Q", title="Tempo total (min)", format=".1f"), alt.Tooltip("stage:N", title="Etapa")],
    )
    st.altair_chart(tema.configurar_grafico((trilha + pontos).properties(height=260)), width="stretch", theme=None)

    st.dataframe(
        pd.DataFrame({
            "Sync": syncs["id_sync"],
            "Criado": syncs["created"].map(ui.formatar_data_hora),
            "Status": syncs["status"].map(tema.ROTULOS_STATUS),
            "Etapa": syncs["stage"],
            "Itens afetados": syncs["number_of_affected_items"],
            "Tempo total (min)": (syncs["total_time"] / 60).round(1),
            "Tipo": syncs["sync_type"],
        }),
        hide_index=True,
        width="stretch",
        column_config={"Sync": st.column_config.NumberColumn(format="%d"),
                       "Itens afetados": st.column_config.NumberColumn(format="localized")},
    )

# =============================================================================
# Aba 3 — Erros (linhas de erro por período, tipo e cliente)
# =============================================================================

with aba_erros:
    ui.intro("<b>Quanto erro as integrações geram, de que tipo e em quais clientes?</b> Cada \"linha de erro\" é um "
             "registro (colaborador, vínculo, etc.) que falhou em um sync. Use os filtros para acompanhar a evolução "
             "por dia, semana ou mês, ver quais tipos de erro mais pesam e em que clientes eles se concentram.",
             tema.ACENTO_ERROS)

    erros_todos = regras.erros_por_sync(erros_sync, historico)
    mapa_responsavel = mapeamento.carregar()
    erros_todos["responsavel"] = erros_todos["tipo_erro"].map(lambda t: mapeamento.responsavel_do_tipo(t, mapa_responsavel))
    com_registros = historico.loc[historico["number_of_data_items"].notna()]
    if erros_todos.empty or com_registros.empty:
        st.info("Ainda não há erros detalhados coletados. Eles aparecem a cada coleta (a cada 4 horas).")
    else:
        e_min = com_registros["created"].min().date()
        e_max = agora.date()

        def aplicar_atalho_erros():
            dias = ATALHOS_PERIODO.get(st.session_state.get("atalho_periodo_erros"))
            inicio_e = e_min if dias is None else max(e_min, e_max - pd.Timedelta(days=dias - 1).to_pytimedelta())
            st.session_state["periodo_erros"] = (inicio_e, e_max)

        if "periodo_erros" not in st.session_state:
            st.session_state["atalho_periodo_erros"] = "Tudo"
            aplicar_atalho_erros()

        f1, f2, f3 = st.columns([2, 2, 4.8], vertical_alignment="bottom")
        f1.segmented_control("Período", list(ATALHOS_PERIODO), key="atalho_periodo_erros",
                             on_change=aplicar_atalho_erros)
        periodo_e = f2.date_input("Intervalo", key="periodo_erros", min_value=e_min, max_value=e_max,
                                  format="DD/MM/YYYY")
        clientes_e = f3.multiselect("Cliente", sorted(historico["tenant"].unique()), key="clientes_erros",
                                    placeholder="Todos os clientes")
        g1, g2 = st.columns([4.8, 4])
        tipos_e = g1.multiselect("Tipo de erro", sorted(erros_todos["tipo_erro"].unique()), key="tipos_erros",
                                 placeholder="Todos os tipos")
        responsaveis_e = g2.multiselect("Responsável", [r for r in mapeamento.RESPONSAVEIS
                                                        if r in set(erros_todos["responsavel"])],
                                        key="responsaveis_erros", placeholder="Todos")
        if "granularidade_erros" not in st.session_state:
            # histórico longo: semana por padrão (centenas de barras diárias não se leem)
            st.session_state["granularidade_erros"] = "Semana" if (e_max - e_min).days > 60 else "Dia"
        granularidade = st.segmented_control("Agrupar por", list(regras.GRANULARIDADES),
                                             key="granularidade_erros") or "Dia"
        formato_periodo = {"Dia": "%d/%m", "Semana": "%d/%m", "Mês": "%m/%Y"}[granularidade]

        ini_e, fim_e = (periodo_e if len(periodo_e) == 2 else (periodo_e[0], e_max))
        dia_hist = historico["created"].dt.tz_localize(None).dt.normalize()
        hist_e = historico.loc[(dia_hist.dt.date >= ini_e) & (dia_hist.dt.date <= fim_e)]
        dia_erro = erros_todos["created"].dt.tz_localize(None).dt.normalize()
        erros_e = erros_todos.loc[(dia_erro.dt.date >= ini_e) & (dia_erro.dt.date <= fim_e)]
        if clientes_e:
            hist_e = hist_e.loc[hist_e["tenant"].isin(clientes_e)]
            erros_e = erros_e.loc[erros_e["tenant"].isin(clientes_e)]
        if tipos_e:
            erros_e = erros_e.loc[erros_e["tipo_erro"].isin(tipos_e)]
        if responsaveis_e:
            erros_e = erros_e.loc[erros_e["responsavel"].isin(responsaveis_e)]

        registros_e = int(hist_e["number_of_data_items"].sum())
        linhas_e = int(erros_e["quantidade"].sum())
        pct_e = 100 * linhas_e / registros_e if registros_e else None
        linhas_mindsight = int(erros_e.loc[erros_e["responsavel"] == mapeamento.MINDSIGHT, "quantidade"].sum())
        linhas_cliente = int(erros_e.loc[erros_e["responsavel"] == mapeamento.CLIENTE, "quantidade"].sum())
        pct_mindsight = f"{linhas_mindsight / linhas_e:.0%}" if linhas_e else "—"
        pct_cliente = f"{linhas_cliente / linhas_e:.0%}" if linhas_e else "—"
        ui.cartoes_metricas([
            ("Registros processados", f"{registros_e:,}".replace(",", "."), "soma dos syncs do período",
             tema.ACENTO_EXECUCOES,
             "Responde: qual o tamanho do que foi processado? Cálculo: soma de number_of_data_items de todos os "
             "syncs do período e dos clientes filtrados. Cada sync reenvia a base do cliente, então o mesmo "
             "colaborador conta de novo a cada sync."),
            ("Linhas de erro", f"{linhas_e:,}".replace(",", "."), f"em {erros_e['id_sync'].nunique()} syncs",
             tema.ACENTO_ERROS,
             "Responde: quantos registros falharam? Cálculo: soma das linhas de erro (itens afetados e dados de "
             "sync com erro) dos syncs do período. Se o erro não for corrigido, a mesma linha se repete a cada sync."),
            ("% de erro", f"{pct_e:.2f}%".replace(".", ",") if pct_e is not None else "—", "linhas de erro ÷ registros",
             tema.ACENTO_CREDENCIAIS,
             "Responde: que fração do processado deu erro? Cálculo: linhas de erro ÷ registros processados, no "
             "mesmo período e filtros. Compare períodos de mesmo tamanho: um erro que se repete em cascata infla o "
             "número."),
            ("Clientes afetados", int(erros_e["tenant"].nunique()), f"de {hist_e['tenant'].nunique()} com sync",
             tema.ACENTO_CORRECOES,
             "Responde: em quantos clientes houve erro? Cálculo: clientes distintos com ao menos uma linha de erro "
             "no período."),
            ("Cabem à Mindsight", f"{linhas_mindsight:,}".replace(",", "."), f"{pct_mindsight} das linhas · "
             f"Cliente {pct_cliente}", tema.ACENTO_TEMPO,
             "Responde: quanto do erro depende de nós? Cálculo: linhas de erro dos tipos cujo responsável é a "
             "Mindsight (arquivo mapeamento_erros.toml). O restante cabe ao Cliente ou está sem responsável definido."),
        ])
        ui.nota(f"O histórico de erros começa em {e_min:%d/%m/%Y}. Contam todas as linhas de erro: um item que "
                "continua com erro volta a ser contado a cada sync.")

        if erros_e.empty:
            st.info("Nenhum erro no período e filtros selecionados.")
        else:
            todos_tipos = sorted(erros_todos["tipo_erro"].unique())
            cores_erros = graficos.cores_por_categoria(todos_tipos)

            ui.secao(f"Erros por {granularidade.lower()}, por tipo")
            ui.descricao("o volume de erro está subindo ou caindo, e de que tipo é?",
                         "cada barra é um período (dia, semana ou mês, conforme o agrupamento) com o total de linhas "
                         "de erro, dividido por tipo (cada cor um tipo). Passe o mouse para ver os valores.")
            st.altair_chart(graficos.barras_por_dia_e_tipo(
                regras.erros_por_periodo_e_tipo(erros_e, granularidade), cores_erros, formato_periodo,
                "Linhas de erro"), width="stretch", theme=None)

            ui.secao(f"Erros por {granularidade.lower()}, por responsável")
            ui.descricao("quem precisa agir para reduzir o erro?",
                         "é o mesmo total do gráfico acima, dividido por quem precisa agir: <b>Mindsight</b> "
                         "(períodos, vínculos, ações de integração), <b>Cliente</b> (dado cadastral que o cliente "
                         "corrige) ou <b>A definir</b> (tipo ainda sem responsável no mapeamento).")
            cores_responsavel = {mapeamento.MINDSIGHT: tema.ROXO, mapeamento.CLIENTE: tema.ACENTO_EXECUCOES,
                                 mapeamento.A_DEFINIR: "#8A8580"}
            por_resp = regras.erros_por_periodo_e_tipo(erros_e.assign(tipo_erro=erros_e["responsavel"]), granularidade)
            st.altair_chart(graficos.barras_por_dia_e_tipo(por_resp, cores_responsavel, formato_periodo,
                                                           "Linhas de erro"), width="stretch", theme=None)

            ui.secao("% de erro por período")
            ui.descricao("a proporção de erro melhorou, independente do volume processado?",
                         "linhas de erro ÷ registros processados em cada período. Períodos sem registros ficam "
                         "sem ponto.")
            st.altair_chart(graficos.linha_pct_por_periodo(
                regras.erros_e_registros_por_periodo(erros_e, hist_e, granularidade), tema.ACENTO_CREDENCIAIS,
                formato_periodo), width="stretch", theme=None)

            ui.secao("Erros mais frequentes")
            ui.descricao("quais tipos de erro pesam mais?",
                         "cada barra é um tipo de erro e o número é o total de linhas no período. Um único tipo "
                         "costuma concentrar a maior parte do volume.")
            por_tipo_e = erros_e.groupby("tipo_erro")["quantidade"].sum()
            st.altair_chart(graficos.barras_horizontais(por_tipo_e, "Linhas de erro", cores=cores_erros),
                            width="stretch", theme=None)

            ui.secao("Erros por cliente")
            ui.descricao("em quais clientes os erros se concentram?",
                         "cada barra é um cliente (os 20 com mais linhas de erro) e o número é o total no período. "
                         "A tabela abaixo traz todos, com registros processados e % de erro.")
            por_cliente = regras.erros_por_cliente(erros_e, hist_e)
            st.altair_chart(graficos.barras_horizontais(
                por_cliente.head(20).set_index("tenant")["linhas"], "Linhas de erro", cor=tema.ACENTO_ERROS),
                width="stretch", theme=None)

            tabela_cliente = por_cliente.rename(columns={
                "tenant": "Cliente", "registros": "Registros processados", "linhas": "Linhas de erro",
                "pct": "% de erro", "syncs_com_erro": "Syncs com erro",
                "linhas_mindsight": "Linhas Mindsight", "linhas_cliente": "Linhas Cliente"})
            st.dataframe(tabela_cliente, hide_index=True, width="stretch", column_config={
                "Registros processados": st.column_config.NumberColumn(format="%d"),
                "% de erro": st.column_config.NumberColumn(format="%.2f%%"),
            })
            st.download_button("Exportar CSV (contagens)", tabela_cliente.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"erros_por_cliente_{agora:%Y%m%d}.csv", mime="text/csv",
                               key="exportar_erros")
            with st.expander("Tipo de erro por cliente (tabela)"):
                st.dataframe(erros_e.pivot_table(index="tenant", columns="tipo_erro", values="quantidade",
                                                 aggfunc="sum", fill_value=0), width="stretch")

# =============================================================================
# Aba 4 — Automação (indicadores da triagem/automação de
# correção, migrados do antigo dashboard/ do repositório de origem)
# =============================================================================

with aba_automacao:
    credenciais_json = credenciais_sheets()
    try:
        resumo, correcoes = carregar_correcoes(credenciais_json)
    except dados_correcoes.ErroFonteDados as e:
        st.error(f"Não foi possível carregar o relatório do Google Sheets: {e}")
        st.button("Tentar de novo", on_click=recarregar, key="tentar_de_novo_correcoes")
        resumo, correcoes = [], []
    resumo = dados_correcoes.somente_aplicadas(resumo)
    correcoes = dados_correcoes.somente_aplicadas(correcoes)

    if not resumo:
        st.info("A planilha de relatório ainda não tem nenhuma execução publicada.")
    else:
        df_resumo = pd.DataFrame(resumo)
        df_correcoes = pd.DataFrame(correcoes)
        sem_correcoes = df_correcoes.empty
        aviso_sem_correcoes = 'Ainda não há correções detalhadas publicadas (aba "Correcoes").'

        total_corrigido = int(df_correcoes["quantidade"].sum()) if not sem_correcoes else 0
        clientes_corrigidos = int(df_correcoes["tenant"].nunique()) if not sem_correcoes else 0
        execucoes = df_resumo["data_hora_utc"].nunique()
        # Uma duração por execução (o resumo tem uma linha por tenant em cada uma)
        duracoes = pd.Series(dados_correcoes.duracao_por_execucao_min(resumo), dtype=float)
        media_min = f"{duracoes.mean():.1f} min" if not duracoes.empty else "—"

        ui.intro("<b>O que a automação de correção está fazendo?</b> A triagem roda uma vez por dia: detecta os erros "
                 "dos clientes, aplica as correções que consegue e registra o resultado. Aqui você acompanha "
                 "<b>quanto foi corrigido</b>, <b>quanto tempo levou</b>, <b>quais execuções falharam</b> e "
                 "<b>quais clientes ainda não têm credencial</b> para a automação atuar.", tema.ACENTO_CORRECOES)

        ui.cartoes_metricas([
            ("Correções aplicadas (total)", total_corrigido, "no período publicado", tema.ACENTO_CORRECOES,
             "Responde: qual o volume de trabalho que a automação já resolveu? Cálculo: soma da quantidade de "
             "correções de todas as execuções publicadas na planilha (aba Correcoes)."),
            ("Clientes com correção", clientes_corrigidos, None, tema.ACENTO_CREDENCIAIS,
             "Responde: em quantos clientes a automação já atuou? Cálculo: clientes distintos com ao menos "
             "uma correção registrada."),
            ("Execuções registradas", int(execucoes), None, tema.ACENTO_EXECUCOES,
             "Responde: quantas vezes a automação rodou? Cálculo: execuções distintas (data/hora) no resumo."),
            ("Duração média por execução", media_min, None, tema.ACENTO_TEMPO,
             "Responde: quanto tempo uma execução inteira leva? Cálculo: média da duração de cada execução "
             "(todos os clientes juntos), em minutos."),
        ])

        aba_corr, aba_tempo, aba_exec, aba_cred = st.tabs(["Correções", "Tempo", "Execuções", "Credenciais"])

        # ---------------------------------------------------------------- Correções
        with aba_corr:
            if sem_correcoes:
                ui.nota(aviso_sem_correcoes)
            else:
                por_tipo_erro = df_correcoes.groupby("tipo_erro")["quantidade"].sum().sort_values(ascending=False)
                cores_tipos = graficos.cores_por_categoria(por_tipo_erro.index)

                ui.intro("<b>Que erros a automação corrige, quando e em quais clientes?</b> Os gráficos abaixo usam "
                         "só correções <b>efetivamente aplicadas</b>, não os erros que ficaram para revisão manual.",
                         tema.ACENTO_CORRECOES)
                ui.secao("Quais erros estamos corrigindo")
                ui.descricao("qual tipo de erro a automação mais corrige?",
                             "cada barra é um tipo de erro e o número é o total de correções aplicadas. A cor de cada "
                             "tipo é a mesma em todos os gráficos desta aba.")
                st.altair_chart(graficos.barras_horizontais(por_tipo_erro, "Correções", cores=cores_tipos),
                                width="stretch", theme=None)

                ui.secao("Correções por dia")
                ui.descricao("a automação está corrigindo mais ou menos ao longo do tempo?",
                             "cada barra é um dia (UTC) com o total de correções aplicadas; dias sem correção ficam "
                             "no eixo, sem barra.")
                por_dia = regras.agregar_por_dia(df_correcoes, "data_hora_utc", "quantidade", "sum",
                                                 preencher_dias_vazios=True)
                st.altair_chart(graficos.barras_por_dia(por_dia, "Correções", tema.ACENTO_CORRECOES),
                                width="stretch", theme=None)

                ui.secao("Correções por dia, por tipo de erro")
                ui.descricao("o que compõe o total de cada dia?",
                             "é o mesmo total do gráfico acima, dividido por tipo de erro (cada cor um tipo). "
                             "Passe o mouse na barra para ver o tipo e a quantidade.")
                st.altair_chart(graficos.barras_por_dia_e_tipo(
                    regras.agregar_por_dia_e_tipo(df_correcoes, "data_hora_utc", "tipo_erro", "quantidade"),
                    cores_tipos), width="stretch", theme=None)

                ui.secao("Erros corrigidos por cliente")
                ui.descricao("em quais clientes a automação mais atuou?",
                             "cada barra é um cliente e o número é o total de correções aplicadas nele. "
                             "A tabela escondida abaixo abre o total por tipo de erro em cada cliente.")
                por_tenant = df_correcoes.groupby("tenant")["quantidade"].sum().sort_values(ascending=False)
                st.altair_chart(graficos.barras_horizontais(por_tenant, "Correções", cor=tema.ACENTO_CREDENCIAIS),
                                width="stretch", theme=None)
                with st.expander("Tipo de erro por cliente (tabela)"):
                    matriz = df_correcoes.pivot_table(
                        index="tenant", columns="tipo_erro", values="quantidade", aggfunc="sum", fill_value=0)
                    st.dataframe(matriz, width="stretch")

        # -------------------------------------------------------------------- Tempo
        with aba_tempo:
            ui.intro("<b>Quanto tempo a automação leva?</b> Primeiro a execução inteira (todos os clientes juntos, "
                     "em paralelo); depois o tempo de cada cliente sozinho, para achar os mais lentos. "
                     "Tudo em minutos.", tema.ACENTO_TEMPO)
            ui.secao("Tempo de execução por run")
            ui.descricao("quanto dura uma execução da automação e isso está piorando?",
                         "os cartões mostram a execução mais rápida, a mais lenta e a média; o gráfico mostra a "
                         "duração média das execuções de cada dia (UTC). É a duração da execução <b>inteira</b>, "
                         "não a de cada cliente.")
            if duracoes.empty:
                ui.nota("Nenhuma execução com duração registrada ainda.")
            else:
                ui.cartoes_metricas([
                    ("Mais rápida", f"{duracoes.min():.1f} min", None, tema.ACENTO_TEMPO),
                    ("Mais lenta", f"{duracoes.max():.1f} min", None, tema.ACENTO_CORRECOES),
                    ("Média", media_min, None, tema.ACENTO_EXECUCOES),
                ])
                # Uma linha por run, em minutos
                runs = pd.DataFrame({"data_hora_utc": duracoes.index, "duracao_min": duracoes.values})
                duracao_por_dia = regras.agregar_por_dia(runs, "data_hora_utc", "duracao_min", "mean",
                                                         preencher_dias_vazios=True)
                st.altair_chart(graficos.barras_por_dia(duracao_por_dia, "Duração média (min)", tema.ACENTO_TEMPO,
                                                        formato=".1f", detalhe_registros="Execuções no dia"),
                                width="stretch", theme=None)

            ui.secao("Tempo de execução por tenant")
            ui.descricao("quais clientes são os mais lentos para a automação?",
                         "cada barra é a <b>média</b> de quanto tempo o cliente levou sozinho (login incluso), entre as "
                         "execuções registradas. Clientes com poucas execuções têm média pouco representativa.")
            duracao_por_tenant = dados_correcoes.duracao_media_por_tenant(resumo)
            if not duracao_por_tenant:
                ui.nota("Nenhuma execução com duração por tenant registrada ainda.")
            else:
                st.altair_chart(graficos.barras_horizontais(pd.Series(duracao_por_tenant), "Duração média (min)",
                                                            cor=tema.ACENTO_TEMPO, formato=".1f"),
                                width="stretch", theme=None)

        # --------------------------------------------------------------- Execuções
        with aba_exec:
            ui.intro("<b>As execuções da automação estão dando certo?</b> Conta, por cliente, em quantas "
                     "execuções a automação terminou com sucesso e em quantas falhou.", tema.ACENTO_EXECUCOES)
            ui.secao("Sucesso × falha por tenant")
            ui.descricao("em quais clientes a automação mais falha?",
                         "cada linha é um cliente: o trecho verde são as execuções com sucesso e o vermelho as "
                         "falhas (qualquer resultado diferente de sucesso, como login, sessão expirada, limite ou "
                         "falha de processamento). Os clientes com mais falhas ficam no topo.")
            taxas = dados_correcoes.taxa_sucesso_por_tenant(resumo)
            if not taxas:
                ui.nota("Sem dados suficientes ainda.")
            else:
                df_taxas = pd.DataFrame(taxas).T.sort_values("taxa_sucesso_pct")
                df_taxas[["sucesso", "falha"]] = df_taxas[["sucesso", "falha"]].astype(int)
                st.altair_chart(graficos.sucesso_falha_por_tenant(df_taxas), width="stretch", theme=None)
                with st.expander("Taxa de sucesso por tenant (tabela)"):
                    st.dataframe(df_taxas, width="stretch")

        # ------------------------------------------------------------- Credenciais
        with aba_cred:
            ui.intro("<b>A automação consegue atuar em todos os clientes?</b> Para corrigir um erro, a automação "
                     "precisa de credencial do cliente. Aqui você vê quantos clientes ativos já têm credencial "
                     "cadastrada.", tema.ACENTO_CREDENCIAIS)
            ui.secao("Cobertura de credenciais (tenants_credenciais.json)")
            ui.descricao("quantos clientes ativos a automação já alcança?",
                         "compara os clientes ativos no HubSpot com os que têm credencial no arquivo de "
                         "credenciais. A barra mostra a fatia coberta; quem está sem credencial aparece na lista.")
            try:
                cobertura = carregar_cobertura_credenciais_cacheada(credenciais_json)
                falha_cobertura = None
            except dados_correcoes.ErroFonteDados as e:
                cobertura, falha_cobertura = None, e
            if falha_cobertura is not None:
                ui.nota(f"Não foi possível carregar a cobertura de credenciais agora: {falha_cobertura}")
            elif cobertura is None:
                ui.nota("Ainda não publicada -- aparece depois da próxima execução agendada do pipeline.")
            else:
                total = cobertura["total_ativos"]
                com = len(cobertura["com_credencial"])
                sem = len(cobertura["sem_credencial"])
                ui.cartoes_metricas([
                    ("Com credencial", f"{com} / {total}", f"{com / total:.0%} dos clientes ativos" if total else None,
                     tema.ACENTO_CREDENCIAIS),
                    ("Sem credencial", sem, "a automação não consegue atuar nesses clientes" if sem else None,
                     tema.cor("Erro") if sem else tema.cor("Sucesso")),
                ])
                st.altair_chart(graficos.barra_de_cobertura(com, total, tema.ACENTO_CREDENCIAIS),
                                width="stretch", theme=None)
                if cobertura["sem_credencial"]:
                    with st.expander(f"Ver os {sem} tenants sem credencial"):
                        st.write(cobertura["sem_credencial"])

        ui.nota(f"Atualizado em {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} -- cache de 5min.")

ui.rodape("Coleta automática a cada 4h · horários dos syncs em UTC, como no sistema · última coleta no horário de Brasília")
