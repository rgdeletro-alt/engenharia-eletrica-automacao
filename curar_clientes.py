"""Curadoria da lista de bloqueio de nomes de cliente.

Gera CLIENTES.txt a partir da fonte real de clientes e marca o que foi cortado.
Existe porque lista de bloqueio sem curadoria enche o relatorio de alarme falso,
e relatorio que ninguem le nao protege ninguem.

Uso:
    python curar_clientes.py <fonte.json> [saida.txt]

A fonte e um JSON com a chave "clientes", cada item com "nome", "condominio"
e "tokens". O painel deste escritorio usa dashboard_rgd\\dados_painel.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Palavras que nao identificam cliente nenhum: aparecem em descricao de
# servico, em nome de estado/cidade, ou sao nome generico de empreendimento
# repetido no mercado.
#
# Esta lista e a diferenca entre um relatorio de 223 linhas que alguem le e um
# de 45.067 linhas que ninguem le. A primeira versao desta curadoria nao
# filtrava nada disso, e o resultado medido foi exatamente 45.067 alarmes.
#
# CUSTO ASSUMIDO: cortar "place" significa que um empreendimento cujo unico
# nome distintivo seja "Place" nao sera bloqueado por essa palavra. E aceitavel
# porque o nome completo continua na lista; se o cliente so tiver nome
# generico, alguem tem de acrescentar a mao.
RUIDO = {
    # descricao de servico
    "cliente", "clientes", "condominio", "condominios", "cond", "residencial",
    "edificio", "predio", "torre", "torres", "aptos", "unidade", "unidades",
    "obras", "obra", "servico", "servicos", "equipe", "empresas", "empresa",
    "fornecedor", "prestador", "prestadora", "parceria", "revenda",
    "particular", "piscina", "garagens", "garagem", "associacao", "sindicato",
    "sindico", "sindica", "zelador", "zeladora", "engenheira", "engenheiro",
    "revisao", "equipamento", "indicado", "identificado", "especificado",
    "interno", "interna", "concessionaria", "industria", "farmaceutica",
    "saneamento", "eletrico", "eletrica", "carregador", "carregadores",
    "pavilhao", "residencia", "hotel", "usinas", "solar", "seguro",
    # estado e cidade: identifica regiao, nao cliente
    "santa", "catarina", "florianopolis", "blumenau", "itajai", "itapema",
    "joinville", "balneario", "camboriu", "navegantes", "brusque",
    # nome generico de empreendimento, repetido no mercado
    "place", "park", "garden", "city", "life", "home", "club", "prime",
    "village", "residence", "horizon", "tower", "jardins",
}


def carregar_termos_do_autor(raiz: Path) -> set[str]:
    """Le TERMOS-DO-AUTOR.txt: nome e sobrenome de quem publica.

    Existe por um caso concreto: um sobrenome pode ser ao mesmo tempo nome de
    cliente e nome do autor. A LICENSE precisa do nome do autor para valer, e
    a lista de bloqueio acusava a propria LICENSE. A distincao tem de estar no
    codigo, senao a proxima geracao da lista traz o problema de volta.

    O arquivo NAO e versionado: e dado pessoal de quem publica.
    """
    arquivo = raiz / "TERMOS-DO-AUTOR.txt"
    if not arquivo.exists():
        return set()
    return {
        linha.strip().lower()
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.strip().startswith("#")
    }


def curado(nome: str, termos_do_autor: set[str] | None = None) -> bool:
    """Diz se o termo vale como bloqueio, ou se e palavra comum disfarcada."""
    nome = nome.strip()
    if termos_do_autor and nome.lower() in termos_do_autor:
        # Nome do proprio autor nao e vazamento de cliente: e atribuicao.
        return False
    if len(nome) < 5:
        return False
    palavras = re.split(r"[\s/\-]+", nome)
    if any(p.lower().strip(".,()") in RUIDO for p in palavras):
        return False
    if " " in nome:
        # Frase: vale se tiver ao menos uma palavra longa e distintiva.
        return any(len(p) >= 5 for p in palavras)
    # Palavra unica: so vale se for claramente nome proprio. Sem esta regra,
    # um sobrenome comum acusa o proprio arquivo que explica a regra.
    letras = [c for c in nome if c.isalpha()]
    return len(letras) >= 5 and nome[0].isupper() and not nome.isupper()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    fonte = Path(sys.argv[1])
    saida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("CLIENTES.txt")
    dados = json.loads(fonte.read_text(encoding="utf-8"))

    brutos: set[str] = set()
    for c in dados.get("clientes", []):
        for campo in ("nome", "condominio"):
            v = (c.get(campo) or "").strip()
            if v:
                brutos.add(v)
        for t in c.get("tokens") or []:
            t = str(t).strip()
            if t:
                brutos.add(t)
        for campo in ("nome", "condominio"):
            v = c.get(campo) or ""
            for pedaco in re.split(r"[\s\-–()/]+", v):
                p = pedaco.strip(".,")
                if len(p) >= 5:
                    brutos.add(p)

    autor = carregar_termos_do_autor(Path(__file__).resolve().parent)
    ficam = sorted(
        (n for n in brutos if curado(n, autor)), key=lambda s: (-len(s), s)
    )
    cortados = sorted(n for n in brutos if not curado(n, autor))

    linhas = [
        "# Nomes que NAO podem aparecer em repositorio publico.",
        f"# Gerado de {fonte.name} por curar_clientes.py - nao editar a mao.",
        "# Uma linha por termo. Linha com # e comentario.",
        "#",
        "# LIMITE CONHECIDO, e nao e pequeno: este arquivo so bloqueia o que",
        "# esta escrito abaixo. Nome de cliente que nao esteja aqui NAO sera",
        f"# procurado. Foram cortados {len(cortados)} termos por serem palavra",
        "# comum (lista no fim do arquivo). Cliente novo, ou cliente com nome",
        "# generico, tem de ser acrescentado a mao - senao passa.",
        "",
    ]
    linhas += ficam
    linhas += ["", "# --- cortados por serem palavra comum (nao bloqueiam) ---"]
    linhas += [f"# {n}" for n in cortados]
    saida.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    print(f"termos brutos: {len(brutos)}")
    print(f"bloqueiam    : {len(ficam)}")
    print(f"cortados     : {len(cortados)}  (palavra comum; listados no fim do arquivo)")
    print(f"gravado em   : {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
