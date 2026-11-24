"""Baixa a edição oficial, trata os dados e gera o painel de Curitiba."""

import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import urllib.request

from src.tratar_despesas import tratar
from src.gerar_painel_curitiba import gerar_painel

RAIZ = Path(__file__).resolve().parent
NOME = "2026-11-01_Despesas_-_Base_de_Dados.csv"
URL = "https://mid-dadosabertos.curitiba.pr.gov.br/BaseReceitaDespesa/" + NOME
HASH_ESPERADO = "6a3eb604c6184e533891197d3e71a39658db7eef766b029e20bd1f69c39e1982"


def conferir_origem(arquivo):
    resumo = sha256()
    with arquivo.open("rb") as entrada:
        for bloco in iter(lambda: entrada.read(1024 * 1024), b""):
            resumo.update(bloco)
    if resumo.hexdigest() != HASH_ESPERADO:
        raise ValueError("O SHA-256 difere da edição analisada. Confira a versão do CSV de origem.")


def baixar_origem(destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".csv.part")
    try:
        with urllib.request.urlopen(URL, timeout=120) as resposta, temporario.open("wb") as saida:
            shutil.copyfileobj(resposta, saida)
        conferir_origem(temporario)
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="CSV oficial já baixado, para execução offline.")
    args = parser.parse_args()
    origem = args.csv or RAIZ / "dados" / "brutos" / NOME
    if args.csv is None and not origem.exists():
        print("Baixando a edição oficial de 01/11/2026...")
        baixar_origem(origem)
    conferir_origem(origem)
    pasta = RAIZ / "dados" / "tratados"
    auditoria = tratar(origem, pasta)
    gerar_painel(pasta / "pagamentos_tratados.csv", pasta / "auditoria_etapa2.json", RAIZ / "index.html")
    print(f'{auditoria["contagens"]["pagamentos_exportados"]} pagamentos. Abra index.html no navegador.')


if __name__ == "__main__":
    main()
