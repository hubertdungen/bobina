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


def _cached(loja: str, termo: str, fn, limite: int) -> list[dict]:
    """Memória curta por (loja, termo). O ecrã de adicionar pesquisa enquanto se
    escreve; sem isto cada tecla era uma volta às cinco lojas."""
    chave = (loja, termo, limite)
    with _cache_lock:
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

def busca_evolt(q: str, limite: int = 12) -> list[dict]:
    url = ("https://evolt.pt/wp-json/wc/store/v1/products?"
           + urllib.parse.urlencode({"search": q, "per_page": limite, "status": "publish"}))
    out = []
    for p in _json(url) or []:
        precos = p.get("prices") or {}
        # a Woo devolve inteiros na unidade mínima: 590 com minor_unit 2 = 5,90 €
        minor = int(precos.get("currency_minor_unit", 2) or 2)
        bruto = precos.get("price")
        preco = (int(bruto) / (10 ** minor)) if bruto not in (None, "") else None
        img = ((p.get("images") or [{}])[0] or {}).get("src", "")
        out.append(_produto(
            "evolt", titulo=_txt(p.get("name")), preco=preco, url=p.get("permalink", ""),
            imagem=img, stock=p.get("is_in_stock"),
            moeda=precos.get("currency_code", "EUR"), ref=str(p.get("sku") or "")))
    return out


# ---------------------------------------------------------------- Core XY (PT) --

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
            url=p.get("url", ""), imagem=cover.get("medium", {}).get("url", "")
            if isinstance(cover.get("medium"), dict) else cover.get("bySize", {})
            .get("medium_default", {}).get("url", ""),
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
    """Reescreve a pesquisa na língua da loja.

    A evolt.pt e a corexy.pt catalogam em português; a QIDI, a Elegoo e a Amazon
    em inglês. Mandar "preto" a uma loja inglesa devolve zero, e "black" à Evolt
    também -- por isso cada loja recebe a sua versão. Nas cores o primeiro alias
    da tabela é sempre o inglês e a chave canónica é sempre a portuguesa, o que
    torna a tradução uma consulta directa."""
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


def busca(q: str, lojas: list[str] | None = None, limite: int = 12) -> dict:
    """Pesquisa em paralelo. Uma loja em baixo não derruba as outras: o erro dela
    vai no relatório e os resultados das restantes seguem."""
    alvo = [s for s in (lojas or list(ADAPTADORES)) if s in ADAPTADORES]
    # (loja, termo) -- a variante traduzida e, se der noutra coisa, o texto tal
    # como foi escrito; o que vier a dobrar é limpo pelo URL mais abaixo
    tarefas: list[tuple[str, str]] = []
    for loja in alvo:
        termo = traduz(q, "pt" if LOJAS[loja]["pais"] == "PT" else "en")
        tarefas.append((loja, termo))
        if norm(q) != termo:
            tarefas.append((loja, norm(q)))

    resultados: list[dict] = []
    erros: dict[str, str] = {}
    consultas: dict[str, list[str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(tarefas), 1)) as ex:
        futuros = {ex.submit(_cached, loja, termo, ADAPTADORES[loja], limite):
                   (loja, termo) for loja, termo in tarefas}
        for fut in concurrent.futures.as_completed(futuros, timeout=TIMEOUT + 10):
            loja, termo = futuros[fut]
            consultas.setdefault(loja, []).append(termo)
            try:
                resultados.extend(fut.result() or [])
            except Exception as e:  # noqa: BLE001 - queremos mesmo apanhar tudo
                erros[loja] = f"{type(e).__name__}: {e}"[:200]

    unicos: dict[str, dict] = {}
    for p in resultados:
        unicos.setdefault(p["url"] or f"{p['loja']}:{p['titulo']}", p)
    resultados = list(unicos.values())
    for p in resultados:
        p["relevancia"] = round(pontua(p["titulo"], p.get("marca", ""), q), 3)
        p["filamento"] = e_filamento(p["titulo"])
    # fora o que não casa nada com a pesquisa nem é sequer filamento
    resultados = [p for p in resultados if p["relevancia"] > 0 and p["filamento"]]
    # mais relevante primeiro; empatados, o €/kg mais barato à cabeça
    resultados.sort(key=lambda p: (-p["relevancia"], p["preco"] is None,
                                   p["preco_kg"] or p["preco"] or 9e9))
    return {"query": q, "resultados": resultados, "erros": erros,
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
