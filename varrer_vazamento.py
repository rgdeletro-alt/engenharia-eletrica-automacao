"""Detector de vazamento: o que NAO pode sair daqui para um repositorio publico.

Regra do escritorio: prosa informa, gate impede. Este arquivo e o gate.

Ele NAO decide o que publicar. Ele mede e reprova. A decisao e humana.

Uso:
    python varrer_vazamento.py                    # varre a workspace inteira
    python varrer_vazamento.py --alvo <pasta>     # varre so uma pasta
    python varrrer_vazamento.py --arquivo <f>     # varre um arquivo (para pre-commit)
    python varrer_vazamento.py --autoteste        # prova que os detectores funcionam

Codigo de saida: 0 nada encontrado - 1 achou algo - 2 erro de uso.

Cada categoria existe por um caso real, e o caso esta escrito ao lado. Categoria
sem caso real e categoria que alguem vai achar que nao serve para nada e apagar.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Categorias. Cada uma com o motivo escrito, porque detector sem motivo morre.
#
# ATENCAO: a ORDEM DESTA LISTA E A PRECEDENCIA. Quando duas categorias casam na
# mesma linha, a de cima fica com o caso e a de baixo nao conta. Por isso a
# ordem e por ESPECIFICIDADE, nao por assunto: a assinatura da chave privada
# vem antes de "SEGREDO" (senao um .pem viraria "senha encontrada"), o token de
# bot vem antes de "TELEFONE" (o id do bot e numerico), e o e-mail vem antes de
# tudo porque e a regra que so acerta o que visa.
#
# Esta ordem custou tres rodadas de autoteste. Ordem de leitura parece razoavel
# e rouba caso: foi assim que um caminho de pasta de usuario virou
# CAMINHO_ABSOLUTO e a categoria USUARIO_DA_MAQUINA nunca disparava.
# ---------------------------------------------------------------------------

CATEGORIAS = [
    # --- mais especifico primeiro ----------------------------------------
    (
        "CHAVE_PRIVADA",
        "bloco de chave privada colado no arquivo",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    (
        "CHAVE_GOOGLE_OU_AWS",
        "chave de nuvem",
        re.compile(r"\b(AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,})\b"),
    ),
    (
        "GITHUB_TOKEN",
        "token de acesso do GitHub",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    (
        "CHAVE_IA",
        "chave de provedor de IA",
        # O hifen entrou na classe depois do autoteste: a chave real do provedor
        # e "sk-proj-...", e o padrao antigo nao mordia nenhuma delas.
        re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9\-_]{20,}\b"),
    ),
    (
        "JWT",
        "token JWT literal (header.payload.signature)",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ),
    (
        "TELEGRAM_OU_SLACK",
        "token de bot",
        # re.I entrou depois do autoteste: o caso real e "api.telegram.org" com
        # T maiusculo. E o \b inicial saiu: em "bot1234567890:" o digito esta
        # colado na palavra "bot", entao nao existe fronteira de palavra ali e
        # o padrao nao mordia - a URL do webhook de bot passava batido.
        re.compile(r"(?i)\d{8,12}:[A-Za-z0-9_\-]{30,}\b"),
    ),
    (
        "EMAIL",
        "e-mail pessoal, expoe pessoa real",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "CPF",
        "CPF: dado pessoal, nao sai em repositorio publico",
        re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"),
    ),
    (
        "CNPJ",
        "CNPJ: identifica a empresa e o cliente",
        re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)"),
    ),
    (
        "USUARIO_DA_MAQUINA",
        "nome do usuario do Windows dentro do codigo",
        # Fica ACIMA de CAMINHO_ABSOLUTO: o caso tipico e
        # "C:\Users\<usuario>\.config", que as duas regras pegam. O que
        # interessa reportar e o nome do usuario, nao "existe um caminho".
        #
        # Este padrao e GENERICO de proposito: procura qualquer
        # "Users\<algo>". Os termos especificos da maquina ficam em
        # TERMOS-LOCAIS.txt, para o scanner servir noutra maquina sem
        # publicar o nome de usuario de quem o escreveu.
        re.compile(r"(?i)\bUsers[\\/]+[A-Za-z0-9._\-]{2,}"),
    ),

    # --- declaracao de senha ---------------------------------------------
    (
        "SEGREDO_PALAVRA_CHAVE",
        "atribuicao de senha com valor que nao parece placeholder",
        # Aceita "senha = valor" e 'senha = "valor"'. Sem a aspa opcional, o
        # caso tipico "senha = \"...\"" caia em SEGREDO e esta categoria
        # nunca disparava - foi o autoteste que expos.
        re.compile(
            r"(?i)\b(senha|password|pwd)\s*[:=]\s*[\"']?"
            r"(?!None\b|''|\"\"|os\.|getenv|input|sys\.|argparse|environ|\w+\()"
            r"[\w!@#$%^&*\-.]{4,}"
        ),
    ),
    (
        "SEGREDO",
        "credencial ou chave literal no codigo",
        re.compile(
            r"(?i)\b("
            r"senha|password|passwd|pwd|token|secret|api[_-]?key|apikey|"
            r"bearer|private[_-]?key|client[_-]?secret|access[_-]?key"
            r")\b\s*[:=]\s*[\"']([^\"'\s]{6,})[\"']"
        ),
    ),

    # --- dado pessoal e identificacao profissional ------------------------
    (
        "REGISTRO_PROFISSIONAL",
        "CREA/ART/RNP: identifica o engenheiro e o contrato",
        # A folga [^\d\n]{0,20} entrou depois do autoteste: o caso tipico e
        # "CREA-SC 000000-0", e o padrao antigo exigia o numero colado na sigla.
        re.compile(r"(?i)\b(CREA|ART|RNP|CAU)\b[^\d\n]{0,20}\d{4,}[\-/]?\d*"),
    ),

    # --- caminho e endereco ----------------------------------------------
    (
        "CAMINHO_ABSOLUTO",
        "caminho desta maquina: expoe usuario, estrutura e nome dos clientes",
        # Generico: qualquer caminho absoluto do Windows que aponte para raiz
        # de usuario ou para pasta de trabalho. O nome exato da pasta de
        # trabalho vai em TERMOS-LOCAIS.txt.
        re.compile(r"(?i)\b[A-Z]:[\\/]{1,2}(?:Users|[A-Za-z0-9 _\-]{3,})"),
    ),
    (
        "HOST_INTERNO",
        "endereco interno, tunel ou IP da rede local",
        re.compile(
            r"(?i)(127\.0\.0\.1:\d+|localhost:\d+|192\.168\.\d+\.\d+|"
            r"100\.\d{1,3}\.\d{1,3}\.\d{1,3}|\.ts\.net|ngrok\.io|tailscale)"
        ),
    ),

    # --- por ultimo: e a regra mais ampla das de dado pessoal -------------
    (
        "TELEFONE",
        "telefone: dado pessoal de cliente ou de terceiro",
        # Exige marcador de telefone (parentese, +55, hifen ou espaco entre
        # grupos). A versao anterior aceitava qualquer sequencia de digitos e
        # roubava o caso do token de bot, que tem 10 digitos, dois pontos e um
        # sufixo. Foi o autoteste que expos.
        re.compile(
            r"(?<![\d\-.])(?:\+?55[\s\-]?)?"
            r"(?:\(?\d{2}\)[\s\-]?\d{4,5}[\s\-]?\d{4}"
            r"|\d{2}[\s\-]\d{4,5}[\s\-]\d{4})"
            r"(?!\d)"
        ),
    ),

    # --- nome de cliente --------------------------------------------------
    # A lista fica em CLIENTES.txt, uma linha por nome, para nao virar
    # um regex gigante aqui dentro e ser facil de manter. O scanner monta
    # o regex a partir do arquivo.
]

# Posicao de cada categoria na lista acima. A ordem E a precedencia: a primeira
# que casa fica com o caso. Pre-computado porque a varredura roda centenas de
# vezes por arquivo e index() dentro do laco seria O(n^2) a toa.
_ORDEM = {categoria: i for i, (categoria, _m, _p) in enumerate(CATEGORIAS)}

def carregar_termos_locais(raiz_do_script: Path) -> dict[str, list[str]]:
    """Le TERMOS-LOCAIS.txt: usuario do sistema, pasta de trabalho e hosts.

    Fica em arquivo, e nao no codigo, por um motivo pratico: este scanner vai
    para repositorio publico, e o nome de usuario da maquina de quem o escreveu
    e exatamente o tipo de dado que ele existe para nao publicar.
    """
    arquivo = raiz_do_script / "TERMOS-LOCAIS.txt"
    if not arquivo.exists():
        return {}
    secoes: dict[str, list[str]] = {}
    secao = None
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("[") and linha.endswith("]"):
            secao = linha[1:-1].upper()
            secoes.setdefault(secao, [])
        elif secao:
            secoes[secao].append(linha)
    return secoes


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

IGNORAR_DIRS = {
    ".git", "__pycache__", "node_modules", "pylibs", ".hf", ".tmp",
    "sessoes", "backup_harness", "backup_pre_publicacao", ".venv", "venv",
    "Temp", "AppData", "Windows", "Program Files", "Program Files (x86)",
}

# Extensoes que valem varrer como texto.
EXTENSOES = {
    ".py", ".js", ".ts", ".ps1", ".psm1", ".bat", ".cmd", ".vbs", ".gs",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".html", ".css", ".sql", ".sh", ".env", ".example",
}

# Arquivos que sao grandes DEMAIS para varrer linha a linha sem custo alto.
TAMANHO_MAX = 2 * 1024 * 1024  # 2 MB


def carregar_clientes(raiz_do_script: Path) -> list[str]:
    """Le CLIENTES.txt (um nome por linha) e devolve a lista limpa."""
    arquivo = raiz_do_script / "CLIENTES.txt"
    if not arquivo.exists():
        return []
    nomes = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            nomes.append(linha)
    return nomes


def regex_clientes(nomes: list[str]):
    """Monta um regex so com todos os nomes, escapados."""
    if not nomes:
        return None
    partes = sorted((re.escape(n) for n in nomes), key=len, reverse=True)
    return re.compile("|".join(partes), re.IGNORECASE)


def regex_termos_locais(secoes: dict[str, list[str]]):
    """Monta um regex com os termos da maquina declarados em TERMOS-LOCAIS.txt."""
    termos = [t for lista in secoes.values() for t in lista]
    if not termos:
        return None
    partes = sorted((re.escape(t) for t in termos), key=len, reverse=True)
    return re.compile("|".join(partes), re.IGNORECASE)


def classificar_linha(linha: str, regex_cli, regex_local=None) -> list[tuple[str, str, str]]:
    """Classifica UMA linha. Devolve [(categoria, motivo, trecho)].

    Esta funcao e o unico caminho de decisao: a varredura de arquivo e o
    autoteste chamam ELA, nao uma copia. A primeira versao deste scanner tinha
    a regra de precedencia so na varredura, e o autoteste aprovava um caso que
    o scanner real classificaria diferente. Detector testado por um caminho e
    usado por outro e detector que mente.
    """
    achados: list[tuple[str, str, str]] = []
    isenta = "vazamento-isento" in linha

    for posicao, (categoria, motivo, padrao) in enumerate(CATEGORIAS):
        m = padrao.search(linha)
        if not m:
            continue
        # Um caso so nao pode ser contado duas vezes por categorias diferentes:
        # isso infla o resumo e faz a categoria mais util nunca aparecer. A mais
        # especifica (declarada antes na lista) fica com o caso; a generica cede.
        if any(
            outro.search(linha)
            for outro_cat, _mo, outro in CATEGORIAS
            if _ORDEM[outro_cat] < posicao
        ):
            continue
        achados.append(
            ("ISENTO" if isenta else categoria, motivo, m.group(0)[:60])
        )

    if regex_cli:
        m = regex_cli.search(linha)
        if m:
            achados.append(
                ("ISENTO" if isenta else "NOME_CLIENTE",
                 "nome de cliente ou empreendimento", m.group(0)[:60])
            )

    if regex_local:
        m = regex_local.search(linha)
        if m:
            achados.append(
                ("ISENTO" if isenta else "TERMO_LOCAL",
                 "nome de usuario, pasta ou host desta maquina", m.group(0)[:60])
            )
    return achados


def varrer_arquivo(caminho: Path, regex_cli, regex_local=None) -> list[tuple[int, str, str, str]]:
    """Devolve [(linha, categoria, motivo, trecho)] para um arquivo."""
    achados: list[tuple[int, str, str, str]] = []
    try:
        if caminho.stat().st_size > TAMANHO_MAX:
            return achados
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return achados

    for numero, linha in enumerate(texto.splitlines(), start=1):
        for categoria, motivo, trecho in classificar_linha(linha, regex_cli, regex_local):
            achados.append((numero, categoria, motivo, trecho))
    return achados


def varrer(caminho: Path, regex_cli, regex_local=None,
           excluidos: list[Path] | None = None) -> dict[Path, list]:
    """Varre um arquivo ou uma arvore.

    Exclusao e DECLARADA, nunca silenciosa: o que for pulado sai na saida.
    Exclusao escondida e indistinguivel de vazamento que passou.
    """
    resultados: dict[Path, list] = {}
    excluidos = [e.resolve() for e in (excluidos or [])]
    if caminho.is_file():
        achados = varrer_arquivo(caminho, regex_cli, regex_local)
        if achados:
            resultados[caminho] = achados
        return resultados

    for arquivo in caminho.rglob("*"):
        if not arquivo.is_file():
            continue
        if arquivo.resolve() in excluidos:
            continue
        if any(parte in IGNORAR_DIRS for parte in arquivo.parts):
            continue
        if arquivo.suffix.lower() not in EXTENSOES:
            continue
        achados = varrer_arquivo(arquivo, regex_cli, regex_local)
        if achados:
            resultados[arquivo] = achados
    return resultados


# ---------------------------------------------------------------------------
# Autoteste: prova que cada detector morde. Caso real, nao caso inventado.
#
# ATENCAO: os valores abaixo sao FALSOS de proposito e tem de continuar
# falsos. Este arquivo vai para repositorio publico, entao um caso de teste
# com valor verdadeiro publica exatamente o que o scanner existe para
# impedir. Aconteceu na primeira versao: a senha real da hospedagem estava
# aqui como exemplo, e foi o proprio scanner que acusou o proprio arquivo.
# Use valor sintetico, e que pareca sintetico.
#
# O segundo item e o que a linha TEM de acusar: uma categoria unica, ou uma
# tupla quando mais de uma regra cobre o mesmo caso honestamente. Exigir
# categoria unica seria exigir que o scanner escondesse uma regra verdadeira
# so para o teste ficar bonito.
# ---------------------------------------------------------------------------

CASOS_DE_TESTE = [
    ('senha = "S3nh4-D3-Exemplo!"', ("SEGREDO_PALAVRA_CHAVE", "SEGREDO")),
    ("token = 'exemplo-nao-e-token-real'", "SEGREDO"),
    ('senha = os.getenv("SENHA_DB")', ()),  # placeholder: NAO pode acusar
    ("-----BEGIN RSA PRIVATE KEY-----", "CHAVE_PRIVADA"),
    (
        "Authorization: Bearer "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJleGVtcGxvIn0.assinaturafalsa",
        "JWT",
    ),
    (
        "https://api.telegram.org/bot1234567890:"
        "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
        "TELEGRAM_OU_SLACK",
    ),
    ("ghp_exemploDeTokenFalsoDoGitHub123", "GITHUB_TOKEN"),
    ("AKIAIOSFODNN7EXAMPLE", "CHAVE_GOOGLE_OU_AWS"),
    ("sk-proj-exemplo-de-chave-falsa-000", "CHAVE_IA"),
    ("CPF de exemplo 123.456.789-09", "CPF"),
    ("CNPJ de exemplo 11.222.333/0001-81", "CNPJ"),
    ("telefone de exemplo (00) 90000-0000", "TELEFONE"),
    ("contato@exemplo.invalid", "EMAIL"),
    ("registro de exemplo CREA-XX 000000-0", "REGISTRO_PROFISSIONAL"),
    (r'caminho = r"C:\Pasta\De\Exemplo\projeto"', "CAMINHO_ABSOLUTO"),
    (r"C:\Users\USUARIO\.config", "USUARIO_DA_MAQUINA"),
    ("http://127.0.0.1:9999/api/exemplo", "HOST_INTERNO"),
    # Host de tunel e TERMO_LOCAL, nao HOST_INTERNO: o valor certo vem do
    # TERMOS-LOCAIS.txt de cada maquina, senao o scanner teria de carregar
    # dentro dele o host real de quem o escreveu. Foi o autoteste que expos
    # a diferenca, ao eu trocar o host real por um sintetico.
    ("https://exemplo.tunel-interno.invalid/painel", "TERMO_LOCAL"),
    # Linhas que NAO podem acusar nada: alarme falso faz o time parar de ler.
    ("PATH_SEGREDO = Path(__file__).parent / 'segredo'", ()),
    ("funcao que soma dois numeros e devolve o total", ()),
]


def autoteste() -> int:
    """Roda cada caso pelo MESMO caminho que a varredura usa. Se nao morder, falha."""
    print("AUTOTESTE dos detectores")
    print("=" * 74)
    raiz = Path(__file__).resolve().parent
    nomes = carregar_clientes(raiz)
    regex_cli = regex_clientes(nomes)

    # O autoteste NAO pode depender de TERMOS-LOCAIS.txt existir: num clone
    # limpo do repositorio ele nao existe, e o teste da categoria TERMO_LOCAL
    # falharia sem haver defeito nenhum no scanner. Foi o que aconteceu. Entao
    # o teste monta o proprio regex, com termos sinteticos.
    regex_local = regex_termos_locais(
        {"USUARIO": ["usuario-de-teste"], "HOST": ["tunel-interno.invalid"]}
    )

    falhas = 0
    for texto, esperado in CASOS_DE_TESTE:
        esperadas = (esperado,) if isinstance(esperado, str) else tuple(esperado)
        acusou = [c for c, _m, _t in classificar_linha(texto, regex_cli, regex_local)]

        if not esperadas:
            # Caso negativo: nao pode acusar NADA. Alarme falso e o que faz o
            # time parar de ler o relatorio, e relatorio que ninguem le nao
            # protege ninguem.
            if not acusou:
                print(f"  OK    {'(nada)':<24} <- {texto[:42]}")
            else:
                print(f"  FALHA {'(nada)':<24} <- {texto[:42]}")
                print(f"        alarme falso: {acusou}")
                falhas += 1
            continue

        if any(c in acusou for c in esperadas):
            print(f"  OK    {'|'.join(esperadas):<24} <- {texto[:42]}")
        else:
            print(f"  FALHA {'|'.join(esperadas):<24} <- {texto[:42]}")
            print(f"        acusou: {acusou or 'nada'}")
            falhas += 1

    print("-" * 74)
    if not nomes:
        print("  AVISO CLIENTES.txt ausente ou vazio: a categoria NOME_CLIENTE")
        print("        nao esta sendo verificada. Isto e um buraco, nao um OK.")
    else:
        print(f"  CLIENTES.txt com {len(nomes)} nome(s) carregado(s).")
        for nome in nomes[:3]:
            linha = f"Orcamento do {nome} - revisao R01"
            acusou = [c for c, _m, _t in classificar_linha(linha, regex_cli, regex_local)]
            if "NOME_CLIENTE" in acusou:
                print(f"  OK    {'NOME_CLIENTE':<24} <- {linha[:42]}")
            else:
                print(f"  FALHA {'NOME_CLIENTE':<24} <- {linha[:42]}")
                print(f"        acusou: {acusou or 'nada'}")
                falhas += 1

    # A isencao tem de aparecer como ISENTO, nunca sumir: isencao escondida
    # e indistinguivel de segredo que passou.
    linha_isenta = 'senha = "x9y8z7w6"  # vazamento-isento: exemplo de manual'
    acusou = [c for c, _m, _t in classificar_linha(linha_isenta, regex_cli, regex_local)]
    if acusou == ["ISENTO"]:
        print(f"  OK    {'ISENTO':<24} <- linha marcada como isenta")
    else:
        print(f"  FALHA {'ISENTO':<24} <- marcada como isenta, acusou {acusou}")
        falhas += 1

    print("=" * 74)
    if falhas:
        print(f"RESULTADO: {falhas} caso(s) NAO morderam. Nao confie neste scanner.")
        return 1
    print(f"RESULTADO: {len(CASOS_DE_TESTE) + len(nomes[:3]) + 1} casos, todos morderam.")
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Detector de vazamento para publicacao.")
    ap.add_argument("--alvo", type=Path, default=Path.cwd(),
                    help="pasta a varrer (padrao: pasta atual)")
    ap.add_argument("--arquivo", type=Path)
    ap.add_argument("--autoteste", action="store_true")
    ap.add_argument("--max-por-arquivo", type=int, default=6)
    ap.add_argument(
        "--excluir", action="append", default=[],
        help="arquivo a pular, repetivel. O que for pulado e declarado na saida.",
    )
    args = ap.parse_args()

    if args.autoteste:
        return autoteste()

    raiz = Path(__file__).resolve().parent
    nomes = carregar_clientes(raiz)
    regex_cli = regex_clientes(nomes)
    secoes_locais = carregar_termos_locais(raiz)
    regex_local = regex_termos_locais(secoes_locais)
    if not nomes:
        print("AVISO: CLIENTES.txt ausente - nomes de cliente NAO serao procurados.")
    if not secoes_locais:
        print("AVISO: TERMOS-LOCAIS.txt ausente - nome de usuario, pasta de")
        print("       trabalho e host desta maquina NAO serao procurados.")
    if not nomes or not secoes_locais:
        print("       Isto e um BURACO no resultado, nao um 'limpo'. Copie os")
        print("       arquivos .exemplo, preencha com os seus valores e rode de novo.")

    alvo = args.arquivo or args.alvo
    if not alvo.exists():
        print(f"ERRO: alvo nao existe: {alvo}")
        return 2

    excluidos = [Path(e) for e in args.excluir]
    resultados = varrer(alvo, regex_cli, regex_local, excluidos)

    # Contagem por categoria: o resumo e o que decide, nao a lista crua.
    por_categoria: dict[str, int] = {}
    for achados in resultados.values():
        for _linha, categoria, _motivo, _trecho in achados:
            por_categoria[categoria] = por_categoria.get(categoria, 0) + 1

    print("=" * 74)
    print(f"ALVO: {alvo}")
    print(f"ARQUIVOS COM ACHADO: {len(resultados)}")
    if excluidos:
        print(f"ARQUIVOS PULADOS POR --excluir ({len(excluidos)}):")
        for e in excluidos:
            print(f"    {e}")
    print("=" * 74)

    if not resultados:
        print("Nada encontrado pelas regras atuais.")
        print("Isto NAO e prova de que esta limpo: e prova de que nada do que")
        print("as regras conhecem apareceu. Regra que nao existe nao acusa.")
        return 0

    print("\nRESUMO POR CATEGORIA (ordenado por quantidade)")
    for categoria, qtd in sorted(por_categoria.items(), key=lambda x: -x[1]):
        motivo = next((m for c, m, _ in CATEGORIAS if c == categoria), "nome de cliente")
        print(f"  {qtd:5}  {categoria:24} {motivo}")

    print("\nDETALHE (ate %d por arquivo)" % args.max_por_arquivo)
    for arquivo, achados in sorted(resultados.items()):
        print(f"\n  {arquivo}")
        for linha, categoria, _motivo, trecho in achados[: args.max_por_arquivo]:
            print(f"    linha {linha:5} [{categoria}] {trecho}")
        if len(achados) > args.max_por_arquivo:
            print(f"    ... e mais {len(achados) - args.max_por_arquivo} "
                  f"(nao truncado em silencio: o total esta acima)")

    print("\n" + "=" * 74)
    print("RESULTADO: ACHOU. Nada publica ate ser tratado.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
