#!/usr/bin/env python3
"""Adaptadores das lojas: pesquisa de produto e leitura de preço.

Cada loja tem o seu próprio bicho e foi confirmada à mão a 2026-08-26:

  evolt.pt      WooCommerce  -> /wp-json/wc/store/v1/products?search=  (JSON limpo,
                               preços em cêntimos com `currency_minor_unit`)
  corexy.pt     PrestaShop   -> /pesquisa?controller=search&s=&ajax=1  (JSON com
                               `products`; o suggest.json da Shopify dá 404 aqui)
  eu.qidi3d.com Shopify      -> /search/suggest.json
  eu.elegoo.com Shopify      -> /search/suggest.json
  amazon.es/.de HTML         -> /s?k=  (a homepage responde 202 a um curl pelado;
                               com User-Agent de browser + Accept-Language passa)

Tudo o que sai daqui é a mesma forma de dicionário -- ver `_produto()`.
"""
from __future__ import annotations

import concurrent.futures
import gzip
import html as _html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from lexicon import CORES, GRUPOS, build_index, norm

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TIMEOUT = 25

LOJAS = {
    "evolt":   {"nome": "Evolt",        "pais": "PT", "url": "https://evolt.pt"},
    "corexy":  {"nome": "Core XY",      "pais": "PT", "url": "https://corexy.pt"},
    "qidi":    {"nome": "QIDI EU",      "pais": "EU", "url": "https://eu.qidi3d.com"},
    "elegoo":  {"nome": "Elegoo EU",    "pais": "EU", "url": "https://eu.elegoo.com"},
    "amazon":  {"nome": "Amazon ES",    "pais": "ES", "url": "https://www.amazon.es"},
}


CACHE_TTL = int(os.environ.get("BOBINA_LOJAS_TTL", "600"))
_cache: dict[tuple, tuple[float, list]] = {}
_cache_lock = threading.Lock()

# Um cadeado por chave. Sem isto, as variantes de língua da mesma pesquisa
# partem todas ao mesmo tempo, falham a cache todas (ainda ninguém a encheu) e
# vão buscar o mesmo à loja três vezes -- foi o que atirou a Amazon a timeout.
_locks: dict[tuple, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_da_chave(chave: tuple) -> threading.Lock:
    with _locks_guard:
        if len(_locks) > 400:
            _locks.clear()
        return _locks.setdefault(chave, threading.Lock())


def _cached(loja: str, termo: str, fn, limite: int) -> list[dict]:
    """Memória curta por (loja, termo). O ecrã de adicionar pesquisa enquanto se
    escreve; sem isto cada tecla era uma volta às cinco lojas."""
    chave = (loja, termo, limite)
    with _cache_lock:
        hit = _cache.get(chave)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    with _lock_da_chave(chave):
        with _cache_lock:                      # outro pode tê-la enchido entretanto
            hit = _cache.get(chave)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return hit[1]
        r = fn(termo, limite)
    with _cache_lock:
        _cache[chave] = (time.time(), r)
        if len(_cache) > 500:                       # não cresce sem fim
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:200]:
                _cache.pop(k, None)
    return r


def _get(url: str, *, headers: dict | None = None, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw


def _json(url: str, **kw) -> dict | list:
    return json.loads(_get(url, **kw).decode("utf-8", "replace"))


def _txt(s) -> str:
    """Tira tags e desfaz entidades -- os títulos da Woo vêm com &#8211; lá dentro."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _num(s) -> float | None:
    """Extrai um número de '23,20 €' / '€23.20' / '1.234,56'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = re.sub(r"[^\d.,]", "", str(s))
    if not t:
        return None
    # separador decimal = o último que aparecer; o outro é de milhares
    if "," in t and "." in t:
        dec = max(t.rfind(","), t.rfind("."))
        t = re.sub(r"[.,]", "", t[:dec]) + "." + re.sub(r"[^\d]", "", t[dec + 1:])
    else:
        t = t.replace(",", ".")
        if t.count(".") > 1:
            head, _, tail = t.rpartition(".")
            t = head.replace(".", "") + "." + tail
    try:
        return float(t)
    except ValueError:
        return None


PESO_RE = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(kg|kgs|quilos?|g|gr|gramas?)(?![a-z])", re.I)


def peso_g(titulo: str) -> float | None:
    """Peso de filamento a partir do título ('... 1Kg', '500g', '2 x 1kg').

    Só conta pesos plausíveis para uma bobine (100 g a 10 kg): assim '1.75mm'
    nunca é lido como peso e '3D' também não."""
    for valor, unidade in PESO_RE.findall(titulo or ""):
        n = _num(valor)
        if n is None:
            continue
        g = n * 1000 if unidade.lower().startswith(("kg", "quilo")) else n
        if 100 <= g <= 10000:
            return g
    return None


def _mini(srcset: str, minimo: int = 200) -> str:
    """A variante mais pequena do srcset que ainda sirva.

    Os cartões mostram a foto a 44 px, mas as lojas servem o original: a foto de
    um filamento na Evolt chega a ter 290 KB. Com trinta filamentos era quase um
    megabyte a cada abertura, para nada. O srcset do WordPress traz 150w, 300w,
    500w e 1000w -- fica-se pela de 300."""
    melhor, melhor_w = "", 10 ** 9
    for parte in (srcset or "").split(","):
        campos = parte.strip().split()
        if len(campos) != 2 or not campos[1].endswith("w"):
            continue
        try:
            w = int(campos[1][:-1])
        except ValueError:
            continue
        if minimo <= w < melhor_w:
            melhor, melhor_w = campos[0], w
    return melhor


def _produto(loja: str, *, titulo: str, preco: float | None, url: str,
             imagem: str = "", stock=None, moeda: str = "EUR",
             marca: str = "", ref: str = "") -> dict:
    """A forma única que todas as lojas devolvem."""
    g = peso_g(titulo)
    return {
        "loja": loja,
        "loja_nome": LOJAS[loja]["nome"],
        "pais": LOJAS[loja]["pais"],
        "titulo": titulo,
        "preco": round(preco, 2) if preco is not None else None,
        "moeda": moeda,
        "peso_g": g,
        "preco_kg": round(preco / (g / 1000.0), 2) if (preco and g) else None,
        "url": url,
        "imagem": imagem,
        "stock": stock,
        "marca": marca,
        "ref": ref,
    }


# ----------------------------------------------------------------- Evolt (PT) --

EVOLT_API = "https://evolt.pt/wp-json/wc/store/v1/products"
EVOLT_PAGINAS = int(os.environ.get("BOBINA_EVOLT_PAGINAS", "3"))


_evolt_paginas: dict[tuple, tuple[float, list]] = {}


def _evolt_pagina(q: str, page: int = 1, n: int = 100) -> list[dict]:
    """Cache à parte das páginas cruas.

    A busca() manda à Evolt duas variantes da mesma pesquisa (a traduzida e a
    escrita tal e qual) e ambas acabam a paginar pelo MESMO termo largo -- sem
    isto eram seis pedidos de 100 produtos em vez de três."""
    chave = ("evolt-pag", q, page, n)
    with _cache_lock:
        hit = _evolt_paginas.get(chave)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    with _lock_da_chave(chave):
        with _cache_lock:
            hit = _evolt_paginas.get(chave)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return hit[1]
        # _fields corta a página de 2 MB para 600 KB e o tempo quase a metade;
        # o resto do payload da Woo (descrições, variações, atributos) não se usa
        url = EVOLT_API + "?" + urllib.parse.urlencode(
            {"search": q, "per_page": n, "page": page, "status": "publish",
             "_fields": "id,name,prices,permalink,images,sku,is_in_stock"})
        try:
            r = _json(url) or []
        except Exception:  # noqa: BLE001 - página a mais devolve erro, não é falha
            r = []
    with _cache_lock:
        _evolt_paginas[chave] = (time.time(), r)
        if len(_evolt_paginas) > 120:
            for k in sorted(_evolt_paginas, key=lambda k: _evolt_paginas[k][0])[:60]:
                _evolt_paginas.pop(k, None)
    return r


def _evolt_produto(p: dict) -> dict:
    precos = p.get("prices") or {}
    # a Woo devolve inteiros na unidade mínima: 590 com minor_unit 2 = 5,90 €
    minor = int(precos.get("currency_minor_unit", 2) or 2)
    bruto = precos.get("price")
    preco = (int(bruto) / (10 ** minor)) if bruto not in (None, "") else None
    bruta = (p.get("images") or [{}])[0] or {}
    img = _mini(bruta.get("srcset", "")) or bruta.get("thumbnail") or bruta.get("src", "")
    return _produto(
        "evolt", titulo=_txt(p.get("name")), preco=preco, url=p.get("permalink", ""),
        imagem=img, stock=p.get("is_in_stock"),
        moeda=precos.get("currency_code", "EUR"), ref=str(p.get("sku") or ""))


def busca_evolt(q: str, limite: int = 12) -> list[dict]:
    """A Evolt precisa de tratamento especial, e a razão é esta:

    a pesquisa da Woo casa uma SUBSTRING contígua do texto todo, não palavra a
    palavra. Os títulos lá são "ASA 1kg Black - Azurefilm", por isso `asa black`
    devolve ZERO (o "1kg" fica pelo meio) enquanto `asa 1kg black` devolve sete.
    Ninguém adivinha que tem de escrever o peso no meio, e era isto que fazia
    desaparecer filamentos que a loja tem à venda.

    Solução: pesquisa-se pelo termo mais selectivo (o material ou a marca, que
    não mudam de língua), pagina-se, e o filtro fino é feito aqui com o léxico.
    Como o filtro é local, deixa também de importar que a loja escreva "Black"
    e a pesquisa venha em "preto"."""
    directa = [_evolt_produto(p) for p in _evolt_pagina(q, 1, max(limite * 2, 20))]
    if len(directa) >= limite:
        return directa[:limite]

    largo = termo_selectivo(q)
    if not largo or largo == norm(q):
        return directa[:limite]

    vistos = {p["url"] for p in directa}
    saida = list(directa)
    # Em série de propósito: com _fields cada página anda em ~1,4 s, e abrir mais
    # ligações em paralelo daqui de dentro (já estamos dentro do pool da busca)
    # tirava banda às outras lojas -- a Amazon chegou a ir a timeout por isso.
    paginas = []
    for n in range(1, EVOLT_PAGINAS + 1):
        bruto = _evolt_pagina(largo, n, 100)
        paginas.append(bruto)
        if len(bruto) < 100:
            break
    for bruto in paginas:
        for item in bruto:
            prod = _evolt_produto(item)
            if prod["url"] in vistos:
                continue
            # aqui é que a pesquisa do utilizador conta, já com sinónimos
            if pontua(prod["titulo"], prod.get("marca", ""), q) >= 0.99:
                vistos.add(prod["url"])
                saida.append(prod)
    return saida[:limite]


# ---------------------------------------------------------------- Core XY (PT) --

def _corexy_img(cover: dict) -> str:
    """A PrestaShop dá vários tamanhos em bySize; o `home_default` chega bem."""
    if not isinstance(cover, dict):
        return ""
    por_tamanho = cover.get("bySize") or {}
    for chave in ("home_default", "medium_default", "cart_default", "large_default"):
        u = (por_tamanho.get(chave) or {}).get("url")
        if u:
            return u
    m = cover.get("medium")
    if isinstance(m, dict) and m.get("url"):
        return m["url"]
    return cover.get("url", "") or ""


def busca_corexy(q: str, limite: int = 12) -> list[dict]:
    url = ("https://corexy.pt/pesquisa?"
           + urllib.parse.urlencode({"controller": "search", "s": q, "ajax": 1}))
    dados = _json(url)
    out = []
    for p in (dados.get("products") or [])[:limite]:
        cover = p.get("cover") or {}
        stock = p.get("quantity")
        out.append(_produto(
            "corexy", titulo=_txt(p.get("name")),
            preco=_num(p.get("price_amount") or p.get("price")),
            url=p.get("url", ""), imagem=_corexy_img(cover),
            stock=(stock > 0) if isinstance(stock, int) else None,
            marca=_txt(p.get("manufacturer_name")), ref=str(p.get("reference") or "")))
    return out


# ------------------------------------------------------- Shopify (QIDI, Elegoo) --

def _busca_shopify(loja: str, base: str, q: str, limite: int = 12) -> list[dict]:
    url = (f"{base}/search/suggest.json?"
           + urllib.parse.urlencode({
               "q": q, "resources[type]": "product", "resources[limit]": limite}))
    dados = _json(url)
    prods = (((dados.get("resources") or {}).get("results") or {}).get("products") or [])
    out = []
    for p in prods[:limite]:
        preco = _num(p.get("price"))
        img = p.get("featured_image") or p.get("image") or ""
        if isinstance(img, dict):
            img = img.get("url", "")
        if img.startswith("//"):
            img = "https:" + img
        if img and "cdn.shopify.com" in img:
            # a CDN da Shopify redimensiona a pedido: 141 KB passam a 16 KB
            img += ("&" if "?" in img else "?") + "width=240"
        out.append(_produto(
            loja, titulo=_txt(p.get("title")), preco=preco,
            url=urllib.parse.urljoin(base, p.get("url", "")), imagem=img,
            stock=p.get("available"), marca=_txt(p.get("vendor"))))
    return out


def busca_qidi(q: str, limite: int = 12) -> list[dict]:
    return _busca_shopify("qidi", "https://eu.qidi3d.com", q, limite)


def busca_elegoo(q: str, limite: int = 12) -> list[dict]:
    return _busca_shopify("elegoo", "https://eu.elegoo.com", q, limite)


# ---------------------------------------------------------------- Amazon (ES) --

_ASIN_RE = re.compile(r'data-asin="([A-Z0-9]{10})"')


def busca_amazon(q: str, limite: int = 12) -> list[dict]:
    """A Amazon não tem API pública aqui, por isso é HTML. É o adaptador mais
    frágil de propósito: falha em silêncio e as outras lojas continuam a valer."""
    url = "https://www.amazon.es/s?" + urllib.parse.urlencode({"k": q})
    pagina = _get(url).decode("utf-8", "replace")
    if 'data-asin="' not in pagina:
        # sob pedidos em paralelo a Amazon devolve às vezes uma página sem
        # resultados em vez de um erro; uma segunda tentativa costuma passar
        time.sleep(1.5)
        pagina = _get(url).decode("utf-8", "replace")
    out, vistos = [], set()
    # cada cartão de resultado começa num data-asin; corta-se o HTML por aí
    partes = re.split(r'(?=<div[^>]*data-asin="[A-Z0-9]{10}")', pagina)
    for parte in partes:
        m = _ASIN_RE.search(parte)
        if not m:
            continue
        asin = m.group(1)
        if asin in vistos:
            continue
        t = re.search(r'<h2[^>]*>.*?<span[^>]*>(.*?)</span>', parte, re.S)
        if not t:
            continue
        titulo = _txt(t.group(1))
        # "Consulte a página de cada produto..." é a linha de variantes de preço
        # da Amazon, não um produto; entrava no inventário como se fosse um.
        if len(titulo) < 15 or titulo.lower().startswith(
                ("consulte a p", "check each product", "ver las opciones")):
            continue
        # a-offscreen traz o preço já formatado ("19,99 €"); é o mais fiável
        pm = re.search(r'class="a-offscreen">([^<]+)<', parte)
        preco = _num(pm.group(1)) if pm else None
        im = re.search(r'<img[^>]+class="s-image"[^>]+src="([^"]+)"', parte)
        vistos.add(asin)
        out.append(_produto(
            "amazon", titulo=titulo, preco=preco,
            url=f"https://www.amazon.es/dp/{asin}",
            imagem=im.group(1) if im else "", ref=asin))
        if len(out) >= limite:
            break
    return out


# ------------------------------------------------------------------ relevância --

_INDEX = build_index()
# O suggest.json da Shopify é generoso: uma busca por "ASA" traz resinas e
# impressoras. Estes termos marcam o que NÃO é bobine de filamento.
NAO_FILAMENTO = ("resin", "resina", "printer", "impressora", "nozzle", "bico",
                 "build plate", "placa", "hotend", "extruder", "extrusor",
                 "scanner", "laser", "cure", "washing", "spare", "peca",
                 "kit", "cable", "cabo", "sensor", "motor", "belt", "correia",
                 "screen", "ecra", "adhesive", "cola", "glue", "tool", "chave")


def _expande(token: str) -> set[str]:
    """Aliases equivalentes a um token (mesma tabela da pesquisa do inventário)."""
    saida = {token}
    for hit in _INDEX.get(token, []):
        tabela = GRUPOS[hit["g"]]
        saida.add(norm(hit["c"]))
        saida.update(norm(a) for a in tabela[hit["c"]])
    return {x for x in saida if x}


def pontua(titulo: str, marca: str, q: str) -> float:
    """Fração dos termos da pesquisa que aparecem no produto, já com sinónimos.

    É o que faz "ASA azure preto" encontrar "ASA AzureFilm Black": cada termo
    expande para os seus aliases e basta um deles cair no título."""
    campo = norm(f"{titulo} {marca}")
    termos = [t for t in norm(q).split() if t]
    if not termos:
        return 0.0
    acertos = 0
    for t in termos:
        for alias in _expande(t):
            # limite de palavra à esquerda para "pla" não casar dentro de "display"
            if re.search(r"(?<![a-z0-9])" + re.escape(alias), campo):
                acertos += 1
                break
    return acertos / len(termos)


def traduz(q: str, alvo: str) -> str:
    """Escreve a pesquisa numa das duas línguas.

    Não serve para SUBSTITUIR o que foi escrito: a busca() manda as duas versões
    além do texto original, porque uma loja portuguesa pode ter o produto
    catalogado em inglês (a Evolt tem: "ASA 1kg Black") e vice-versa. Nas cores a
    chave canónica é sempre a portuguesa e o primeiro alias é sempre o inglês, o
    que torna isto uma consulta directa."""
    saida = []
    for token in norm(q).split():
        hits = _INDEX.get(token, [])
        cor = next((h for h in hits if h["g"] == "cor"), None)
        outro = next((h for h in hits if h["g"] in ("marca", "material")), None)
        if outro:                                   # marcas e materiais não se traduzem
            saida.append(outro["c"])
        elif cor:
            saida.append(cor["c"] if alvo == "pt" else CORES[cor["c"]][0])
        else:
            saida.append(token)
    return " ".join(saida)


def termo_selectivo(q: str) -> str:
    """O termo por onde vale a pena pedir a lista larga a uma loja.

    Materiais primeiro (conjunto pequeno e escrito igual em toda a parte),
    marcas a seguir. Cores ficam de fora de propósito: pedir "preto" a uma loja
    que cataloga em inglês devolve zero, e é justamente isso que se quer evitar."""
    toks = [t for t in norm(q).split() if len(t) > 1]
    if not toks:
        return ""
    for grupo in ("material", "marca"):
        for t in toks:
            hit = next((h for h in _INDEX.get(t, []) if h["g"] == grupo), None)
            if hit:
                return hit["c"] if grupo == "material" else t
    naocor = [t for t in toks
              if not any(h["g"] in ("cor", "formato") for h in _INDEX.get(t, []))]
    return max(naocor or toks, key=len)


def e_filamento(titulo: str) -> bool:
    t = norm(titulo)
    if any(re.search(r"(?<![a-z])" + re.escape(w), t) for w in NAO_FILAMENTO):
        # "PLA Filament" ganha a "kit": se diz filamento/bobine, é filamento
        return bool(re.search(r"(?<![a-z])(filament|filamento|bobine|spool|refill|refil)", t))
    return True


ADAPTADORES = {
    "evolt": busca_evolt,
    "corexy": busca_corexy,
    "qidi": busca_qidi,
    "elegoo": busca_elegoo,
    "amazon": busca_amazon,
}


def _variantes(q: str, loja: str) -> list[str]:
    """O que se manda a uma loja: o texto tal como foi escrito e as versões em
    português e em inglês, sem repetidos. A da língua da loja vai à frente por
    ser a que costuma acertar à primeira -- mas nenhuma é descartada."""
    primeira = "pt" if LOJAS[loja]["pais"] == "PT" else "en"
    ordem = [traduz(q, primeira), norm(q), traduz(q, "en" if primeira == "pt" else "pt")]
    saida: list[str] = []
    for v in ordem:
        if v and v not in saida:
            saida.append(v)
    return saida


def _busca_loja(loja: str, q: str, limite: int) -> list[dict]:
    """Uma loja, uma ligação, as variantes em fila.

    Antes mandavam-se todas as variantes de todas as lojas ao mesmo tempo -- 15
    pedidos em paralelo -- e a Core XY e a Amazon iam a timeout. Assim cada loja
    usa uma ligação de cada vez e pára mal tenha um produto que case TODOS os
    termos escritos, que na prática é logo à primeira variante."""
    saida: list[dict] = []
    vistos: set[str] = set()
    for variante in _variantes(q, loja):
        for prod in _cached(loja, variante, ADAPTADORES[loja], limite) or []:
            chave = prod["url"] or f"{prod['loja']}:{prod['titulo']}"
            if chave in vistos:
                continue
            vistos.add(chave)
            saida.append(prod)
        if any(pontua(p["titulo"], p.get("marca", ""), q) >= 0.99 for p in saida):
            break
    return saida


def busca(q: str, lojas: list[str] | None = None, limite: int = 12) -> dict:
    """Pesquisa em paralelo, uma tarefa por loja. Uma loja em baixo não derruba
    as outras: o erro dela vai no relatório e o resto segue."""
    alvo = [s for s in (lojas or list(ADAPTADORES)) if s in ADAPTADORES]
    resultados: list[dict] = []
    erros: dict[str, str] = {}
    consultas: dict[str, list[str]] = {loja: _variantes(q, loja) for loja in alvo}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(alvo), 1)) as ex:
        futuros = {ex.submit(_busca_loja, loja, q, limite): loja for loja in alvo}
        for fut in concurrent.futures.as_completed(futuros, timeout=TIMEOUT * 3):
            loja = futuros[fut]
            try:
                resultados.extend(fut.result() or [])
            except Exception as e:  # noqa: BLE001 - queremos mesmo apanhar tudo
                erros[loja] = f"{type(e).__name__}: {e}"[:200]

    for p in resultados:
        p["relevancia"] = round(pontua(p["titulo"], p.get("marca", ""), q), 3)
        p["filamento"] = e_filamento(p["titulo"])
    bons = [p for p in resultados if p["relevancia"] > 0 and p["filamento"]]
    # com dois termos ou mais, exigir metade evita encher a lista de produtos que
    # só casam a marca; se isso não deixar nada, mostra-se o que houver
    termos = len([t for t in norm(q).split() if t])
    if termos >= 2:
        apertado = [p for p in bons if p["relevancia"] >= 0.6]
        bons = apertado or bons
    bons.sort(key=lambda p: (-p["relevancia"], p["preco"] is None,
                             p["preco_kg"] or p["preco"] or 9e9))
    return {"query": q, "resultados": bons, "erros": erros,
            "consultas": consultas, "lojas": {s: LOJAS[s] for s in alvo}}


if __name__ == "__main__":
    import sys
    termo = " ".join(sys.argv[1:]) or "ASA preto 1kg"
    r = busca(termo)
    print(f"== {termo!r}: {len(r['resultados'])} resultados, erros={r['erros']}")
    for p in r["resultados"][:14]:
        kg = f"{p['preco_kg']:.2f}/kg" if p["preco_kg"] else "—"
        print(f"  [{p['loja_nome']:<10}] {p['relevancia']:.2f} {p['preco'] if p['preco'] else '—':>7} € "
              f"{kg:>10}  {p['titulo'][:64]}")
