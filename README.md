# Bobina — logística de filamento 3D

Inventário de filamento para impressão 3D: o que tenho, onde está, quanto resta,
quanto custa em cada loja — e um agente que ajuda a arrumar.

Corre em `http://pavilion-nas:8100`. Python da biblioteca padrão, sem dependências,
SQLite em `~/.local/share/bobina/bobina.db`. Mesmo molde do Fatia e do Rumo.

## O que faz

**Pesquisa instantânea.** Escreve-se e a lista filtra — sem Enter, sem botão. O
truque é o léxico (`lexicon.py`): 700+ sinónimos de marcas, materiais, cores e
formatos, em português e inglês. `ASA Azure Preto` encontra um *AzureFilm ASA
Black*; `grey` encontra *Cinzento*; `azu` já chega para a AzureFilm aparecer.
"Azure" é de propósito marca **e** cor — casa com as duas.

**Preços.** Cinco lojas (`lojas.py`): Evolt e Core XY (PT), QIDI EU, Elegoo EU e
Amazon. Cada loja recebe o texto tal como foi escrito **mais** as versões em
português e em inglês — a língua soma-se, nunca substitui, para nenhuma loja
ficar de fora só por catalogar na outra. Actualiza sozinho de 24 em 24 horas e
guarda o histórico.

A Evolt leva tratamento à parte: a pesquisa da WooCommerce casa uma *substring*
contígua do título, por isso `asa black` devolve zero enquanto `asa 1kg black`
devolve sete — o "1kg" fica pelo meio. Pesquisa-se pelo termo mais selectivo,
pagina-se e o filtro fino é feito cá com o léxico.

**Fotos.** A foto da loja é guardada em `~/.local/share/bobina/imagens` e servida
por `/api/imagem` — o endereço da loja sozinho não chegava, parte no dia em que
ela mexer nos ficheiros. Usa-se a miniatura que a própria loja serve (7–20 KB em
vez de 300 KB) e só se vai buscar imagens aos domínios das cinco lojas.

**Cores.** Sem foto — ou por preferência — a bobine é **desenhada** em traço e
pintada pelo que está escrito na cor: `dark grey`, `wood ash`, `silk red`,
`purple-blue`, `Pastel Mint Green`, `negro azabache`. São ~290 nomes de cor de
impressão 3D com modificadores (`dark`, `pastel`, `neon`, `matte`, `silk`), e as
cores compostas misturam-se. Dá para escolher à mão por amostra ou por roda RGB,
e voltar ao automático quando se quiser.

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

## Manutenção

    ~/scripts/bobina-server.sh {start|stop|restart|status}
    ~/scripts/bobina-backup.sh          # DB + repo para dentro de 2_CONFIG (cron 03:05)

Arranca no boot e é vigiado de 5 em 5 minutos pelo cron.
