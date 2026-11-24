"""Recria as figuras e o relatório final a partir dos pagamentos tratados."""

from collections import Counter, defaultdict
import csv
from decimal import Decimal
import json
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
)

RAIZ = Path(__file__).resolve().parent
AREAS = ["Saúde", "Educação", "Transporte coletivo urbano"]
MESES = ["2026-08", "2026-09", "2026-10"]
ROTULOS = ["Agosto", "Setembro", "Outubro"]
GRUPOS = ["Outras Despesas Correntes", "Pessoal e Encargos Sociais", "Investimentos"]
CORES = ["#146656", "#3477a1", "#a65f16"]
CATALOGO = "https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe?chave=5DDFFBE8-313B-4D94-A862-73AB74B3817C"
ORIGEM = "https://mid-dadosabertos.curitiba.pr.gov.br/BaseReceitaDespesa/2026-11-01_Despesas_-_Base_de_Dados.csv"
DICIONARIO = "https://mid-dadosabertos.curitiba.pr.gov.br/BaseReceitaDespesa/2025-06-18_Despesas_-_Dicionario_de_Dados.xlsx"


def br(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def dinheiro(valor):
    return "R$ " + br(valor)


def tabela_md(cabecalho, linhas):
    textos = ["| " + " | ".join(cabecalho) + " |", "| " + " | ".join(["---"] * len(cabecalho)) + " |"]
    textos.extend("| " + " | ".join(map(str, linha)) + " |" for linha in linhas)
    return "\n".join(textos)


def gerar():
    with (RAIZ / "dados/tratados/pagamentos_tratados.csv").open(encoding="utf-8-sig", newline="") as arquivo:
        registros = list(csv.DictReader(arquivo))
    auditoria = json.loads((RAIZ / "dados/tratados/auditoria_etapa2.json").read_text(encoding="utf-8"))
    mensal = defaultdict(Decimal)
    composicao = defaultdict(Decimal)
    acoes = defaultdict(Decimal)
    quantidades = Counter()
    for registro in registros:
        valor = Decimal(registro["valor_pago_reais"])
        area, mes = registro["area"], registro["mes"]
        mensal[mes, area] += valor
        composicao[area, registro["grupo"]] += valor
        acoes[area, registro["acao"]] += valor
        quantidades[area] += 1
    totais = {area: sum((mensal[mes, area] for mes in MESES), Decimal(0)) for area in AREAS}
    total = sum(totais.values())
    if total != Decimal(auditoria["total_pago_reais"]) or len(registros) != auditoria["contagens"]["pagamentos_exportados"]:
        raise ValueError("Os valores do relatório divergem da auditoria.")
    for linha in auditoria["conferencia_por_mes_e_area"]:
        if mensal[linha["mes"], linha["area"]] != Decimal(linha["valor_pago_reais"]):
            raise ValueError("Divergência no total por mês e área.")
    totais_mes = [sum(mensal[mes, area] for area in AREAS) for mes in MESES]
    variacao = (totais_mes[-1] / totais_mes[0] - 1) * 100
    grupos_totais = {grupo: sum(composicao[area, grupo] for area in AREAS) for grupo in GRUPOS}

    pasta_figuras = RAIZ / "figuras"
    pasta_figuras.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.spines.left": False, "axes.spines.bottom": False})
    fig, ax = plt.subplots(figsize=(10.5, 4))
    fundo = [0.0] * 3
    for area, cor in zip(AREAS, CORES):
        valores = [float(mensal[mes, area] / 1_000_000) for mes in MESES]
        ax.bar(ROTULOS, valores, bottom=fundo, label=area, color=cor, width=.52)
        fundo = [a + b for a, b in zip(fundo, valores)]
    for i, valor in enumerate(totais_mes):
        ax.text(i, float(valor / 1_000_000) + 10, br(valor / 1_000_000, 1), ha="center", weight="bold")
    ax.set_ylabel("Valor bruto pago (R$ milhões)")
    ax.set_ylim(0, 720)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda valor, _: br(valor, 0)))
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", ncol=3, fontsize=9)
    fig.tight_layout()
    fig.savefig(pasta_figuras / "evolucao_mensal.png", dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.5, 4))
    esquerda = [0.0] * 3
    for grupo, cor in zip(GRUPOS, ["#146656", "#88b5a3", "#d69b50"]):
        valores = [float(composicao[area, grupo] / totais[area] * 100) for area in AREAS]
        ax.barh(AREAS, valores, left=esquerda, label=grupo, color=cor, height=.5)
        for i, valor in enumerate(valores):
            if valor > 5:
                ax.text(esquerda[i] + valor / 2, i, br(valor, 1) + "%", ha="center", va="center",
                        color="white" if grupo == GRUPOS[0] else "#132a22", fontsize=10, weight="bold")
        esquerda = [a + b for a, b in zip(esquerda, valores)]
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Participação no valor pago de cada área (%)")
    ax.grid(axis="x", alpha=.15)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.19), ncol=3, fontsize=9)
    fig.tight_layout()
    fig.savefig(pasta_figuras / "composicao_despesas.png", dpi=170)
    plt.close(fig)

    introducao = (
        "Este projeto examina a distribuição dos pagamentos municipais de Curitiba em saúde, educação e transporte "
        "coletivo urbano, entre agosto e outubro de 2026. A comparação procura tornar os registros de execução financeira "
        "mais acessíveis e relacioná-los a serviços presentes no cotidiano da população."
    )
    perguntas = (
        "As perguntas orientadoras são identificar a área com maior valor pago, acompanhar a evolução mensal e reconhecer "
        "os grupos e ações orçamentárias de maior participação. A hipótese descritiva de concentração dos pagamentos em "
        "saúde e educação é examinada pelos totais e pela composição observada."
    )
    metodo = (
        "A análise utiliza a edição de 01/11/2026 da Base de receitas e despesas da Secretaria Municipal de Finanças. "
        "O catálogo informa atualização mensal e cobertura de três meses. A unidade de análise é cada evento classificado "
        "como Pagamento de Empenho, com DT_TRANSACAO no período e VL_PAGO válido e diferente de zero. "
        "O processamento seleciona Saúde (função 10), Educação (função 12) e Transportes Coletivos Urbanos "
        "(função 15, Urbanismo, e subfunção 453). Inclui os fundos municipais."
    )
    tratamento = (
        "O CSV original foi lido como UTF-8 com BOM, com separador ponto e vírgula. As duplicatas exatas foram "
        "identificadas comparando todas as colunas de origem. Datas e valores obrigatórios foram validados. "
        "Descrições opcionais vazias recebem Não informado. Nesta edição, todos os pagamentos exportados tinham "
        "esses campos preenchidos. O mês foi derivado da data da transação. Valores foram calculados com Decimal "
        "e centavos inteiros, e identificadores foram mantidos como texto. A auditoria registra o SHA-256 da fonte "
        "e os totais por mês e área."
    )
    ferramentas = (
        "Python e sua biblioteca padrão foram escolhidos para o ETL, a auditoria e a geração do painel por permitirem "
        "execução reproduzível com aritmética decimal. HTML, CSS e JavaScript permitem consultar o painel offline, "
        "filtrar área e mês e explorar as ações. Matplotlib gera as figuras estáticas, e ReportLab compõe este relatório."
    )
    mensal_texto = (
        f"A saúde liderou os pagamentos nos três meses e reuniu {br(totais['Saúde'] / total * 100, 1)}% do total. "
        f"A educação representou {br(totais['Educação'] / total * 100, 1)}%, e o transporte coletivo, "
        f"{br(totais['Transporte coletivo urbano'] / total * 100, 1)}%. O total mensal passou de "
        f"{dinheiro(totais_mes[0])} em agosto para {dinheiro(totais_mes[2])} em outubro, variação nominal de "
        f"{br(variacao, 1)}%. A educação aumentou em cada mês. Saúde e transporte apresentaram trajetórias diferentes, "
        "com queda da saúde em setembro e maior valor do transporte nesse mesmo mês."
    )
    composicao_texto = (
        f"Outras Despesas Correntes somaram {dinheiro(grupos_totais[GRUPOS[0]])}, equivalentes a "
        f"{br(grupos_totais[GRUPOS[0]] / total * 100, 1)}% dos pagamentos. Pessoal e Encargos Sociais "
        f"representaram {br(grupos_totais[GRUPOS[1]] / total * 100, 1)}%, e Investimentos, "
        f"{br(grupos_totais[GRUPOS[2]] / total * 100, 1)}%. No transporte coletivo, os investimentos foram "
        f"{br(composicao[AREAS[2], 'Investimentos'] / totais[AREAS[2]] * 100, 1)}% dos valores pagos. "
        "A educação apresentou maior participação de pessoal que as outras áreas."
    )
    limites = (
        "Os indicadores representam pagamentos brutos em reais correntes, antes da dedução das devoluções. "
        "Consignações, anulações e liquidações têm eventos próprios, excluídos do indicador. O recorte compara duas "
        "funções amplas com uma subfunção de transporte e abrange os registros disponibilizados na edição escolhida. "
        "O prazo entre empenho, liquidação e pagamento pode deslocar despesas entre meses e exercícios. "
        "A amostra temporal cobre três meses e conserva a situação da publicação de 01/11/2026, sujeita a revisões "
        "posteriores. A comparação descreve o fluxo financeiro observado. Avaliar qualidade ou eficiência dos serviços "
        "exige indicadores de atendimento, custos unitários e contexto orçamentário adicionais."
    )
    conclusao = (
        "Os resultados sustentam a hipótese descritiva de concentração em saúde e educação, que juntas corresponderam "
        f"a {br((totais[AREAS[0]] + totais[AREAS[1]]) / total * 100, 1)}% do valor analisado. A composição dos pagamentos "
        "expõe diferenças entre as áreas, especialmente o peso dos investimentos no transporte coletivo. "
        "A rastreabilidade entre CSV, auditoria, gráficos e painel permite conferir essas observações e reutilizar "
        "o procedimento com o recorte explicitado."
    )
    linhas_etl = [
        ["Entrada", "87.868"], ["Fora das áreas", "64.682"],
        ["Duplicatas exatas no recorte", "33"], ["Sem tipo de transação após deduplicação", "9.186"],
        ["Outros tipos de transação", "7.197"], ["Pagamentos descartados por data, valor ou período", "0"],
        ["Pagamentos exportados", br(len(registros), 0)],
    ]
    linhas_totais = [[area, br(quantidades[area], 0), dinheiro(totais[area])] for area in AREAS]
    linhas_totais.append(["Total", br(len(registros), 0), dinheiro(total)])
    linhas_meses = [
        [rotulo] + [dinheiro(mensal[mes, area]) for area in AREAS]
        for mes, rotulo in zip(MESES, ROTULOS)
    ]
    maiores = sorted(acoes.items(), key=lambda item: item[1], reverse=True)[:3]
    linhas_acoes = [[area, acao, dinheiro(valor)] for (area, acao), valor in maiores]

    markdown = "\n\n".join([
        "# Para onde vai o dinheiro de Curitiba?",
        "## Relatório técnico final\n\nAnálise de Dados Governamentais Abertos - 2º Bimestre\n\nPeríodo de agosto a outubro de 2026. Relatório de 24/11/2026.",
        "## 1. Introdução", introducao, perguntas,
        "## 2. Metodologia", metodo, tratamento, ferramentas,
        tabela_md(["Resultado do ETL", "Linhas"], linhas_etl),
        "## 3. Análise visual", "### Distribuição e evolução mensal",
        tabela_md(["Área", "Pagamentos", "Valor bruto pago"], linhas_totais),
        "![Evolução mensal dos pagamentos](figuras/evolucao_mensal.png)",
        tabela_md(["Mês", *AREAS], linhas_meses), mensal_texto,
        "### Composição e ações de maior valor",
        "![Composição dos pagamentos por grupo](figuras/composicao_despesas.png)", composicao_texto,
        tabela_md(["Área", "Ação orçamentária", "Valor pago"], linhas_acoes),
        "As ações são agrupadas pela área e pela descrição orçamentária, somando os pagamentos no período.",
        "## 4. Limitações", limites, "## 5. Conclusões", conclusao,
        "## 6. Reprodução",
        "O README descreve os comandos. Execute `python executar.py` para baixar a edição original, conferir seu SHA-256, "
        "tratar os dados e gerar `index.html`. Use `--csv` com o arquivo de origem para execução offline. "
        "O painel e a auditoria também estão incluídos no repositório.",
        "## 7. Referências",
        f"Prefeitura Municipal de Curitiba. Secretaria Municipal de Finanças. [Base de receitas e despesas]({CATALOGO}). "
        "Metadados consultados na preparação da Etapa 2, em 10/11/2026.",
        f"[CSV original, edição de 01/11/2026]({ORIGEM}). "
        "SHA-256 `" + auditoria["sha256_origem"] + "`.",
        f"[Dicionário de dados, edição de 18/06/2025]({DICIONARIO}).",
    ]) + "\n"
    (RAIZ / "relatorio_tecnico.md").write_text(markdown, encoding="utf-8")

    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(name="CorpoPT", fontName="Helvetica", fontSize=10, leading=14,
                              textColor=colors.HexColor("#253b32"), spaceAfter=9, alignment=TA_LEFT))
    estilos.add(ParagraphStyle(name="TituloPT", fontName="Helvetica-Bold", fontSize=24, leading=28,
                              textColor=colors.HexColor("#10362d"), spaceAfter=14))
    estilos.add(ParagraphStyle(name="SecaoPT", fontName="Helvetica-Bold", fontSize=14, leading=18,
                              textColor=colors.HexColor("#146656"), spaceBefore=10, spaceAfter=9))
    estilos.add(ParagraphStyle(name="TabelaPT", fontName="Helvetica", fontSize=8, leading=10))
    estilos.add(ParagraphStyle(name="PequenoPT", fontName="Helvetica", fontSize=8, leading=11,
                              textColor=colors.HexColor("#52645c"), spaceAfter=7))
    historia = []
    corpo = lambda texto: Paragraph(escape(texto), estilos["CorpoPT"])
    secao = lambda texto: Paragraph(escape(texto), estilos["SecaoPT"])

    def tabela(cabecalho, linhas, larguras):
        valores = [cabecalho, *linhas]
        celulas = [[Paragraph(escape(str(celula)), estilos["TabelaPT"]) for celula in linha] for linha in valores]
        objeto = Table(celulas, colWidths=larguras, repeatRows=1, hAlign="LEFT")
        objeto.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f2e9")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), .6, colors.HexColor("#146656")),
            ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#dce4db")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return objeto

    historia += [
        Paragraph("Para onde vai o dinheiro<br/>de Curitiba?", estilos["TituloPT"]),
        corpo("Relatório técnico final | Análise de Dados Governamentais Abertos | 24/11/2026"),
        secao("1. Introdução"), corpo(introducao), corpo(perguntas),
        secao("2. Metodologia"), corpo(metodo), corpo(tratamento),
        tabela(["Resultado do ETL", "Linhas"], linhas_etl, [13.5 * cm, 3.5 * cm]),
        Paragraph("Todas as 33 duplicatas removidas pertenciam a registros sem tipo de transação.", estilos["PequenoPT"]),
        PageBreak(),
        secao("3. Distribuição e evolução mensal"),
        tabela(["Área", "Pagamentos", "Valor bruto pago"], linhas_totais, [7.4 * cm, 3.1 * cm, 6.5 * cm]),
        Spacer(1, .25 * cm),
        Image(str(pasta_figuras / "evolucao_mensal.png"), width=17 * cm, height=6.48 * cm),
        Paragraph("Figura 1. Pagamentos brutos mensais das três áreas. Elaboração a partir do CSV tratado.", estilos["PequenoPT"]),
        tabela(["Mês", "Saúde", "Educação", "Transporte coletivo"], linhas_meses,
               [2 * cm, 5 * cm, 5 * cm, 5 * cm]),
        Spacer(1, .3 * cm), corpo(mensal_texto),
        PageBreak(),
        secao("4. Composição e ações de maior valor"),
        Image(str(pasta_figuras / "composicao_despesas.png"), width=17 * cm, height=6.48 * cm),
        Paragraph("Figura 2. Composição dos pagamentos de cada área por grupo de despesa.", estilos["PequenoPT"]),
        corpo(composicao_texto),
        tabela(["Área", "Ação orçamentária", "Valor bruto pago"], linhas_acoes,
               [2.2 * cm, 10.8 * cm, 4 * cm]),
        Spacer(1, .25 * cm),
        corpo("As ações são agrupadas pela área e pela descrição orçamentária. O painel permite explorar as cinco "
              "maiores ações de cada seleção, os valores mensais e a composição dos gastos, com filtros de área e mês."),
        PageBreak(),
        secao("5. Limitações"), corpo(limites),
        secao("6. Conclusões"), corpo(conclusao),
        secao("7. Ferramentas e reprodução"), corpo(ferramentas),
        corpo("O README contém os comandos de execução. O comando python executar.py baixa o arquivo original, "
              "confere o SHA-256, realiza o ETL e gera o painel index.html. Os dados tratados, a auditoria e o painel "
              "estão incluídos no repositório. A execução com --csv utiliza a cópia local da edição original."),
        secao("8. Referências"),
        Paragraph(f'Prefeitura Municipal de Curitiba. Secretaria Municipal de Finanças. '
                  f'<link href="{CATALOGO}" color="#146656">Base de receitas e despesas</link>. '
                  f'Metadados consultados em 10/11/2026.', estilos["CorpoPT"]),
        Paragraph(f'<link href="{ORIGEM}" color="#146656">CSV de despesas da edição de 01/11/2026</link>. '
                  f'<link href="{DICIONARIO}" color="#146656">Dicionário de dados de 18/06/2025</link>.',
                  estilos["CorpoPT"]),
        Paragraph("SHA-256 da origem<br/>" + auditoria["sha256_origem"], estilos["PequenoPT"]),
    ]

    def rodape(canvas, documento):
        canvas.setStrokeColor(colors.HexColor("#dce4db"))
        canvas.line(2 * cm, 1.5 * cm, 19 * cm, 1.5 * cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#52645c"))
        canvas.drawString(2 * cm, 1.05 * cm, "Curitiba | Pagamentos de agosto a outubro de 2026")
        canvas.drawRightString(19 * cm, 1.05 * cm, str(documento.page))

    documento = SimpleDocTemplate(
        str(RAIZ / "relatorio_tecnico.pdf"), pagesize=(21 * cm, 29.7 * cm),
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=1.65 * cm, bottomMargin=2 * cm,
        title="Para onde vai o dinheiro de Curitiba? - Relatório técnico",
        author="Projeto de Análise de Dados Governamentais Abertos",
    )
    documento.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    print(f"Relatório e figuras gerados a partir de {len(registros)} pagamentos.")


if __name__ == "__main__":
    gerar()
