"""Gera o painel offline a partir do CSV validado na Etapa 2."""

import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import json
from pathlib import Path


def gerar_painel(origem, auditoria, destino):
    agrupados = defaultdict(lambda: [0, 0])
    controle = defaultdict(lambda: [0, 0])
    with origem.open(encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            mes, area = linha["mes"], linha["area"]
            centavos = int(Decimal(linha["valor_pago_reais"]) * 100)
            chave = (mes, area, linha["grupo"], linha["acao"])
            agrupados[chave][0] += centavos
            agrupados[chave][1] += 1
            controle[mes, area][0] += centavos
            controle[mes, area][1] += 1

    esperados = {
        (linha["mes"], linha["area"]): [
            int(Decimal(linha["valor_pago_reais"]) * 100), linha["pagamentos"]
        ]
        for linha in json.loads(auditoria.read_text(encoding="utf-8"))["conferencia_por_mes_e_area"]
    }
    if controle != esperados:
        raise ValueError("O CSV e a auditoria da Etapa 2 têm totais diferentes.")
    dados = [
        dict(mes=mes, area=area, grupo=grupo, acao=acao, centavos=valor, quantidade=qtd)
        for (mes, area, grupo, acao), (valor, qtd) in sorted(agrupados.items())
    ]
    template = Path(__file__).with_name("painel_curitiba.template.html").read_text(encoding="utf-8")
    json_seguro = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    destino.write_text(template.replace("__DADOS__", json_seguro), encoding="utf-8")
    print(f"{len(dados)} combinações e {sum(qtd for _, qtd in controle.values())} pagamentos verificados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("auditoria", type=Path)
    parser.add_argument("saida", type=Path)
    args = parser.parse_args()
    gerar_painel(args.csv, args.auditoria, args.saida)
