# RGD — automação para engenharia elétrica

Ferramentas que construí para resolver problemas concretos de projeto,
orçamento e regularização de instalações elétricas. Cada item aqui nasceu de
um trabalho real: o problema apareceu primeiro, o script veio depois.

Engenheiro eletricista, Santa Catarina. Este repositório é o registro técnico
do método — o código que dá para reusar, sem nenhum dado de cliente.

---

> ### 🐝 Colmeia aberta: deixe o seu recado
>
> A aba [**Issues**](../../issues) está aberta para **recado** e **charada**.
> Qualquer pessoa com conta no GitHub pode escrever — não precisa ser técnico.
>
> - **[recado]** — pergunta, sugestão, correção, ou só um oi.
> - **[charada]** — uma pergunta que faz pensar. A resposta fica escondida por
>   um clique, para a graça estar na tentativa.
>
> As regras da casa estão em
> [COMO-FUNCIONA-A-COLMEIA.md](.github/COMO-FUNCIONA-A-COLMEIA.md).
> A principal: **nunca cole senha, token ou chave numa issue.** Recado aqui é
> público e indexado por buscador.

---

## O que tem aqui

| # | Pipeline | Problema de origem |
|---|---|---|
| 1 | [Cálculo de alimentação de carregador veicular](#1-calculo-de-alimentacao-de-carregador-veicular) | Dimensionar derivação e provar conformidade por vaga |
| 2 | [Conversão de prancha digitalizada em CAD editável](#2-conversao-de-prancha-digitalizada-em-cad-editavel) | Projeto antigo só existia em PDF/imagem |
| 3 | [Base de composição de orçamento](#3-base-de-composicao-de-orcamento) | Orçar sem planilha inconsistente e sem item repetido |
| 4 | [Assinatura digital de documento](#4-assinatura-digital-de-documento) | Assinar laudo e proposta sem depender de site de terceiro |
| 5 | [Auditoria de vazamento antes de publicar](#5-auditoria-de-vazamento-antes-de-publicar) | Não vazar cliente nem credencial em repositório público |

---

## 1. Cálculo de alimentação de carregador veicular

**O que resolve.** Cada vaga de garagem tem um comprimento de trajeto
diferente. Calcular queda de tensão vaga por vaga, na mão, é lento e erra.

**Como funciona.** Para cada vaga, o script monta o trajeto por trechos:

```
trajeto = trecho_em_G1 + prumada + trecho_na_garagem
```

e calcula a queda de tensão pela seção do condutor:

```
ΔU = (2 · ρ · L · I) / S          ρ = 0,0172 Ω·mm²/m (cobre)
I  = P / (U · cos φ)              P = 8 kVA, U = 220 V, cos φ = 1
```

O critério de aceitação é o da NBR 5410: **ΔU ≤ 4 %** da tensão nominal.
O resultado sai como tabela por vaga — trajeto, corrente, queda em volts,
queda em porcentagem e se atende.

**Exemplo do critério funcionando** (dados de trajeto genéricos):

| trajeto | corrente | ΔU | % | atende |
|---|---|---|---|---|
| 26,75 m | 36,36 A | 4,014 V | 1,82 % | sim |
| 41,68 m | 36,36 A | 6,253 V | 2,84 % | sim |
| 49,50 m | 36,36 A | 7,426 V | 3,38 % | sim |

O que faz o cálculo ser útil não é a fórmula — é que ele **reprova**. Um
trajeto de 70 m com o mesmo cabo passaria de 4 % e o script diria "não
atende", forçando o aumento de seção.

**Normas aplicadas no dimensionamento completo:**

- **NBR 5410** — instalações elétricas de baixa tensão (queda de tensão,
  proteção contra sobrecorrente e residual);
- **NBR 17019** — instalação de sistemas de abastecimento de veículos
  elétricos (SAVE);
- **IN 23 do CBMSC** — exigência estadual para SAVE (seccionamento de
  emergência);
- **norma da concessionária** — requisitos de conexão de recarga veicular.

**Detalhe que muda o resultado.** O DR de 40 A **não** incorpora proteção
contra sobrecorrente, conforme a NBR 5410. Quem protege é o disjuntor
bipolar 40 A curva C associado a ele. Dimensionar só pelo DR é um erro que
passa despercebido porque o valor "parece" o mesmo.

---

## 2. Conversão de prancha digitalizada em CAD editável

**O que resolve.** Projeto preventivo antigo, ou prancha que só existe como
foto de tela, precisa voltar a ser desenho editável.

**Como funciona.** Extração das figuras do PDF, classificação por grupo,
lançamento em CAD por automação e conferência do resultado por plotagem —
não por captura de tela.

**Duas regras que custaram retrabalho e ficaram permanentes:**

**A tela mente, a plotagem não.** Depois de editar texto ou criar entidade por
automação, a tela continua mostrando o estado antigo. `Regen` resolve o
repaint, mas captura de tela de canvas acelerado volta em branco. A
conferência de verdade é **plotar para PDF e rasterizar** — a plotagem relê o
banco do desenho e é a fonte da verdade.

**Nunca aprovar tamanho ou posição no olho.** Medir o `BoundingBox` de cada
texto e comparar com o enquadramento que o contém. Foi assim que apareceu uma
nota de 281 mm numa caixa de 271 mm, que ia até 595 mm numa folha de 594 mm —
visivelmente "quase certo", e errado.

**Model sempre em escala real** (1 unidade = 1 mm). A escala de apresentação
é da viewport, e o campo de escala do selo tem de casar com ela.

---

## 3. Base de composição de orçamento

**O que resolve.** Orçamento de obra elétrica sem item repetido, sem dois
códigos para o mesmo material e sem linha que "parece" certa mas aponta para
o item errado.

**Estrutura.** Banco de materiais e banco de serviços com código estável, e
uma tabela de composição que liga serviço a material. O orçamento é gerado a
partir dessa base, nunca digitado solto.

**Três decisões que sustentam o resto:**

**Um código por linha, quantidade somada por local.** Não existe "ITEM
REPETIDO": o mesmo código aparece uma vez, com a quantidade somada entre
térreo, garagem 1 e garagem 2.

**Descrição de item existente não se altera.** Se a descrição está
desatualizada, corrige-se o cadastro, não a linha do orçamento. Alterar a
descrição na linha quebra o histórico e a rastreabilidade do preço.

**Item novo se cadastra na obra, não só na base mãe.** Um código que existe
só na base central e não na planilha da obra faz a linha apontar para o item
errado em silêncio — o orçamento soma um preço que não é o daquele material.

**Conferência de integridade** antes de fechar: contagem de itens da obra
contra a base mãe, procura de código duplicado, e validação de que toda linha
tem descrição, unidade e preço.

---

## 4. Assinatura digital de documento

**O que resolve.** Assinar laudo, proposta ou contrato com certificado
próprio, em lote, sem subir documento para serviço de terceiro.

**Como funciona.** Assinatura com certificado A1/A3, com a senha fornecida em
tempo de execução — nunca embutida no código nem em arquivo de configuração
versionado.

**A regra que não se negocia.** Senha de certificado é obtida na hora, por
entrada do usuário ou por cofre do sistema operacional. Não existe versão
deste código com a senha escrita dentro. Um `.env` que entra no repositório é
uma chave privada publicada.

---

## 5. Auditoria de vazamento antes de publicar

**O que resolve.** Publicar código de trabalho sem levar junto nome de
cliente, telefone, CPF/CNPJ, caminho da máquina ou credencial.

Este é o item que eu recomendo que qualquer pessoa copie, porque o problema
não é específico de engenharia — é de qualquer pasta de trabalho que acumulou
anos de arquivo.

**O que ele procura:**

| categoria | por que |
|---|---|
| chave privada, token, JWT, chave de nuvem e de IA | acesso direto |
| senha atribuída com valor literal | idem |
| CPF, CNPJ, telefone, e-mail | dado pessoal e de terceiro |
| CREA / ART / RNP | identifica o profissional e o contrato |
| caminho absoluto e nome de usuário do sistema | expõe estrutura e cliente |
| endereço interno, túnel e IP de rede | porta de entrada |
| nome de cliente, a partir de lista gerada da fonte real | o vazamento mais comum |

**O que faz esse scanner diferente de um `grep`:** ele tem **autoteste**. Cada
detector tem um caso real que precisa mordê-lo, e casos negativos que não
podem acusar nada. Na primeira versão, quatro detectores não mordiam e três
categorias roubavam o caso uma da outra — o scanner dizia "limpo" com a
consciência tranquila. O autoteste pegou os três.

> **Regra que eu levo para todo script de conferência:** o teste tem de
> exercitar a **mesma função** que a execução real usa. Testar por um caminho
> e executar por outro é testar nada.

---

## Como este repositório se protege

O repositório **não** foi criado a partir da pasta de trabalho. Ele nasceu
vazio e recebe arquivo escolhido a dedo — porque "varrer e publicar" depende
de o scanner não ter buraco, e scanner com buraco é exatamente o que o
autoteste existe para descobrir.

Medido antes de começar: a árvore de trabalho tinha **2.271 arquivos** com
conteúdo que não pode ser público, em **62.806 ocorrências**, incluindo **77
marcas de credencial real**. Nada disso chegou perto deste repositório.

**Regras de contribuição para quem for mexer:**

1. **Nunca `git add .` nem `git add -A`.** Arquivo entra por nome.
2. **Antes de commitar:** `python varrer_vazamento.py --alvo <pasta>`. Código
   diferente de zero significa que achou — e nada publica até ser tratado.
3. **Credencial nunca no código.** Configuração por variável de ambiente ou
   cofre do sistema. Se você precisa de um valor de exemplo, use placeholder
   óbvio.
4. **Dado de cliente não entra nem como exemplo.** Se precisa ilustrar,
   invente o dado — e diga que é inventado.
5. **Caminho relativo sempre.** Nenhum `C:\...` no código.
6. **`relatorio_vazamento.txt` nunca é versionado.** Ele lista exatamente o
   que há de sensível na máquina; publicá-lo seria publicar o vazamento.

### Usando o scanner

O scanner precisa de duas listas que **não** podem estar versionadas, porque
são específicas de cada máquina e de cada escritório:

| arquivo | o que tem | versionado? |
|---|---|---|
| `CLIENTES.txt` | nomes de cliente e empreendimento que não podem ser procurados | **não** — só o `.exemplo` |
| `TERMOS-LOCAIS.txt` | usuário do sistema, pasta de trabalho, host de túnel | **não** — só o `.exemplo` |

```bash
python varrer_vazamento.py --alvo .                    # varre a pasta atual
python varrer_vazamento.py --alvo src --max-por-arquivo 10
python varrer_vazamento.py --autoteste                 # prova que os detectores mordem
python varrer_vazamento.py --alvo . --excluir caminho/arquivo.py
```

Saída: `0` nada encontrado · `1` achou · `2` erro de uso.

**Se um arquivo de configuração não existir, o scanner avisa que aquela
categoria não foi procurada** — e avisa que isso é um buraco, não um
resultado limpo. Scanner que devolve "limpo" quando não verificou nada é pior
que scanner nenhum.

**`--excluir` é declarado, nunca silencioso.** Todo arquivo pulado sai na
saída. A razão é prática: um mecanismo de exclusão escondido é exatamente a
porta por onde um vazamento passa, e um arquivo de teste de scanner — que
precisa conter exemplo de segredo — é o único caso legítimo de exclusão.

### Sobre a lista de clientes

`curar_clientes.py` gera `CLIENTES.txt` a partir de uma fonte JSON e **corta
palavra comum**, que é o que separa um relatório útil de um inútil. Medido
neste escritório: a lista sem curadoria produzia **45.067 alarmes falsos**;
com curadoria, **223**.

**O limite é real e está escrito no próprio arquivo:** a lista só bloqueia o
que está nela. Cliente novo, ou cliente cujo nome seja palavra genérica, tem
de ser acrescentado à mão. Os termos cortados ficam listados no fim do
`CLIENTES.txt`, para a decisão ser auditável em vez de invisível.

---

## Licença

MIT — ver [LICENSE](LICENSE).
