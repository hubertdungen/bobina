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
Amazon. Cada uma recebe a pesquisa na sua língua — mandar "preto" a uma loja
inglesa devolvia zero. Actualiza sozinho de 24 em 24 horas e guarda o histórico.

**Arrumação.** Locais em árvore (sala › armário › prateleira › caixa) com
capacidade. O agente (`agente.py`) propõe nomes e onde pôr cada bobine; o
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
