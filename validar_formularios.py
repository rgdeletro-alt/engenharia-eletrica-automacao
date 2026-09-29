"""Valida os formularios de issue antes de commitar.

Existe porque formulario com YAML invalido NAO aparece no GitHub, e o erro nao
da mensagem: a aba Issues simplesmente mostra a caixa em branco. Voce so
descobre olhando o navegador, depois de publicar.

AS REGRAS ABAIXO FORAM EXTRAIDAS DA DOCUMENTACAO OFICIAL, nao escritas de
memoria. Fonte:
https://raw.githubusercontent.com/github/docs/.../syntax-for-githubs-form-schema.md
(secao "Keys" e "Attributes for <tipo>")

A primeira versao deste validador exigia 'id' em todo campo. A documentacao
diz, literalmente, que 'id' e OPTIONAL:

    | `id` | The identifier for the element, except when `type` is set to
      `markdown`. | {% octicon "x" aria-label="Optional" %} | ...

Ou seja: eu inventei uma exigencia, e por pouco "consertei" formularios que
estavam certos para obedecer ao meu proprio erro. Regra que nao vem de fonte
e regra que faz o autor brigar com a ferramenta.

Uso:
    python validar_formularios.py            # valida .github/ISSUE_TEMPLATE
    python validar_formularios.py --autoteste # prova que o validador reprova YAML ruim

Codigo de saida: 0 tudo valido - 1 achou problema - 2 erro de uso.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERRO: falta o PyYAML. Instale com: pip install pyyaml")
    sys.exit(2)

# Tipos de campo que o GitHub aceita em formulario de issue.
# Fonte: secao "Keys" -> valid values de `type`.
TIPOS_VALIDOS = {
    "markdown", "input", "textarea", "dropdown", "checkboxes",
}

# Atributos OBRIGATORIOS por tipo, conforme a documentacao oficial.
#
# ATENCAO: 'id' NAO esta aqui de proposito. A documentacao o marca como
# Optional. Exigi-lo foi o erro da primeira versao.
ATRIBUTOS_OBRIGATORIOS = {
    "markdown": ("value",),
    "textarea": ("label",),
    "input": ("label",),
    "dropdown": ("label", "options"),
    "checkboxes": ("label", "options"),
}

# Elementos para os quais 'id' faz sentido (a doc exclui apenas markdown).
TIPOS_COM_ID = {"input", "textarea", "dropdown", "checkboxes"}


def validar_formulario(caminho: Path) -> list[str]:
    """Devolve a lista de problemas. Lista vazia significa valido."""
    problemas: list[str] = []
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return [f"YAML invalido: {str(e).splitlines()[0]}"]

    if not isinstance(dados, dict):
        return ["o arquivo nao e um mapa YAML (chave: valor)"]

    # O GitHub recusa formulario sem name, description e body.
    for campo in ("name", "description", "body"):
        if campo not in dados:
            problemas.append(f"falta o campo obrigatorio '{campo}'")

    if "name" in dados and len(str(dados["name"])) > 50:
        problemas.append("'name' passa de 50 caracteres - o GitHub recusa")

    if "description" in dados and len(str(dados["description"])) > 200:
        problemas.append("'description' passa de 200 caracteres")

    body = dados.get("body")
    if body is None:
        return problemas
    if not isinstance(body, list) or not body:
        problemas.append("'body' tem de ser uma lista com pelo menos um campo")
        return problemas

    for i, campo in enumerate(body):
        onde = f"body[{i}]"
        if not isinstance(campo, dict):
            problemas.append(f"{onde}: nao e um mapa")
            continue
        tipo = campo.get("type")
        if tipo not in TIPOS_VALIDOS:
            problemas.append(
                f"{onde}: type '{tipo}' invalido. Aceitos: {sorted(TIPOS_VALIDOS)}"
            )
            continue

        atributos = campo.get("attributes")
        if not isinstance(atributos, dict):
            problemas.append(f"{onde} ({tipo}): falta 'attributes'")
            continue

        if tipo == "markdown":
            if "value" not in atributos:
                problemas.append(f"{onde} (markdown): falta 'value'")
            continue

        # Atributos obrigatorios deste tipo, conforme a documentacao.
        for exigido in ATRIBUTOS_OBRIGATORIOS.get(tipo, ()):
            if not atributos.get(exigido):
                problemas.append(f"{onde} ({tipo}): falta '{exigido}'")

        # 'id' e opcional. So se reclama se existir e estiver vazio.
        ident = atributos.get("id")
        if "id" in atributos and not ident:
            problemas.append(f"{onde} ({tipo}): 'id' presente mas vazio")

        if "validations" in campo and not isinstance(campo["validations"], dict):
            problemas.append(f"{onde}: 'validations' tem de ser mapa")

    # id repetido: a documentacao exige unicidade quando o id e informado.
    ids = [
        c.get("attributes", {}).get("id")
        for c in body
        if isinstance(c, dict) and isinstance(c.get("attributes"), dict)
    ]
    repetidos = {i for i in ids if i and ids.count(i) > 1}
    if repetidos:
        problemas.append(f"id repetido no body: {sorted(repetidos)}")

    return problemas


def validar_config(caminho: Path) -> list[str]:
    """Valida o config.yml das Issues."""
    problemas: list[str] = []
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return [f"YAML invalido: {str(e).splitlines()[0]}"]
    if not isinstance(dados, dict):
        return ["o arquivo nao e um mapa YAML"]
    if "blank_issues_enabled" in dados and not isinstance(
        dados["blank_issues_enabled"], bool
    ):
        problemas.append("'blank_issues_enabled' tem de ser true ou false")
    for i, link in enumerate(dados.get("contact_links") or []):
        if not isinstance(link, dict):
            problemas.append(f"contact_links[{i}]: nao e um mapa")
            continue
        for campo in ("name", "url", "about"):
            if not link.get(campo):
                problemas.append(f"contact_links[{i}]: falta '{campo}'")
        url = str(link.get("url", ""))
        if url and not url.startswith(("http://", "https://")):
            problemas.append(f"contact_links[{i}]: url tem de comecar com https://")
    return problemas


def repositorio_do_git(raiz: Path) -> str | None:
    """Le o remote origin e devolve 'usuario/repo'. None se nao houver remote."""
    import re
    import subprocess

    try:
        r = subprocess.run(
            ["git", "-C", str(raiz), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    url = (r.stdout or "").strip()
    if not url:
        return None
    m = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$", url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def validar_links_do_repo(caminho_config: Path, raiz: Path) -> list[str]:
    """Confere se os links do config.yml apontam para ESTE repositorio.

    Existe por um caso concreto: o config.yml tem o endereco escrito a mao. Se
    o nome do repositorio mudar, os dois botoes da colmeia levam a lugar
    nenhum - e o GitHub nao reclama, porque um link quebrado e so um link.
    """
    problemas: list[str] = []
    repo = repositorio_do_git(raiz)
    if not repo:
        # Sem remote configurado o teste nao tem contra o que comparar. Isto
        # nao e falha, mas tambem nao e aprovacao - e um limite declarado.
        return problemas

    try:
        dados = yaml.safe_load(caminho_config.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return problemas

    for i, link in enumerate(dados.get("contact_links") or []):
        url = str((link or {}).get("url", ""))
        if url and f"github.com/{repo}/" not in url:
            problemas.append(
                f"contact_links[{i}] aponta para outro repositorio: {url}\n"
                f"                 o remote do git e: github.com/{repo}"
            )
    return problemas


def validar_pasta(pasta: Path) -> tuple[int, int]:
    """Valida a pasta inteira. Devolve (arquivos verificados, falhas)."""
    if not pasta.exists():
        print(f"ERRO: pasta nao existe: {pasta}")
        return 0, 1

    arquivos = sorted(pasta.glob("*.yml")) + sorted(pasta.glob("*.yaml"))
    if not arquivos:
        print(f"AVISO: nenhum .yml em {pasta}")
        return 0, 0

    verificados = 0
    falhas = 0
    raiz = pasta.parent.parent  # .github/ISSUE_TEMPLATE -> raiz do repositorio
    repo = repositorio_do_git(raiz)

    for arquivo in arquivos:
        verificados += 1
        if arquivo.name == "config.yml":
            problemas = validar_config(arquivo)
            problemas += validar_links_do_repo(arquivo, raiz)
            rotulo = "config"
        else:
            problemas = validar_formulario(arquivo)
            rotulo = "formulario"
        if problemas:
            falhas += 1
            print(f"  REPROVADO  {rotulo:10} {arquivo.name}")
            for p in problemas:
                print(f"               - {p}")
        else:
            print(f"  OK         {rotulo:10} {arquivo.name}")

    if repo:
        print(f"\n  remote do git: github.com/{repo}")
    else:
        print("\n  AVISO: nenhum remote 'origin' configurado - os links do config.yml")
        print("         NAO foram conferidos contra o repositorio real. Isto e um")
        print("         limite do teste, nao uma aprovacao.")
    return verificados, falhas


# --- Autoteste: prova que o validador reprova o que tem de reprovar ---------

CASOS_RUINS = [
    ("YAML quebrado", "name: [sem fechar\n"),
    (
        "sem body",
        "name: X\ndescription: Y\n",
    ),
    (
        "type invalido",
        "name: X\ndescription: Y\nbody:\n  - type: textarea2\n    attributes:\n      label: L\n",
    ),
    (
        # Este caso substituiu "textarea sem id": a doc diz que id e OPCIONAL,
        # entao o campo sem id esta certo. O que nao pode faltar e o label.
        "textarea sem label",
        "name: X\ndescription: Y\nbody:\n  - type: textarea\n    attributes:\n      description: D\n",
    ),
    (
        "dropdown sem options",
        "name: X\ndescription: Y\nbody:\n  - type: dropdown\n    attributes:\n      id: a\n      label: L\n",
    ),
    (
        "id repetido",
        "name: X\ndescription: Y\nbody:\n"
        "  - type: input\n    attributes:\n      id: a\n      label: L\n"
        "  - type: input\n    attributes:\n      id: a\n      label: M\n",
    ),
    (
        "markdown sem value",
        "name: X\ndescription: Y\nbody:\n  - type: markdown\n    attributes:\n      x: 1\n",
    ),
    (
        "sem name",
        "description: Y\nbody:\n  - type: input\n    attributes:\n      label: L\n",
    ),
    (
        "body vazio",
        "name: X\ndescription: Y\nbody: []\n",
    ),
    (
        "checkboxes sem options",
        "name: X\ndescription: Y\nbody:\n  - type: checkboxes\n    attributes:\n      label: L\n",
    ),
]

# Formularios que TEM de passar. Um validador que reprova tudo e tao inutil
# quanto um que aprova tudo.
CASOS_BONS = [
    (
        "formulario minimo com id",
        "name: Exemplo\ndescription: Um formulario valido\nbody:\n"
        "  - type: markdown\n    attributes:\n      value: oi\n"
        "  - type: textarea\n    attributes:\n      id: a\n      label: L\n",
    ),
    (
        # Prova viva da regra: id ausente e valido na documentacao oficial.
        "formulario SEM id (a doc permite)",
        "name: Exemplo\ndescription: Sem id em campo nenhum\nbody:\n"
        "  - type: input\n    attributes:\n      label: L\n"
        "  - type: textarea\n    attributes:\n      label: M\n",
    ),
]


def autoteste() -> int:
    print("AUTOTESTE do validador de formularios")
    print("=" * 66)
    falhas = 0

    for rotulo, conteudo in CASOS_RUINS:
        tmp = Path("_tmp_autoteste.yml")
        tmp.write_text(conteudo, encoding="utf-8")
        problemas = validar_formulario(tmp)
        tmp.unlink()
        if problemas:
            print(f"  OK    reprovou: {rotulo}")
        else:
            print(f"  FALHA deixou passar: {rotulo}")
            falhas += 1

    for rotulo, conteudo in CASOS_BONS:
        tmp = Path("_tmp_autoteste.yml")
        tmp.write_text(conteudo, encoding="utf-8")
        problemas = validar_formulario(tmp)
        tmp.unlink()
        if problemas:
            print(f"  FALHA reprovou formulario valido ({rotulo}): {problemas}")
            falhas += 1
        else:
            print(f"  OK    aprovou: {rotulo}")

    print("=" * 66)
    if falhas:
        print(f"RESULTADO: {falhas} caso(s) errados. Nao confie neste validador.")
        return 1
    print(f"RESULTADO: {len(CASOS_RUINS) + len(CASOS_BONS)} casos, todos corretos.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", type=Path,
                    default=Path(__file__).resolve().parent / ".github" / "ISSUE_TEMPLATE")
    ap.add_argument("--autoteste", action="store_true")
    args = ap.parse_args()

    if args.autoteste:
        return autoteste()

    print(f"VALIDANDO: {args.pasta}")
    print("=" * 66)
    verificados, falhas = validar_pasta(args.pasta)
    print("=" * 66)
    print(f"{verificados} arquivo(s) verificado(s), {falhas} reprovado(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
