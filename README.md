# Bobina — logística de filamento 3D

Inventário de filamento para impressão 3D: o que tenho, onde está, quanto resta,
quanto custa em cada loja — e um agente que ajuda a arrumar.

Python da biblioteca padrão, **sem dependências**: corre com o `python3` do sistema.
Serve em `:8100` e guarda tudo num SQLite em `~/.local/share/bobina/bobina.db`.

## O que faz

**Pesquisa instantânea.** Escreve-se e a lista filtra — sem Enter, sem botão. O
truque é o léxico (`lexicon.py`): 700+ sinónimos de marcas, materiais, cores e
formatos, em português e inglês. `ASA Azure Preto` encontra um *AzureFilm ASA
Black*; `grey` encontra *Cinzento*; `azu` já chega para a AzureFilm aparecer.
"Azure" é de propósito marca **e** cor — casa com as duas.

**Preços.** Seis lojas (`lojas.py`): Evolt, Core XY e RepRap PT (Portugal),
QIDI EU, Elegoo EU e Amazon. Cada loja recebe o texto tal como foi escrito **mais** as versões em
português e em inglês — a língua soma-se, nunca substitui, para nenhuma loja
ficar de fora só por catalogar na outra. Actualiza sozinho de 24 em 24 horas e
guarda o histórico.

**Colar um link** vale como pesquisa: mete-se o URL do produto na caixa de
procura das lojas e o Bobina vai lê-lo. A Evolt resolve-se pelo *slug* (a
pesquisa da WooCommerce devolve zero mesmo com a página a existir), as Shopify
por `/products/<slug>.js`, e a Amazon pelo **ASIN** do `/dp/…` — em qualquer
domínio, `.com` incluído, porque o ASIN é o mesmo em toda a parte. O preço da
Amazon só entra quando vem em euros: a página devolve a moeda de quem pede, e
guardar dólares num campo somado como euros estragava o €/kg de tudo.

Cada loja tem a sua manha. A Evolt corre WooCommerce, cuja pesquisa casa uma
*substring* contígua do título: `asa black` devolve zero e `asa 1kg black`
devolve sete, porque o "1kg" fica pelo meio — daí pesquisar-se pelo termo mais
selectivo, paginar e filtrar cá com o léxico. A RepRap PT tem plataforma própria
e só responde com o conjunto todo de parâmetros (`terms` sozinho devolve uma
página vazia), mas em troca diz o peso e o diâmetro em badges próprias.

**Fotos.** A foto da loja é guardada em `~/.local/share/bobina/imagens` e servida
por `/api/imagem` — o endereço da loja sozinho não chegava, parte no dia em que
ela mexer nos ficheiros. Usa-se a miniatura que a própria loja serve (7–20 KB em
vez de 300 KB) e só se vai buscar imagens aos domínios das cinco lojas.

**Adicionar.** Um resultado de loja chega ao formulário já preenchido: marca,
material (com a variante — `PETG Matte`, `PLA+`, `PETG CF`), cor, peso convertido
para gramas e a cor em hex. As facetas saem de três fontes, por esta ordem: o
título, a marca que a própria loja declara, e os termos que foram escritos na
pesquisa. A varredura é por **frases** de até três palavras, senão marcas como
"Professional Lab" ou "The Filament" nunca casariam.

**Cores.** Sem foto — ou por preferência — a bobine é **desenhada** em traço e
pintada pelo que está escrito na cor: `dark grey`, `wood ash`, `silk red`,
`purple-blue`, `Pastel Mint Green`, `negro azabache`. São ~290 nomes de cor de
impressão 3D com modificadores (`dark`, `pastel`, `neon`, `matte`, `silk`), e as
cores compostas misturam-se. Dá para escolher à mão por amostra ou por roda RGB,
e voltar ao automático quando se quiser.

**Compras.** Cada bobine guarda onde foi comprada (as seis lojas ou outra
qualquer, à mão), por quanto e quando. O cartão mostra o **€/kg médio** —
ponderado pelo peso, porque a mesma referência pode ter sido comprada em alturas
e lojas diferentes. Adicionar uma bobine que já existe **junta-a ao grupo**: a
comparação é por significado e não por letras, por isso a mesma bobine comprada
como "Black" numa loja e "Preto" noutra fica no mesmo sítio.

**Na impressora.** Cada cartão tem o bico da impressora por baixo da contagem:
cinzento quer dizer que não há nada montado, verde que há. Clicar monta a bobine
que está **mais perto de acabar** (em empate, a mais antiga) — é a que se quer
gastar primeiro —, e clicar outra vez tira todas. Para escolher outra, abre-se o
filamento e marca-se lá a bobine; o cartão acende à mesma, e só apaga quando
nenhuma lá dentro estiver marcada. Podem estar várias ao mesmo tempo, para quem
imprime a duas cores. Não é um estado da bobine: uma bobine montada continua
*aberta*. Ao adicionar uma bobine também se pode marcá-la logo, ao lado da
embalagem — só quando se adiciona uma de cada vez, porque montar três ao mesmo
tempo seria mentira.

**Perguntar pelo estado.** Três chips só com o desenho — o bico, a caixa e a
bobine — deixam na lista o que está **na impressora**, o que ainda tem **caixa**
e o que já **não tem**. Não são interruptores à parte: escrevem o termo na caixa
de pesquisa, e escrever `na impressora`, `com caixa`, `sem caixa` ou `bobina` à
mão dá o mesmo. Somam-se entre si e com o texto — `PLA na impressora sem caixa`
procura uma bobine que seja as três coisas ao mesmo tempo, e não um filamento
com uma de cada. Os três sinais — símbolo a verde, contorno verde e véu verde — ligam-se
e desligam-se um a um em *Definições* (o véu vem desligado).

**Aparência.** Em *Definições* dá para forçar o desenho ou a foto em todas as
bobines, ligar/desligar a etiqueta do material e marcar os **por abrir** — muda
só o que se vê, nunca o que está gravado. Um grupo em que *todas* as bobines
ainda estão seladas pode levar duas coisas, ligadas em separado: um **véu roxo**,
que se nota sempre, e um **reflexo** que o atravessa devagar (muito mais pausa do
que passagem, e nenhum se o sistema pedir menos animação). Só o reflexo já chega
para dar o sinal sem pintar o cartão. Basta abrir uma bobine para o grupo deixar
de estar marcado.

**O que não coube.** As linhas dos cartões não dobram, para os cartões terem
todos a mesma altura; quando o texto é cortado, o rato por cima abre uma dica
com o resto. Só quando é mesmo cortado — uma dica que aparece sempre é ruído.

**Vistas.** A lista mostra-se seguida ou agrupada por **local**, **marca**,
**material**, **sub-material** ou **cor**, com sub-ordenação (nome, mais
filamento, mais bobines, adicionado há menos). A escolha fica guardada. O
material tem dois níveis: *por material* junta tudo o que é PLA — PLA+, PLA
Silk, PLA Wood, HT-PLA — e é a mesma leitura da etiqueta do cartão, enquanto
*por sub-material* separa o que está escrito em cada filamento. No agrupamento por cor, "Jet
Black", "Preto" e "Traffic Black" caem todos no mesmo grupo — agrupar pelo texto
cru dava um grupo por bobine.

Na vista **por local**, um filamento espalhado por duas estantes aparece nas
duas, e cada cartão conta só o que está ali: é isso que a ordenação usa, e o
cartão diz **de quantas bobines** faz parte e **onde estão as outras** — no
lugar da estante, que o cabeçalho do grupo já diz. As linhas do cartão nunca
dobram, para os cartões terem todos a mesma altura.

**Arrumação.** Locais em árvore (sala › armário › prateleira › caixa) com
capacidade, e a lista desenha essa árvore: o que está dentro de outro aparece
encaixado lá dentro. Nome, tipo, capacidade e "dentro de" mudam-se a qualquer
momento; o campo "dentro de" nunca oferece o próprio local nem um que já esteja
lá dentro, e o servidor recusa na mesma — um anel de locais fazia o caminho até
à raiz nunca terminar. Cada local diz quantas bobines tem, quanto filamento por
gastar lá está e **quanto vale** esse filamento — as três contas somam sempre a
subárvore, por isso uma estante mostra o que está nas gavetas dela. O topo da app
fecha a conta: quilos e euros armazenados, do mesmo conjunto de bobines. O valor
sai do que se pagou por cada bobine (preço a dividir pelo peso que trazia, vezes o
que resta); sem preço próprio vale o €/kg médio do filamento, e sem nenhum dos dois
fica de fora — somar menos é melhor do que inventar um preço. O agente
(`agente.py`) propõe nomes e onde pôr cada bobine; o
**Preview** não escreve nada, o **Apply** aplica e guarda a reversão para se
poder **anular**. Claude, GPT, Gemini ou DeepSeek, à escolha em Definições.

**Arrumar (para depois de uma mudança).** Uma aba com o monte do que ainda não tem
sítio à esquerda e os contentores à direita. Arrasta-se de um para o outro com o
rato, ou com o dedo no tablet (segura-se um instante e arrasta-se; deslizar logo
continua a rolar a lista) — ou toca-se na bobine e depois no contentor. Os
contentores **são os locais**: o que se arruma aqui vale para a lista, o agente e o
Fatia.

Cada contentor diz o que **aceita**: tipo (PLA normais, PLA especiais — madeira,
silk, LW/foam, glitter, metálicos, CF, HD —, PETG, Engenharia — ABS, ASA, PC,
Nylon, TPU —, Outros) ou material, e se se quiser só certas famílias de cor e/ou só
seladas/abertas. As prateleiras sem regras herdam as da estante. A partir daí cada
bobine do monte traz o sítio sugerido (material escolhido pesa mais do que tipo;
bobines iguais ficam juntas; a capacidade é respeitada, também ao pôr várias de uma
vez). As famílias de cor saem da cor **desenhada** e não do texto, por isso
"Glacier White", "Branco" e "Rapid White" são todos brancos.

O monte vê-se por cor, por tipo, tudo, ou em **rondas aleatórias** de 5–6 bobines
para procurar no meio da pilha. Há "pôr no sítio sugerido" por grupo ou para tudo,
e desfazer passo a passo. **Nova mudança** devolve tudo ao monte (as impressoras
podem ficar) e pode apagar os contentores antigos; fica um retrato do antes — cada
bobine mostra "antes: …", o **+** oferece os contentores antigos com as regras
deduzidas do que lá estava, e a mudança inteira anula-se de uma vez (os
contentores apagados voltam com o mesmo id).

**Ponte para o Fatia.** O [Fatia](https://github.com/hubertdungen/fatia) escolhe os
filamentos daqui **em direto**, sem importar nada: `/api/fatia/filamentos` devolve, por
filamento, o custo real por quilo (do que foi mesmo pago), o melhor preço visto nas lojas,
quanto material ainda há em casa, em que locais está, e a **cor já resolvida em hex** —
`lexicon.cor_hex()` é o mesmo algoritmo que o browser corre em `corDe()`, para a bobine
desenhada sair igual nas duas apps. Não há nada a configurar: as duas apps correm nesta
máquina e falam por um segredo em `~/.local/share/bobina/bridge.token`.

## Ficheiros

| | |
|---|---|
| `server.py`  | API, SQLite, autenticação, seguimento de preços |
| `lexicon.py` | sinónimos PT/EN — servido em `/api/lexicon`, partilhado com o browser |
| `lojas.py`   | adaptadores das lojas (Woo, PrestaShop, Shopify, HTML) |
| `agente.py`  | o agente de arrumação; devolve um plano, nunca escreve |
| `index.html` | a app toda, num ficheiro |

## Pôr a andar

Não há nada para instalar além do Python 3 (10 ou mais recente). Sem `pip`, sem
`node`, sem base de dados a correr ao lado.

    git clone https://github.com/hubertdungen/bobina.git
    cd bobina
    python3 server.py --port 8100

Abre `http://localhost:8100`, cria a conta na primeira visita (essa fica dona do
inventário) e está feito. Os dados ficam em `~/.local/share/bobina/`.

Para o agente de arrumação é preciso uma chave de API — Claude, GPT, Gemini ou
DeepSeek, à escolha em *Definições*. O resto da app funciona sem nenhuma.

## Manutenção

    ~/scripts/bobina-server.sh {start|stop|restart|status}
    ~/scripts/bobina-backup.sh          # DB + repo para dentro de 2_CONFIG (cron 03:05)

Arranca no boot e é vigiado de 5 em 5 minutos pelo cron.

## Licença

Código disponível, não é código aberto. **Uso pessoal gratuito; uso comercial
exige licença acordada com o autor** — [`LICENSE`](LICENSE) (inglês, prevalece)
e [`LICENCA.md`](LICENCA.md) (português).

As lojas referidas não têm qualquer ligação a este projeto. Os preços que a app
mostra são lidos das páginas públicas delas, são informativos e ficam
desactualizados — confirma sempre no site da loja antes de comprar.
