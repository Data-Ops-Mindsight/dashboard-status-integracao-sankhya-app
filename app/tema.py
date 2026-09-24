"""Identidade visual Mindsight 3.0: paleta, CSS global e tema dos gráficos."""

import base64
from pathlib import Path

import regras

PASTA_ASSETS = Path(__file__).resolve().parent / "assets"

# --- Marca ---
ROXO = "#7321E8"
LILAS = "#DCC8FA"
OFF_WHITE = "#FFFAF6"
BRANCO = "#FFFFFF"
GRAFITE = "#181818"
TEXTO_SECUNDARIO = "#6B6560"
BORDA = "#EDE6DF"
TRILHA = "#F1EBE5"

FONTE_TITULO = "'Plus Jakarta Sans', sans-serif"
FONTE_CORPO = "Inter, sans-serif"

# --- Status (semânticas, ajustadas à marca; nunca usam o roxo) ---
# preenchimento: marcas e barras | texto: rótulos sobre branco (contraste >= 5.8:1)
CORES_ESTADO = {
    regras.SEM_SYNC:          {"preenchimento": "#8A8580", "texto": "#5C5752"},
    regras.ERRO:              {"preenchimento": "#C8322F", "texto": "#A8231F"},
    regras.PENDENTE_PROBLEMA: {"preenchimento": "#B54708", "texto": "#8A3406"},
    regras.PENDENTE:          {"preenchimento": "#FF9C3A", "texto": "#8F4A00"},
    regras.SUCESSO:           {"preenchimento": "#1E9E61", "texto": "#11704A"},
}

# Status bruto de um sync (success/error/pending) -> estado visual
ESTADO_DO_STATUS = {"success": regras.SUCESSO, "error": regras.ERRO, "pending": regras.PENDENTE}
ROTULOS_STATUS = {"success": "Sucesso", "error": "Erro", "pending": "Pendente"}

# Rampa sequencial (um só matiz, claro -> escuro) para taxa de erro
RAMPA_ERRO = ["#EDD9D5", "#E8A29D", "#C8322F", "#7E1A17"]

# Glifo sobre a cor (o mapa de calor não depende só de verde x vermelho)
GLIFOS_STATUS = {"Sucesso": "", "Erro": "×", "Pendente": "–"}


def cor(estado, tipo="preenchimento"):
    return CORES_ESTADO[estado][tipo]


def svg_base64(nome):
    conteudo = (PASTA_ASSETS / nome).read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(conteudo).decode()


# Contorno do ícone, como nos fundos do manual da marca
_CONTORNO_ICONE = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 469 478'>"
    "<path d='M0 477.9H112.4L283.4 0H468V477.9H283.4L112.4 117H0V477.9Z' "
    "fill='none' stroke='%23181818' stroke-opacity='0.09' stroke-width='2.5'/></svg>"
)

CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1320px; }}
[data-testid="stHeader"] {{ background: transparent; }}

/* Cabeçalho */
.ms-cabecalho {{
  position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  padding: 26px 30px; margin-bottom: 18px;
  background: {BRANCO}; border: 1px solid {BORDA}; border-radius: 16px;
}}
.ms-cabecalho::after {{
  content: ""; position: absolute; right: -40px; top: -30px; width: 260px; height: 265px;
  background: url("data:image/svg+xml;utf8,{_CONTORNO_ICONE}") no-repeat center / contain;
  pointer-events: none;
}}
.ms-cabecalho .ms-marca {{ display: flex; flex-direction: column; gap: 14px; z-index: 1; }}
.ms-cabecalho .ms-marca img {{ height: 34px; width: auto; max-width: none; margin: 0 !important; align-self: flex-start; }}
.ms-cabecalho h1 {{
  font-family: {FONTE_TITULO}; font-weight: 600; font-size: 1.9rem; line-height: 1.15;
  margin: 0; padding: 0; color: {GRAFITE};
}}
.ms-cabecalho .ms-sub {{ color: {TEXTO_SECUNDARIO}; font-size: .92rem; margin-top: 4px; }}
.ms-coleta {{ z-index: 1; text-align: right; font-size: .85rem; color: {TEXTO_SECUNDARIO}; line-height: 1.5; }}
.ms-coleta b {{ display: block; font-family: {FONTE_TITULO}; font-weight: 600; font-size: 1.15rem; color: {GRAFITE}; }}
.ms-coleta .ms-alerta {{ color: {cor(regras.ERRO, "texto")}; font-weight: 500; }}

/* Rótulo de seção */
.ms-secao {{
  font-family: {FONTE_TITULO}; font-weight: 600; font-size: 1.05rem; color: {GRAFITE};
  margin: 22px 0 8px;
}}
.ms-nota {{ color: {TEXTO_SECUNDARIO}; font-size: .82rem; margin: 4px 0 0; }}

/* Cartões */
.ms-cartoes {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 6px 0 18px; }}
.ms-cartao {{
  background: {BRANCO}; border: 1px solid {BORDA}; border-radius: 12px;
  padding: 14px 16px 14px 18px; position: relative; overflow: hidden;
}}
.ms-cartao::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--cor, {BORDA}); }}
.ms-cartao .ms-rotulo {{ display: flex; align-items: center; gap: 8px; font-size: .85rem; color: {TEXTO_SECUNDARIO}; }}
.ms-cartao .ms-valor {{ font-family: {FONTE_TITULO}; font-weight: 600; font-size: 2rem; line-height: 1.2; color: {GRAFITE}; margin-top: 4px; }}
.ms-cartao .ms-detalhe {{ font-size: .8rem; color: {TEXTO_SECUNDARIO}; }}
.ms-cartao.ms-zerado .ms-valor {{ color: #B9B2AB; }}

/* Selo de status */
.ms-selo {{
  display: inline-flex; align-items: center; gap: 7px; white-space: nowrap;
  padding: 3px 10px 3px 8px; border-radius: 999px; font-size: .82rem; font-weight: 500;
  color: var(--texto); background: color-mix(in srgb, var(--cor) 12%, white);
}}
.ms-ponto {{ width: 8px; height: 8px; border-radius: 50%; background: var(--cor); flex: none; }}

/* Tabela */
.ms-tabela-wrap {{ background: {BRANCO}; border: 1px solid {BORDA}; border-radius: 12px; overflow-x: auto; }}
.ms-tabela {{ width: 100%; border-collapse: collapse; font-size: .88rem; color: {GRAFITE}; }}
.ms-tabela th {{
  text-align: left; font-weight: 500; font-size: .74rem; letter-spacing: .04em; text-transform: uppercase;
  color: {TEXTO_SECUNDARIO}; padding: 12px 14px; border-bottom: 1px solid {BORDA}; background: #FDFAF7;
  white-space: nowrap;
}}
.ms-tabela td {{ padding: 10px 14px; border-bottom: 1px solid #F4EEE8; vertical-align: middle; white-space: nowrap; }}
.ms-tabela tr:last-child td {{ border-bottom: none; }}
.ms-tabela tbody tr:hover td {{ background: #FCF8F4; }}
.ms-tabela .ms-num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.ms-tabela .ms-cliente {{ font-weight: 500; }}
.ms-tabela .ms-quando {{ color: {TEXTO_SECUNDARIO}; font-size: .8rem; }}
.ms-aviso {{ margin-left: 6px; cursor: help; }}

/* Últimos syncs: quadradinhos */
.ms-trilha {{ display: inline-flex; gap: 3px; }}
.ms-quadro {{ width: 12px; height: 12px; border-radius: 3px; background: var(--cor); }}
.ms-quadro.ms-vazio {{ background: transparent; box-shadow: inset 0 0 0 1px {BORDA}; }}

/* Barra de taxa de erro */
.ms-barra {{ display: inline-flex; align-items: center; gap: 8px; }}
.ms-barra .ms-trilho {{ display: block; width: 64px; height: 6px; border-radius: 3px; background: {TRILHA}; overflow: hidden; }}
.ms-barra .ms-preenche {{ display: block; height: 100%; border-radius: 3px; background: {cor(regras.ERRO)}; }}
.ms-barra > span:last-child {{ min-width: 34px; text-align: right; font-variant-numeric: tabular-nums; }}

/* Legenda (HTML, acima dos gráficos) */
.ms-legenda {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: .82rem; color: {GRAFITE}; margin: 0 0 8px; }}
.ms-legenda span {{ display: inline-flex; align-items: center; gap: 6px; }}
.ms-legenda .ms-quadro {{ width: 14px; height: 14px; color: white; font-size: 11px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; line-height: 1; }}

/* Tela de login */
.ms-login {{
  max-width: 460px; margin: 10vh auto 24px; text-align: center;
  background: {BRANCO}; border: 1px solid {BORDA}; border-radius: 16px; padding: 40px 36px 28px;
}}
.ms-login img {{ height: 36px; width: auto; margin: 0 auto 26px !important; display: block; }}
.ms-login h1 {{ font-family: {FONTE_TITULO}; font-weight: 600; font-size: 1.5rem; margin: 0 0 8px; padding: 0; color: {GRAFITE}; }}
.ms-login p {{ color: {TEXTO_SECUNDARIO}; font-size: .92rem; margin: 0; }}
.ms-usuario {{ text-align: right; color: {TEXTO_SECUNDARIO}; font-size: .82rem; padding-top: 6px; }}

.ms-gradiente {{ display: inline-flex; align-items: center; gap: 8px; color: {TEXTO_SECUNDARIO}; }}
.ms-gradiente .ms-faixa {{ width: 140px; height: 10px; border-radius: 3px; }}

/* Rodapé */
.ms-rodape {{
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
  margin-top: 36px; padding-top: 16px; border-top: 1px solid {BORDA};
  color: {TEXTO_SECUNDARIO}; font-size: .8rem;
}}
.ms-rodape img {{ height: 16px; opacity: .85; }}

/* Abas */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ font-family: {FONTE_TITULO}; font-weight: 600; }}
</style>
"""


def configurar_grafico(grafico):
    """Linguagem visual dos gráficos: Inter, grade quase invisível, eixos recessivos."""
    return (
        grafico
        .properties(padding={"left": 24, "top": 4, "right": 8, "bottom": 4})
        .configure(font="Inter", background="transparent")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=TEXTO_SECUNDARIO, titleColor=TEXTO_SECUNDARIO, labelFontSize=11, titleFontSize=11,
            titleFontWeight=500, gridColor="#F1EBE5", domainColor=BORDA, tickColor=BORDA,
        )
        .configure_legend(labelColor=GRAFITE, labelFontSize=12, symbolType="square", symbolSize=120,
                          orient="top", title=None)
    )
