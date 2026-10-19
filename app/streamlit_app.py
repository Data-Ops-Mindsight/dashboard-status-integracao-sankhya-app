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
MODULOS_LOCAIS = ["senha", "regras", "tema", "graficos", "dados", "dados_correcoes", "componentes", "autenticacao"]
recarga.recarregar_modulos_alterados(MODULOS_LOCAIS)

import autenticacao  # noqa: E402
import componentes as ui  # noqa: E402
import dados  # noqa: E402
import dados_correcoes  # noqa: E402
import graficos  # noqa: E402
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

ui.cabecalho(ultima_execucao.tz_convert(dados.FUSO_COLETA), (agora - ultima_execucao) / pd.Timedelta(hours=1),
             atrasada=agora - ultima_execucao > INTERVALO_COLETA * 2)
col_usuario, col_recarregar, col_sair = st.columns([6.4, 1.6, 1], vertical_alignment="center")
if usuario:
    col_usuario.markdown(f"<div class='ms-usuario'>Conectado como <b>{usuario}</b></div>", unsafe_allow_html=True)
    col_sair.button("Sair", on_click=autenticacao.sair, width="stretch")
col_recarregar.button("↻ Recarregar dados", on_click=recarregar, width="stretch",
                      help="Busca os dados mais recentes agora (normalmente atualizam sozinhos a cada 10 min)")

aba_atual, aba_historico, aba_automacao = st.tabs(["Status atual", "Histórico", "Automação"])

# =============================================================================
# Aba 1 — Status atual
# =============================================================================

with aba_atual:
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
        ("Status atual", estado_atual.iloc[0] if not estado_atual.empty else "fora da coleta", None,
         tema.cor(estado_atual.iloc[0] if not estado_atual.empty else regras.SEM_SYNC)),
        ("Taxa de erro (7 dias)", f"{taxa:.0%}" if pd.notna(taxa) else "—", "entre syncs finalizados"),
        ("Dias seguidos com erro", regras.dias_seguidos_com_erro(syncs_todos), "até o sync mais recente"),
        ("Último sucesso", ui.formatar_data_hora(ultimo_ok),
         ui.formatar_ha_quanto((agora - ultimo_ok) / pd.Timedelta(hours=1)) if pd.notna(ultimo_ok) else "nenhum no histórico"),
        ("Syncs no período", len(syncs), f"{inicio:%d/%m} a {fim:%d/%m}"),
    ])

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
# Aba 3 — Correções aplicadas (indicadores da triagem/automação de
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

        ui.cartoes_metricas([
            ("Correções aplicadas (total)", total_corrigido, "no período publicado", tema.ACENTO_CORRECOES),
            ("Clientes com correção", clientes_corrigidos, None, tema.ACENTO_CREDENCIAIS),
            ("Execuções registradas", int(execucoes), None, tema.ACENTO_EXECUCOES),
            ("Duração média por execução", media_min, None, tema.ACENTO_TEMPO),
        ])

        aba_corr, aba_tempo, aba_exec, aba_cred = st.tabs(["Correções", "Tempo", "Execuções", "Credenciais"])

        # ---------------------------------------------------------------- Correções
        with aba_corr:
            if sem_correcoes:
                ui.nota(aviso_sem_correcoes)
            else:
                por_tipo_erro = df_correcoes.groupby("tipo_erro")["quantidade"].sum().sort_values(ascending=False)
                cores_tipos = graficos.cores_por_categoria(por_tipo_erro.index)

                ui.secao("Quais erros estamos corrigindo")
                st.altair_chart(graficos.barras_horizontais(por_tipo_erro, "Correções", cores=cores_tipos),
                                width="stretch", theme=None)

                ui.secao("Correções por dia")
                por_dia = regras.agregar_por_dia(df_correcoes, "data_hora_utc", "quantidade", "sum",
                                                 preencher_dias_vazios=True)
                st.altair_chart(graficos.barras_por_dia(por_dia, "Correções", tema.ACENTO_CORRECOES),
                                width="stretch", theme=None)
                ui.nota("Total de correções aplicadas em cada dia (UTC).")

                ui.secao("Correções por dia, por tipo de erro")
                st.altair_chart(graficos.barras_por_dia_e_tipo(
                    regras.agregar_por_dia_e_tipo(df_correcoes, "data_hora_utc", "tipo_erro", "quantidade"),
                    cores_tipos), width="stretch", theme=None)
                ui.nota("Mesmo total do gráfico acima, dividido pelo tipo de erro corrigido (UTC).")

                ui.secao("Erros corrigidos por cliente")
                por_tenant = df_correcoes.groupby("tenant")["quantidade"].sum().sort_values(ascending=False)
                st.altair_chart(graficos.barras_horizontais(por_tenant, "Correções", cor=tema.ACENTO_CREDENCIAIS),
                                width="stretch", theme=None)
                with st.expander("Tipo de erro por cliente (tabela)"):
                    matriz = df_correcoes.pivot_table(
                        index="tenant", columns="tipo_erro", values="quantidade", aggfunc="sum", fill_value=0)
                    st.dataframe(matriz, width="stretch")

        # -------------------------------------------------------------------- Tempo
        with aba_tempo:
            ui.secao("Tempo de execução por run")
            ui.nota("Duração da execução INTEIRA (todos os tenants daquele run, em paralelo) -- não confundir "
                    "com o tempo de cada tenant individualmente, mais abaixo.")
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
                ui.nota("Duração média das execuções de cada dia (UTC).")

            ui.secao("Tempo de execução por tenant")
            ui.nota("Média de quanto tempo CADA tenant levou sozinho (login incluso), entre as execuções "
                    "registradas -- ajuda a achar quais tenants são os mais lentos.")
            duracao_por_tenant = dados_correcoes.duracao_media_por_tenant(resumo)
            if not duracao_por_tenant:
                ui.nota("Nenhuma execução com duração por tenant registrada ainda.")
            else:
                st.altair_chart(graficos.barras_horizontais(pd.Series(duracao_por_tenant), "Duração média (min)",
                                                            cor=tema.ACENTO_TEMPO, formato=".1f"),
                                width="stretch", theme=None)

        # --------------------------------------------------------------- Execuções
        with aba_exec:
            ui.secao("Sucesso × falha por tenant")
            taxas = dados_correcoes.taxa_sucesso_por_tenant(resumo)
            if not taxas:
                ui.nota("Sem dados suficientes ainda.")
            else:
                df_taxas = pd.DataFrame(taxas).T.sort_values("taxa_sucesso_pct")
                df_taxas[["sucesso", "falha"]] = df_taxas[["sucesso", "falha"]].astype(int)
                st.altair_chart(graficos.sucesso_falha_por_tenant(df_taxas), width="stretch", theme=None)
                ui.nota("Número de execuções de cada cliente, por resultado. Falha = qualquer resultado diferente "
                        "de sucesso (login, sessão expirada, limite, processamento).")
                with st.expander("Taxa de sucesso por tenant (tabela)"):
                    st.dataframe(df_taxas, width="stretch")

        # ------------------------------------------------------------- Credenciais
        with aba_cred:
            ui.secao("Cobertura de credenciais (tenants_credenciais.json)")
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
