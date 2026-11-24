"""Trata o CSV de despesas de Curitiba para a Etapa 2 (Python 3.10+)."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

INICIO = date(2026, 8, 1)
FIM_EXCLUSIVO = date(2026, 11, 1)
PAGAMENTO = "Pagamento de Empenho"
CENTAVO = Decimal("0.01")
AREAS_POR_FUNCAO = {"10": "Saúde", "12": "Educação"}
CAMPOS = {
    "SIGLA_EMPRESA": "sigla_entidade",
    "EMPRESA": "entidade",
    "CD_ORGAO": "codigo_orgao",
    "DS_ORGAO": "orgao",
    "CD_FUNCAO": "codigo_funcao",
    "DS_FUNCAO": "funcao",
    "CD_SUBFUNCAO": "codigo_subfuncao",
    "DS_SUBFUNCAO": "subfuncao",
    "CD_ACAO": "codigo_acao",
    "DS_ACAO": "acao",
    "CD_CATEGORIA_DESPESA": "codigo_categoria",
    "DS_DESPESA_CATEGORIA": "categoria",
    "CD_GRUPO_DESPESA": "codigo_grupo",
    "DS_GRUPO_DESPESA": "grupo",
    "ANO_EMPENHO": "ano_empenho",
    "NR_EMPENHO": "numero_empenho",
    "NR_PARCELA": "numero_parcela",
}
CAMPOS_TEXTO = {
    "entidade", "orgao", "funcao", "subfuncao", "acao", "categoria", "grupo",
}


def area_do_registro(funcao, subfuncao):
    if (funcao, subfuncao) == ("15", "453"):
        return "Transporte coletivo urbano"
    return AREAS_POR_FUNCAO.get(funcao)


def valor_em_reais(texto):
    # A edição do portal usa vírgula decimal e nenhum separador de milhares.
    if not re.fullmatch(r"-?\d+(?:,\d{1,2})?", texto):
        raise ValueError("valor monetário ausente ou inválido")
    return Decimal(texto.replace(",", ".")).quantize(CENTAVO)


def tratar(origem, destino):
    contagem = Counter(dict.fromkeys((
        "linhas_lidas", "fora_das_areas", "duplicatas_exatas_no_recorte",
        "sem_tipo_de_transacao", "outros_tipos_de_transacao",
        "datas_ausentes_ou_invalidas", "pagamentos_fora_do_periodo",
        "valores_ausentes_ou_invalidos", "pagamentos_com_valor_zero",
        "pagamentos_exportados",
    ), 0))
    tipos_excluidos = Counter()
    textos_vazios = Counter()
    totais = defaultdict(Decimal)
    quantidades = Counter()
    linhas_vistas = set()
    registros = []

    with origem.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.reader(arquivo, delimiter=";", strict=True)
        cabecalho = next(leitor, [])
        colunas = {nome: indice for indice, nome in enumerate(cabecalho)}
        obrigatorias = {*CAMPOS, "DT_TRANSACAO", "TRANSACAO", "VL_PAGO"}
        if ausentes := obrigatorias - colunas.keys():
            raise ValueError(f"Colunas ausentes no CSV: {', '.join(sorted(ausentes))}")

        for linha in leitor:
            contagem["linhas_lidas"] += 1
            if len(linha) != len(cabecalho):
                raise ValueError(f"Registro com tamanho incorreto na linha {leitor.line_num}.")

            funcao = linha[colunas["CD_FUNCAO"]].strip()
            subfuncao = linha[colunas["CD_SUBFUNCAO"]].strip()
            area = area_do_registro(funcao, subfuncao)
            if area is None:
                contagem["fora_das_areas"] += 1
                continue

            # Compara todas as colunas originais antes de selecionar a saída.
            identidade = tuple(linha)
            if identidade in linhas_vistas:
                contagem["duplicatas_exatas_no_recorte"] += 1
                continue
            linhas_vistas.add(identidade)

            tipo = " ".join(linha[colunas["TRANSACAO"]].split())
            if not tipo:
                contagem["sem_tipo_de_transacao"] += 1
                continue
            if tipo != PAGAMENTO:
                contagem["outros_tipos_de_transacao"] += 1
                tipos_excluidos[tipo] += 1
                continue

            try:
                data = date.fromisoformat(linha[colunas["DT_TRANSACAO"]].strip())
            except ValueError:
                contagem["datas_ausentes_ou_invalidas"] += 1
                continue
            if not INICIO <= data < FIM_EXCLUSIVO:
                contagem["pagamentos_fora_do_periodo"] += 1
                continue

            try:
                valor = valor_em_reais(linha[colunas["VL_PAGO"]].strip())
            except ValueError:
                contagem["valores_ausentes_ou_invalidos"] += 1
                continue
            if valor == 0:
                contagem["pagamentos_com_valor_zero"] += 1
                continue

            registro = {}
            for coluna, campo in CAMPOS.items():
                texto = " ".join(linha[colunas[coluna]].split())
                if not texto and campo in CAMPOS_TEXTO:
                    textos_vazios[campo] += 1
                    texto = "Não informado"
                registro[campo] = texto

            mes = data.isoformat()[:7]
            registro.update(data_pagamento=data.isoformat(), mes=mes, area=area,
                            valor_pago_reais=str(valor))
            registros.append(registro)
            contagem["pagamentos_exportados"] += 1
            totais[(mes, area)] += valor
            quantidades[(mes, area)] += 1

    if not registros:
        raise ValueError("Nenhum pagamento encontrado para o recorte de agosto a outubro de 2026.")
    if contagem["linhas_lidas"] != sum(v for k, v in contagem.items() if k != "linhas_lidas"):
        raise RuntimeError("As contagens de saída não reconciliam com a entrada.")

    destino.mkdir(parents=True, exist_ok=True)
    arquivo_tratado = destino / "pagamentos_tratados.csv"
    campos_saida = ["data_pagamento", "mes", "area", "valor_pago_reais", *CAMPOS.values()]
    with arquivo_tratado.open("w", encoding="utf-8-sig", newline="") as arquivo:
        gravador = csv.DictWriter(arquivo, fieldnames=campos_saida)
        gravador.writeheader()
        gravador.writerows(registros)

    with origem.open("rb") as arquivo:
        hash_origem = sha256()
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            hash_origem.update(bloco)

    auditoria = {
        "arquivo_origem": origem.name,
        "sha256_origem": hash_origem.hexdigest(),
        "periodo": {"inicio": str(INICIO), "fim_exclusivo": str(FIM_EXCLUSIVO)},
        "contagens": dict(contagem),
        "transacoes_excluidas_por_tipo": dict(tipos_excluidos),
        "descricoes_preenchidas": dict(textos_vazios),
        "total_pago_reais": str(sum(totais.values(), Decimal("0.00"))),
        "conferencia_por_mes_e_area": [
            {"mes": mes, "area": area, "pagamentos": quantidades[(mes, area)],
             "valor_pago_reais": str(total)}
            for (mes, area), total in sorted(totais.items())
        ],
    }
    arquivo_auditoria = destino / "auditoria_etapa2.json"
    arquivo_auditoria.write_text(
        json.dumps(auditoria, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return auditoria


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_origem", type=Path, help="CSV original de despesas da Prefeitura.")
    parser.add_argument("--saida", type=Path, default=Path("dados_tratados"))
    args = parser.parse_args()
    auditoria = tratar(args.csv_origem, args.saida)
    print(f'{auditoria["contagens"]["pagamentos_exportados"]} pagamentos exportados para {args.saida}')


if __name__ == "__main__":
    main()
