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

**Aparência.** Em *Definições* dá para forçar o desenho ou a foto em todas as
bobines e ligar/desligar a etiqueta do material — muda só o que se vê, nunca o
que está gravado.

**Vistas.** A lista mostra-se seguida ou agrupada por **local**, **marca**,
**material** ou **cor**, com sub-ordenação (nome, mais filamento, mais bobines,
adicionado há menos). A escolha fica guardada. No agrupamento por cor, "Jet
Black", "Preto" e "Traffic Black" caem todos no mesmo grupo — agrupar pelo texto
cru dava um grupo por bobine.

**Arrumação.** Locais em árvore (sala › armário › prateleira › caixa) com
capacidade, e a lista desenha essa árvore: o que está dentro de outro aparece
encaixado lá dentro. Nome, tipo, capacidade e "dentro de" mudam-se a qualquer
momento; o campo "dentro de" nunca oferece o próprio local nem um que já esteja
lá dentro, e o servidor recusa na mesma — um anel de locais fazia o caminho até
à raiz nunca terminar. O agente (`agente.py`) propõe nomes e onde pôr cada bobine; o
**Preview** não escreve nada, o **Apply** aplica e guarda a reversão para se
poder **anular**. Claude, GPT, Gemini ou DeepSeek, à escolha em Definições.

**Ponte para o Fatia.** O Fatia importa daqui os filamentos com o custo real por
quilo, calculado pelo que foi mesmo pago. Não há nada a configurar: as duas apps
correm nesta máquina e falam por um segredo em `~/.local/share/bobina/bridge.token`.

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
