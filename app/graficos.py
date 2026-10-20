"""Gráficos Altair da aba "Automação" (sem Streamlit: cada função devolve o gráfico já com o tema)."""

import altair as alt
import pandas as pd

import tema

ROTULO_SUCESSO, ROTULO_FALHA = "Sucesso", "Falha"


def cores_por_categoria(categorias):
    """{categoria: cor}, estável: a ordem é a alfabética, então o mesmo tipo tem a mesma cor em todos os gráficos."""
    ordenadas = sorted(set(categorias))
    paleta = tema.PALETA_CATEGORIAS
    return {c: paleta[i % len(paleta)] for i, c in enumerate(ordenadas)}


OUTROS = "Outros tipos"


def cores_em_destaque(volume, n=None):
    """Cores para muitas categorias sem repetir: só as `n` de maior volume (Series categoria -> volume) recebem
    cor da paleta; as demais ficam cinza. Devolve ({categoria: cor}, [categorias em destaque])."""
    n = tema.N_CATEGORIAS_EM_DESTAQUE if n is None else n
    ordenadas = volume.sort_values(ascending=False, kind="stable")
    destaque = list(ordenadas.index[:n])
    cores = {c: (tema.PALETA_CATEGORIAS[destaque.index(c)] if c in destaque else tema.COR_OUTROS) for c in ordenadas.index}
    return cores, destaque


def agrupar_em_outros(df, coluna, destaque, rotulo=OUTROS):
    """Troca as categorias fora de `destaque` por `rotulo` e soma `valor` (df: ..., coluna, valor)."""
    df = df.assign(**{coluna: df[coluna].where(df[coluna].isin(destaque), rotulo)})
    chaves = [c for c in df.columns if c != "valor"]
    return df.groupby(chaves, as_index=False)["valor"].sum()


def _eixo_dia(df, formato_curto="%d/%m"):
    formato = "%d/%m/%y" if formato_curto == "%d/%m" and df["dia"].nunique() > 300 else formato_curto
    return df.assign(dia_rotulo=df["dia"].dt.strftime(formato))


def barras_por_dia(df_dia, titulo_valor, cor, formato=",.0f", detalhe_registros=None):
    """Barras por dia (eixo dd/mm). Dias sem valor continuam no eixo, só sem barra."""
    tooltip = [alt.Tooltip("dia:T", title="Dia", format="%d/%m/%Y"),
               alt.Tooltip("valor:Q", title=titulo_valor, format=formato)]
    if detalhe_registros:
        tooltip.append(alt.Tooltip("registros:Q", title=detalhe_registros))
    df_dia = _eixo_dia(df_dia)
    dias = df_dia["dia_rotulo"].tolist()
    marca = dict(color=cor, cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
    if len(dias) < 10:
        marca["size"] = 56  # poucos dias: sem barras gigantes
    grafico = alt.Chart(df_dia).mark_bar(**marca).encode(
        x=alt.X("dia_rotulo:N", title=None, sort=dias, scale=alt.Scale(domain=dias),
                axis=alt.Axis(labelAngle=0, labelOverlap=True, ticks=False)),
        y=alt.Y("valor:Q", title=titulo_valor, axis=alt.Axis(tickCount=4, domain=False, ticks=False)),
        tooltip=tooltip,
    ).properties(height=260)
    return tema.configurar_grafico(grafico)


def barras_por_dia_e_tipo(df_dia_tipo, cores, formato="%d/%m", titulo_valor="Correções", titulo_legenda="Tipo de erro"):
    """Barras empilhadas por período (dia, semana ou mês), uma cor por tipo (`cores`: {tipo: cor})."""
    df_dia_tipo = _eixo_dia(df_dia_tipo, formato)
    dias = df_dia_tipo.sort_values("dia")["dia_rotulo"].drop_duplicates().tolist()
    tipos = sorted(df_dia_tipo["tipo"].unique())
    grafico = alt.Chart(df_dia_tipo).mark_bar(size=56 if len(dias) < 10 else alt.Undefined).encode(
        x=alt.X("dia_rotulo:N", title=None, sort=dias, scale=alt.Scale(domain=dias),
                axis=alt.Axis(labelAngle=0, labelOverlap=True, ticks=False)),
        y=alt.Y("valor:Q", title=titulo_valor, axis=alt.Axis(tickCount=4, domain=False, ticks=False)),
        color=alt.Color("tipo:N", title=None,
                        scale=alt.Scale(domain=tipos, range=[cores[t] for t in tipos])),
        tooltip=[alt.Tooltip("dia:T", title="Dia", format="%d/%m/%Y"), alt.Tooltip("tipo:N", title=titulo_legenda),
                 alt.Tooltip("valor:Q", title=titulo_valor, format=",.0f")],
    ).properties(height=260)
    return tema.configurar_grafico(grafico)


def linha_pct_por_periodo(df, cor, formato="%d/%m"):
    """Linha do % de erro por período. `df`: dia, registros, erros, pct (períodos sem registros ficam sem ponto)."""
    df = _eixo_dia(df, formato)
    periodos = df["dia_rotulo"].tolist()
    base = alt.Chart(df).encode(
        x=alt.X("dia_rotulo:N", title=None, sort=periodos, scale=alt.Scale(domain=periodos),
                axis=alt.Axis(labelAngle=0, labelOverlap=True, ticks=False)),
        y=alt.Y("pct:Q", title="% de erro", axis=alt.Axis(tickCount=4, domain=False, ticks=False, format=".1f")),
        tooltip=[alt.Tooltip("dia:T", title="Período", format="%d/%m/%Y"),
                 alt.Tooltip("pct:Q", title="% de erro", format=".2f"),
                 alt.Tooltip("erros:Q", title="Linhas de erro", format=",.0f"),
                 alt.Tooltip("registros:Q", title="Registros", format=",.0f")],
    )
    linha = base.mark_line(color=cor, strokeWidth=2.5, point=alt.OverlayMarkDef(color=cor, size=70, filled=True))
    return tema.configurar_grafico(linha.properties(height=220))


def barras_horizontais(serie, titulo_valor, cor=None, cores=None, formato=",.0f"):
    """Barras horizontais ordenadas (maior em cima), com o valor na ponta.

    `cor`: uma cor para todas; `cores`: {categoria: cor} para colorir cada barra."""
    df = serie.rename("valor").rename_axis("categoria").reset_index().sort_values("valor", ascending=False)
    ordem = df["categoria"].tolist()
    base = alt.Chart(df).encode(
        y=alt.Y("categoria:N", sort=ordem, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=220)),
        x=alt.X("valor:Q", title=titulo_valor, axis=alt.Axis(tickCount=4, domain=False, ticks=False)),
        tooltip=[alt.Tooltip("categoria:N", title="Item"), alt.Tooltip("valor:Q", title=titulo_valor, format=formato)],
    )
    if cores:
        barras = base.mark_bar(cornerRadiusTopRight=5, cornerRadiusBottomRight=5).encode(
            color=alt.Color("categoria:N", legend=None,
                            scale=alt.Scale(domain=ordem, range=[cores[c] for c in ordem])))
    else:
        barras = base.mark_bar(color=cor or tema.ROXO, cornerRadiusTopRight=5, cornerRadiusBottomRight=5)
    rotulos = base.mark_text(align="left", dx=5, color=tema.TEXTO_SECUNDARIO, fontSize=11).encode(
        text=alt.Text("valor:Q", format=formato))
    return tema.configurar_grafico((barras + rotulos).properties(height=max(120, 26 * len(df) + 30)))


def sucesso_falha_por_tenant(df):
    """Barras horizontais empilhadas (sucesso × falha) por tenant. `df`: índice tenant, colunas sucesso e falha."""
    longo = (df[["sucesso", "falha"]].rename(columns={"sucesso": ROTULO_SUCESSO, "falha": ROTULO_FALHA})
             .rename_axis("tenant").reset_index().melt(id_vars="tenant", var_name="resultado", value_name="execucoes"))
    ordem = df.assign(total=df["sucesso"] + df["falha"]).sort_values(["falha", "total"], ascending=False).index.tolist()
    grafico = alt.Chart(longo).mark_bar(size=16, stroke="white", strokeWidth=1).encode(
        y=alt.Y("tenant:N", sort=ordem, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=220)),
        x=alt.X("execucoes:Q", title="Execuções",
                axis=alt.Axis(tickMinStep=1, format="d", domain=False, ticks=False)),
        color=alt.Color("resultado:N", scale=alt.Scale(
            domain=[ROTULO_SUCESSO, ROTULO_FALHA], range=[tema.cor("Sucesso"), tema.cor("Erro")])),
        tooltip=[alt.Tooltip("tenant:N", title="Cliente"), alt.Tooltip("resultado:N", title="Resultado"),
                 alt.Tooltip("execucoes:Q", title="Execuções")],
    ).properties(height=max(120, 26 * len(df) + 30))
    return tema.configurar_grafico(grafico)


def barra_de_cobertura(com, total, cor):
    """Barra única de progresso (com / total)."""
    df = pd.DataFrame({"parte": ["Com credencial", "Sem credencial"], "n": [com, max(total - com, 0)]})
    grafico = alt.Chart(df).mark_bar(height=26, cornerRadius=6).encode(
        x=alt.X("n:Q", stack="zero", axis=None),
        color=alt.Color("parte:N", legend=None, scale=alt.Scale(
            domain=["Com credencial", "Sem credencial"], range=[cor, tema.TRILHA])),
        tooltip=[alt.Tooltip("parte:N", title=""), alt.Tooltip("n:Q", title="Clientes")],
    ).properties(height=40)
    return tema.configurar_grafico(grafico)
