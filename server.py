#!/usr/bin/env python3
"""Bobina: logística de filamento 3D — PWA estática + API SQLite.

Mesmo molde do Fatia e do Rumo: Python da biblioteca padrão, sem dependências,
um index.html só, SQLite no SSD (nunca em exFAT — ver a nota do Jellyfin).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import agente
import lexicon
import lojas

ROOT = Path(__file__).resolve().parent
VERSAO = "1.8.0"
SESSION_COOKIE = "bobina_session"
SESSION_DIAS = int(os.environ.get("BOBINA_SESSION_DAYS", "30"))
MAX_BODY = int(os.environ.get("BOBINA_MAX_BODY", "2097152"))
PBKDF2_ROUNDS = int(os.environ.get("BOBINA_PBKDF2_ROUNDS", "260000"))
GZIP_MIN = 1024
COMPRIMIVEIS = {".html", ".css", ".js", ".json", ".svg", ".webmanifest", ".txt"}

DB: sqlite3.Connection | None = None
DB_LOCK = threading.Lock()
DATA_DIR = Path.home() / ".local/share/bobina"


def agora() -> int:
    return int(time.time())


# ------------------------------------------------------------------ esquema --

ESQUEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  pass_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  criado_em INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  criado_em INTEGER NOT NULL,
  expira_em INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  chave TEXT NOT NULL,
  valor TEXT,
  PRIMARY KEY (user_id, chave)
);
-- Locais em árvore: sala > armário > prateleira > caixa. `pai_id` a NULL é raiz.
CREATE TABLE IF NOT EXISTS locais (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  pai_id INTEGER REFERENCES locais(id) ON DELETE SET NULL,
  tipo TEXT DEFAULT 'prateleira',
  notas TEXT DEFAULT '',
  capacidade INTEGER DEFAULT 0,
  ordem INTEGER DEFAULT 0,
  criado_em INTEGER NOT NULL
);
-- Planos do agente. Guarda-se o plano proposto E a reversão do que foi
-- aplicado, para o "anular" não ser um exercício de memória.
CREATE TABLE IF NOT EXISTS planos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  instrucoes TEXT DEFAULT '',
  plano TEXT NOT NULL,
  reversao TEXT DEFAULT '',
  estado TEXT DEFAULT 'proposto',
  criado_em INTEGER NOT NULL,
  aplicado_em INTEGER DEFAULT 0
);
-- Um filamento é o PRODUTO (marca+material+cor+formato). As bobines físicas
-- que se têm em casa estão na tabela a seguir e apontam para aqui.
CREATE TABLE IF NOT EXISTS filamentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  marca TEXT DEFAULT '',
  material TEXT DEFAULT '',
  cor TEXT DEFAULT '',
  cor_hex TEXT DEFAULT '',
  diametro REAL DEFAULT 1.75,
  peso_g REAL DEFAULT 1000,
  densidade REAL DEFAULT 1.24,
  temp_bico INTEGER DEFAULT 0,
  temp_mesa INTEGER DEFAULT 0,
  ref TEXT DEFAULT '',
  url TEXT DEFAULT '',
  imagem TEXT DEFAULT '',
  loja TEXT DEFAULT '',
  etiquetas TEXT DEFAULT '',
  notas TEXT DEFAULT '',
  -- 0 = automático (foto da loja se houver, senão a bobine desenhada);
  -- 1 = desenhar sempre a bobine, mesmo tendo foto
  icone INTEGER DEFAULT 0,
  seguir INTEGER DEFAULT 1,
  seguir_query TEXT DEFAULT '',
  criado_em INTEGER NOT NULL,
  actualizado_em INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bobines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  filamento_id INTEGER NOT NULL REFERENCES filamentos(id) ON DELETE CASCADE,
  etiqueta TEXT DEFAULT '',
  local_id INTEGER REFERENCES locais(id) ON DELETE SET NULL,
  peso_liquido_g REAL DEFAULT 1000,
  restante_g REAL DEFAULT 1000,
  tara_g REAL DEFAULT 0,
  estado TEXT DEFAULT 'selado',
  preco REAL DEFAULT 0,
  moeda TEXT DEFAULT 'EUR',
  comprado_em TEXT DEFAULT '',
  comprado_loja TEXT DEFAULT '',
  comprado_url TEXT DEFAULT '',
  aberto_em TEXT DEFAULT '',
  -- 1 = ainda tem a caixa original (é onde costuma andar o exsicante)
  caixa INTEGER DEFAULT 0,
  notas TEXT DEFAULT '',
  criado_em INTEGER NOT NULL,
  actualizado_em INTEGER NOT NULL
);
-- Histórico de preços: uma linha por observação, nunca se apaga por cima.
CREATE TABLE IF NOT EXISTS precos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filamento_id INTEGER NOT NULL REFERENCES filamentos(id) ON DELETE CASCADE,
  loja TEXT NOT NULL,
  titulo TEXT DEFAULT '',
  url TEXT DEFAULT '',
  preco REAL,
  moeda TEXT DEFAULT 'EUR',
  peso_g REAL,
  preco_kg REAL,
  stock INTEGER,
  visto_em INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bobines_user ON bobines(user_id);
CREATE INDEX IF NOT EXISTS ix_bobines_fil ON bobines(filamento_id);
CREATE INDEX IF NOT EXISTS ix_filamentos_user ON filamentos(user_id);
CREATE INDEX IF NOT EXISTS ix_locais_user ON locais(user_id);
CREATE INDEX IF NOT EXISTS ix_precos_fil ON precos(filamento_id, visto_em);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
"""


def db() -> sqlite3.Connection:
    assert DB is not None
    return DB


def abre_db(data_dir: Path) -> sqlite3.Connection:
    global DB, DATA_DIR
    DATA_DIR = data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(data_dir / "bobina.db", check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(ESQUEMA)
    # bases criadas antes da capacidade existir continuam a abrir
    colunas = {r[1] for r in con.execute("PRAGMA table_info(locais)")}
    if "capacidade" not in colunas:
        con.execute("ALTER TABLE locais ADD COLUMN capacidade INTEGER DEFAULT 0")
    cols_fil = {r[1] for r in con.execute("PRAGMA table_info(filamentos)")}
    if "icone" not in cols_fil:
        con.execute("ALTER TABLE filamentos ADD COLUMN icone INTEGER DEFAULT 0")
    cols_bob = {r[1] for r in con.execute("PRAGMA table_info(bobines)")}
    if "caixa" not in cols_bob:
        con.execute("ALTER TABLE bobines ADD COLUMN caixa INTEGER DEFAULT 0")
    con.commit()
    DB = con
    return con


def linhas(sql: str, args: tuple = ()) -> list[dict]:
    with DB_LOCK:
        return [dict(r) for r in db().execute(sql, args).fetchall()]


def linha(sql: str, args: tuple = ()) -> dict | None:
    r = linhas(sql, args)
    return r[0] if r else None


def executa(sql: str, args: tuple = ()) -> int:
    with DB_LOCK:
        cur = db().execute(sql, args)
        db().commit()
        return cur.lastrowid


def altera(sql: str, args: tuple = ()) -> int:
    """Como `executa`, mas devolve quantas linhas mudaram. Num UPDATE o
    `lastrowid` não quer dizer nada -- chegou a devolver 2 quando só uma bobine
    tinha sido arrastada."""
    with DB_LOCK:
        cur = db().execute(sql, args)
        db().commit()
        return cur.rowcount


# ---------------------------------------------------------------- utilizadores --

def hash_pass(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()


def cria_user(email: str, password: str) -> int:
    salt = secrets.token_hex(16)
    uid = executa(
        "INSERT INTO users(email,pass_hash,salt,criado_em) VALUES(?,?,?,?)",
        (email.strip().lower(), hash_pass(password, salt), salt, agora()))
    semear(uid)
    return uid


def verifica_user(email: str, password: str) -> dict | None:
    u = linha("SELECT * FROM users WHERE email=?", (email.strip().lower(),))
    if not u:
        return None
    if hmac.compare_digest(hash_pass(password, u["salt"]), u["pass_hash"]):
        return u
    return None


def nova_sessao(uid: int) -> str:
    token = secrets.token_urlsafe(32)
    executa("INSERT INTO sessions(token,user_id,criado_em,expira_em) VALUES(?,?,?,?)",
            (token, uid, agora(), agora() + SESSION_DIAS * 86400))
    return token


def user_da_sessao(token: str | None) -> dict | None:
    if not token:
        return None
    s = linha("SELECT user_id FROM sessions WHERE token=? AND expira_em>?",
              (token, agora()))
    if not s:
        return None
    return linha("SELECT id,email,criado_em FROM users WHERE id=?", (s["user_id"],))


def canon(texto: str, grupo: str) -> str:
    """A chave canónica de um termo, para poder comparar significados em vez de
    letras: "Black", "Preto" e "Deep Black" dão todos "preto".

    Varre frases de até três palavras (a mais longa ganha) porque "Professional
    Lab" e "Devil Design" não casam palavra a palavra. Sem termo conhecido,
    devolve o texto normalizado -- assim uma marca que o léxico não conheça
    continua a comparar-se consigo própria."""
    toks = [t for t in lexicon.norm(texto or "").split() if t]
    for i in range(len(toks)):
        for n in (3, 2, 1):
            if i + n > len(toks):
                continue
            for h in lojas._INDEX.get(" ".join(toks[i:i + n]), []):
                if h["g"] == grupo:
                    return h["c"]
    return " ".join(toks)


def filamento_igual(uid: int, f: dict) -> dict | None:
    """O filamento que já existe e é, para todos os efeitos, este.

    Comparar texto não chegava: a mesma bobine comprada na Evolt ("Black") e na
    Core XY ("Preto") ficava em dois grupos separados, com dois históricos de
    preço e duas contagens. O peso continua a contar -- um rolo de 1 kg e uma
    amostra de 250 g são produtos diferentes, com preços por quilo diferentes."""
    chave = (canon(f.get("marca"), "marca"),
             canon(f.get("material"), "material"),
             canon(f.get("cor"), "cor"),
             round(float(f.get("peso_g") or 1000), 1))
    for existente in linhas("SELECT * FROM filamentos WHERE user_id=?", (uid,)):
        if (canon(existente["marca"], "marca"),
                canon(existente["material"], "material"),
                canon(existente["cor"], "cor"),
                round(float(existente["peso_g"] or 0), 1)) == chave:
            return existente
    return None


def _apara(restante: float, peso: float) -> float:
    """O que resta nunca é negativo nem passa do que a bobine leva.

    Sem isto dava para pôr 900 g numa bobine de 250 g e a barra de nível ficava
    a dizer qualquer coisa. Peso desconhecido (0) deixa passar o valor."""
    try:
        r = float(restante or 0)
        p = float(peso or 0)
    except (TypeError, ValueError):
        return 0.0
    if p <= 0:
        return max(0.0, r)
    return max(0.0, min(r, p))


def _estado_pelo_peso(estado: str, restante: float, peso: float) -> str:
    """O estado segue o que resta, não o contrário.

    Uma bobine a zero está vazia e uma bobine "selada" com metade do filamento
    não existe -- se foi pesada abaixo do cheio, foi aberta. `arquivado` fica
    intocado: é uma decisão de arrumação, não um estado físico."""
    e = (estado or "").strip() or "selado"
    if e == "arquivado":
        return e
    r, p = float(restante or 0), float(peso or 0)
    if r <= 0:
        return "vazio"
    if e == "vazio":
        return "aberto"
    if p > 0 and r < p and e == "selado":
        return "aberto"
    return e


def valida_pai(uid: int, lid: int, pai_id: int | None) -> str:
    """Impede que um local fique dentro de si próprio ou de um descendente seu.

    Sem esta trava, pôr a "Oficina" dentro da "Estante A" -- que já está na
    Oficina -- fechava um anel: `caminhoLocal()` passava a subir para sempre à
    procura de uma raiz que já não existia. Devolve "" quando está tudo bem."""
    if pai_id is None:
        return ""
    if pai_id == lid:
        return "um local não pode estar dentro de si próprio"
    if not linha("SELECT 1 FROM locais WHERE id=? AND user_id=?", (pai_id, uid)):
        return "esse local não existe"
    visto: set[int] = set()
    actual: int | None = pai_id
    while actual is not None and actual not in visto:
        visto.add(actual)
        if actual == lid:
            return "isso punha o local dentro de um que já está dentro dele"
        r = linha("SELECT pai_id FROM locais WHERE id=? AND user_id=?", (actual,uid))
        actual = r["pai_id"] if r else None
    return ""


def semear(uid: int) -> None:
    """Locais de arranque — dá para mudar tudo na app, mas começar com uma
    lista vazia obriga a criar um local antes de poder guardar a primeira bobine."""
    t = agora()
    for i, (nome, tipo) in enumerate([
            ("Oficina", "sala"), ("Estante A", "estante"), ("Caixa seca", "caixa"),
            ("Junto à impressora", "impressora")]):
        executa("INSERT INTO locais(user_id,nome,pai_id,tipo,ordem,criado_em)"
                " VALUES(?,?,?,?,?,?)", (uid, nome, None, tipo, i, t))


# ------------------------------------------------------ cache das imagens --

# As fotos ficam guardadas em disco e servidas por nós. Só o endereço da loja não
# chegava: no dia em que a Evolt mexer nos ficheiros, os cartões ficam com o
# quadrado partido. Assim a foto é nossa a partir do momento em que se adiciona.
IMG_MAX = 4 * 1024 * 1024
IMG_TIPOS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
             "image/gif": ".gif", "image/avif": ".avif"}
# Só se vai buscar imagens às lojas que a app conhece -- sem isto, /api/imagem
# era um proxy aberto para qualquer endereço que alguém quisesse pôr no campo.
IMG_HOSTS = (
    "evolt.pt", "corexy.pt", "reprap.pt", "qidi3d.com", "elegoo.com",
    "cdn.shopify.com", "shopify.com",
    "media-amazon.com", "ssl-images-amazon.com", "images-amazon.com",
)


def img_dir() -> Path:
    d = DATA_DIR / "imagens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def img_permitida(url: str) -> bool:
    try:
        u = urllib.parse.urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    h = u.hostname.lower()
    return any(h == d or h.endswith("." + d) for d in IMG_HOSTS)


def img_local(url: str) -> Path | None:
    """Devolve o ficheiro em cache, indo buscá-lo à loja da primeira vez."""
    if not img_permitida(url):
        return None
    nome = hashlib.sha256(url.encode()).hexdigest()[:32]
    for f in img_dir().glob(nome + ".*"):
        return f
    try:
        req = urllib.request.Request(url, headers={"User-Agent": lojas.UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if tipo not in IMG_TIPOS:
                return None
            dados = r.read(IMG_MAX + 1)
    except Exception:  # noqa: BLE001
        return None
    if not dados or len(dados) > IMG_MAX:
        return None
    destino = img_dir() / (nome + IMG_TIPOS[tipo])
    destino.write_bytes(dados)
    return destino


# ------------------------------------------------- ponte para o Fatia (token) --

def ficheiro_token() -> Path:
    return DATA_DIR / "bridge.token"


def token_ponte() -> str:
    """Segredo partilhado com o Fatia, em ficheiro só legível pelo dono.

    O Fatia corre no mesmo utilizador e na mesma máquina, por isso lê o ficheiro
    e faz o pedido do lado do servidor. Assim não há CORS nem cookies entre
    portas, e não há nada para copiar de uma app para a outra."""
    f = ficheiro_token()
    if f.exists():
        t = f.read_text().strip()
        if t:
            return t
    t = secrets.token_urlsafe(24)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(t)
    os.chmod(f, 0o600)
    return t


def dono() -> dict | None:
    """A ponte serve o primeiro utilizador registado: esta máquina é de uma
    pessoa só, tal como o Fatia e o Rumo."""
    return linha("SELECT id,email FROM users ORDER BY id LIMIT 1")


def filamentos_para_fatia(uid: int) -> list[dict]:
    """O Fatia quer {n, kg, portes}: nome, custo real por quilo, portes.

    O custo por quilo sai do que foi realmente pago pelas bobines que ainda cá
    estão (média ponderada pelo peso). Sem compras registadas, cai para o melhor
    preço observado nas lojas; sem isso, fica a zero e o Fatia pede o número."""
    saida = []
    for f in linhas("SELECT * FROM filamentos WHERE user_id=? ORDER BY marca,material,cor",
                    (uid,)):
        bs = linhas("SELECT * FROM bobines WHERE filamento_id=? AND user_id=?"
                    " AND estado!='arquivado'", (f["id"], uid))
        pago = sum((b["preco"] or 0) for b in bs if (b["preco"] or 0) > 0)
        kg = sum((b["peso_liquido_g"] or 0) for b in bs if (b["preco"] or 0) > 0) / 1000.0
        custo_kg = round(pago / kg, 2) if kg > 0 else 0.0
        if not custo_kg:
            m = linha("SELECT MIN(preco_kg) k FROM precos WHERE filamento_id=?"
                      " AND preco_kg>0 AND visto_em>?", (f["id"], agora() - 90 * 86400))
            custo_kg = round(m["k"], 2) if m and m["k"] else 0.0
        nome = " ".join(x for x in [f["marca"], f["material"], f["cor"]] if x).strip()
        saida.append({
            "n": nome or f"filamento #{f['id']}",
            "kg": custo_kg,
            "portes": 0,
            "material": f["material"],
            "cor": f["cor"],
            "cor_hex": f["cor_hex"],
            "marca": f["marca"],
            "restante_g": round(sum((b["restante_g"] or 0) for b in bs
                                    if b["estado"] != "vazio"), 1),
            "bobines": len([b for b in bs if b["estado"] != "vazio"]),
        })
    return saida


# ------------------------------------------------------------ preferências --

# O que a app assume quando se adiciona uma bobine, para não se andar a repetir
# os mesmos cliques. Ficam no servidor e não no browser porque decidem o que é
# GRAVADO, não como se vê -- e devem valer em qualquer aparelho.
PREFS_OMISSAO = {
    "caixa": True,            # bobines novas vêm na caixa
    "desenhar": False,        # preferir a bobine desenhada à foto da loja
    "seguir": True,           # seguir os preços dos filamentos novos
    "estado": "selado",       # estado inicial de uma bobine nova
    "diametro": 1.75,
    "local": 0,               # local por omissão (0 = nenhum)
}


def prefs_de(uid: int) -> dict:
    r = linha("SELECT valor FROM settings WHERE user_id=? AND chave='preferencias'", (uid,))
    guardadas = {}
    if r and r["valor"]:
        try:
            guardadas = json.loads(r["valor"]) or {}
        except Exception:  # noqa: BLE001
            guardadas = {}
    # só se aceitam chaves conhecidas: um cliente antigo não deve poder inventar
    return {k: guardadas.get(k, v) for k, v in PREFS_OMISSAO.items()}


# ------------------------------------------------------ seguimento de preços --

INTERVALO_PADRAO_H = 24
_tracker_stop = threading.Event()


def query_de(f: dict) -> str:
    if (f.get("seguir_query") or "").strip():
        return f["seguir_query"].strip()
    return " ".join(x for x in [f.get("marca"), f.get("material"), f.get("cor")] if x)


def _tem(campo: str, termo: str) -> bool:
    """O campo contém o termo, contando sinónimos ('black' acha 'preto')."""
    termo = (termo or "").strip()
    if not termo:
        return True
    return any(re.search(r"(?<![a-z0-9])" + re.escape(a), campo)
               for a in lojas._expande(lexicon.norm(termo)))


def casa_produto(p: dict, f: dict) -> bool:
    """O produto da loja é mesmo ESTE filamento?

    Marca e material são obrigatórios quando se sabem: sem esta trava, o
    histórico de um "AzureFilm ASA preto" enchia-se de PLA da Winkle porque a
    pontuação de texto só olha para quantas palavras casam, não para quais.
    A cor fica de fora de propósito — as lojas chamam-lhe "Deep Black",
    "Traffic Black" ou "azabache" e o preço não muda por causa disso."""
    campo = lexicon.norm(f"{p['titulo']} {p.get('marca', '')}")
    return _tem(campo, f.get("marca") or "") and _tem(campo, f.get("material") or "")


def actualiza_precos(filamento_id: int, uid: int | None = None) -> dict:
    """Vai às lojas e grava as observações deste filamento."""
    f = linha("SELECT * FROM filamentos WHERE id=?", (filamento_id,))
    if not f or (uid is not None and f["user_id"] != uid):
        return {"erro": "filamento desconhecido"}
    q = query_de(f)
    if not q.strip():
        return {"erro": "sem termos para pesquisar"}
    r = lojas.busca(q, limite=8)
    t = agora()
    gravados = 0
    # uma linha por loja: a melhor correspondência que essa loja tem hoje
    melhor_por_loja: dict[str, dict] = {}
    for p in r["resultados"]:
        if p["relevancia"] < 0.6 or p["preco"] is None:
            continue
        if not casa_produto(p, f):
            continue
        atual = melhor_por_loja.get(p["loja"])
        chave = (-p["relevancia"], p["preco_kg"] or p["preco"] or 9e9)
        if atual is None or chave < (-atual["relevancia"],
                                     atual["preco_kg"] or atual["preco"] or 9e9):
            melhor_por_loja[p["loja"]] = p
    for p in melhor_por_loja.values():
        executa("INSERT INTO precos(filamento_id,loja,titulo,url,preco,moeda,peso_g,"
                "preco_kg,stock,visto_em) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (filamento_id, p["loja"], p["titulo"], p["url"], p["preco"], p["moeda"],
                 p["peso_g"], p["preco_kg"], 1 if p["stock"] else 0, t))
        gravados += 1
    executa("UPDATE filamentos SET actualizado_em=? WHERE id=?", (t, filamento_id))
    return {"ok": True, "query": q, "gravados": gravados, "erros": r["erros"],
            "vistos": len(r["resultados"])}


def ciclo_tracker() -> None:
    """Corre em fundo: refresca os filamentos seguidos que já estão velhos.

    Poucos de cada vez e com pausa entre eles — cinco lojas vezes cinquenta
    filamentos de uma assentada era uma boa maneira de apanhar um bloqueio."""
    while not _tracker_stop.is_set():
        try:
            if DB is not None:
                limite = agora() - INTERVALO_PADRAO_H * 3600
                pendentes = linhas(
                    "SELECT f.id FROM filamentos f WHERE f.seguir=1 AND COALESCE("
                    " (SELECT MAX(visto_em) FROM precos p WHERE p.filamento_id=f.id), 0"
                    ") < ? ORDER BY 1 LIMIT 6", (limite,))
                for p in pendentes:
                    if _tracker_stop.is_set():
                        break
                    try:
                        actualiza_precos(p["id"])
                    except Exception:  # noqa: BLE001
                        pass
                    _tracker_stop.wait(20)
        except Exception:  # noqa: BLE001
            pass
        _tracker_stop.wait(1800)


# ------------------------------------------------------------------- HTTP --

CAMPOS_FILAMENTO = ["marca", "material", "cor", "cor_hex", "diametro", "peso_g",
                    "densidade", "temp_bico", "temp_mesa", "ref", "url", "imagem",
                    "loja", "etiquetas", "notas", "icone", "seguir", "seguir_query"]
CAMPOS_BOBINE = ["filamento_id", "etiqueta", "local_id", "peso_liquido_g", "restante_g",
                 "tara_g", "estado", "preco", "moeda", "comprado_em", "comprado_loja",
                 "comprado_url", "aberto_em", "caixa", "notas"]
CAMPOS_LOCAL = ["nome", "pai_id", "tipo", "notas", "capacidade", "ordem"]


class Handler(SimpleHTTPRequestHandler):
    server_version = f"Bobina/{VERSAO}"
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):  # menos ruído no log
        if os.environ.get("BOBINA_VERBOSE"):
            super().log_message(fmt, *args)

    # -------------------------------------------------------------- respostas --
    def _envia(self, corpo: bytes, tipo: str, code: int = 200,
               extra: dict | None = None) -> None:
        aceita = self.headers.get("Accept-Encoding", "")
        if (len(corpo) >= GZIP_MIN and "gzip" in aceita
                and any(tipo.startswith(t) for t in
                        ("text/", "application/json", "application/manifest",
                         "image/svg"))):
            corpo = gzip.compress(corpo, 6)
            extra = {**(extra or {}), "Content-Encoding": "gzip"}
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def json(self, dados: Any, code: int = 200, extra: dict | None = None) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self._envia(corpo, "application/json; charset=utf-8", code, extra)

    def erro(self, msg: str, code: int = 400) -> None:
        self.json({"erro": msg}, code)

    # ------------------------------------------------------------------ auth --
    def sessao(self) -> dict | None:
        bruto = self.headers.get("Cookie")
        if not bruto:
            return None
        try:
            c = cookies.SimpleCookie(bruto)
        except Exception:  # noqa: BLE001
            return None
        m = c.get(SESSION_COOKIE)
        return user_da_sessao(m.value) if m else None

    def exige(self) -> dict | None:
        u = self.sessao()
        if not u:
            self.erro("sessão expirada", 401)
            return None
        return u

    def corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace")) or {}
        except Exception:  # noqa: BLE001
            return {}

    # ------------------------------------------------------------------ GET --
    def do_GET(self) -> None:  # noqa: N802
        u = urllib.parse.urlparse(self.path)
        caminho, q = u.path, urllib.parse.parse_qs(u.query)

        if caminho == "/api/health":
            return self.json({"ok": True, "app": "bobina", "versao": VERSAO})
        if caminho == "/api/lexicon":
            return self.json(lexicon.payload(),
                             extra={"Cache-Control": "public, max-age=3600"})
        if caminho == "/api/lojas":
            return self.json({"lojas": lojas.LOJAS})

        # ponte do Fatia: autenticada por token, sem cookie e sem CORS no browser
        if caminho == "/api/fatia/filamentos":
            tok = (q.get("token") or [""])[0]
            if not hmac.compare_digest(tok, token_ponte()):
                return self.erro("token inválido", 403)
            d = dono()
            if not d:
                return self.json({"filamentos": []})
            return self.json({"filamentos": filamentos_para_fatia(d["id"]),
                              "fonte": "bobina", "versao": VERSAO})

        if caminho == "/api/auth/me":
            us = self.sessao()
            tem = linha("SELECT COUNT(*) n FROM users")
            return self.json({"user": us, "primeiro_arranque": (tem or {}).get("n", 0) == 0})

        if not caminho.startswith("/api/"):
            if caminho == "/":
                self.path = "/index.html"
            return super().do_GET()

        us = self.exige()
        if not us:
            return
        uid = us["id"]

        if caminho == "/api/imagem":
            alvo = (q.get("u") or [""])[0]
            f = img_local(alvo)
            if not f:
                return self.erro("imagem indisponível", 404)
            tipo = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            corpo = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "public, max-age=2592000, immutable")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)
            return
        if caminho == "/api/inventario":
            return self.json(self._inventario(uid))
        if caminho == "/api/precos":
            fid = int((q.get("filamento_id") or [0])[0] or 0)
            if not fid:
                return self.erro("falta filamento_id")
            if not linha("SELECT 1 FROM filamentos WHERE id=? AND user_id=?", (fid, uid)):
                return self.erro("filamento desconhecido", 404)
            return self.json({"precos": linhas(
                "SELECT * FROM precos WHERE filamento_id=? ORDER BY visto_em DESC LIMIT 400",
                (fid,))})
        if caminho == "/api/lojas/busca":
            termo = (q.get("q") or [""])[0].strip()
            if len(termo) < 2:
                return self.erro("pesquisa demasiado curta")
            alvo = [s for s in (q.get("lojas") or [""])[0].split(",") if s] or None
            try:
                return self.json(lojas.busca(termo, alvo, limite=10))
            except Exception as e:  # noqa: BLE001
                return self.erro(f"lojas indisponíveis: {e}", 502)
        if caminho == "/api/ponte":
            # o endereço sai do Host do próprio pedido: quem abrir a app por
            # outro nome ou noutra porta recebe o endereço certo, em vez de um
            # hostname escrito à mão que só existia numa máquina
            host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_address[1]}"
            return self.json({
                "token": token_ponte(),
                "url": f"http://{host}/api/fatia/filamentos?token={token_ponte()}",
                "ficheiro": str(ficheiro_token()),
            })
        if caminho == "/api/definicoes":
            d = {r["chave"]: r["valor"] for r in
                 linhas("SELECT chave,valor FROM settings WHERE user_id=?", (uid,))}
            fornecedor = d.get("fornecedor") or agente.PADRAO
            # as chaves nunca saem daqui em claro: só "tem/não tem" e os 4 finais
            chaves = {}
            for f, meta in agente.FORNECEDORES.items():
                k = d.get(meta["chave"]) or ""
                chaves[f] = {"nome": meta["nome"], "tem": bool(k),
                             "fim": k[-4:] if k else "",
                             "modelo": d.get(f"modelo_{f}") or agente.MODELOS[f]}
            return self.json({
                "fornecedor": fornecedor,
                "fornecedores": chaves,
                "intervalo_precos_h": int(d.get("intervalo_precos_h") or INTERVALO_PADRAO_H),
                "preferencias": prefs_de(uid),
            })
        if caminho == "/api/agente/planos":
            return self.json({"planos": linhas(
                "SELECT id,instrucoes,estado,criado_em,aplicado_em,plano FROM planos"
                " WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,))})
        if caminho == "/api/export":
            return self.json({
                "app": "bobina", "versao": VERSAO, "exportado_em": agora(),
                "locais": linhas("SELECT * FROM locais WHERE user_id=?", (uid,)),
                "filamentos": linhas("SELECT * FROM filamentos WHERE user_id=?", (uid,)),
                "bobines": linhas("SELECT * FROM bobines WHERE user_id=?", (uid,)),
                "precos": linhas(
                    "SELECT p.* FROM precos p JOIN filamentos f ON f.id=p.filamento_id"
                    " WHERE f.user_id=?", (uid,)),
            }, extra={"Content-Disposition":
                      f'attachment; filename="bobina-{time.strftime("%Y%m%d")}.json"'})
        return self.erro("rota desconhecida", 404)

    def do_HEAD(self) -> None:  # noqa: N802
        if urllib.parse.urlparse(self.path).path == "/api/health":
            return self.json({"ok": True})
        return super().do_HEAD()

    def _inventario(self, uid: int) -> dict:
        fs = linhas("SELECT * FROM filamentos WHERE user_id=?", (uid,))
        bs = linhas("SELECT * FROM bobines WHERE user_id=?", (uid,))
        # último preço por loja de cada filamento, numa consulta só
        melhores = linhas(
            "SELECT p.filamento_id, p.loja, p.preco, p.preco_kg, p.url, p.titulo,"
            " p.stock, p.visto_em FROM precos p JOIN ("
            "  SELECT filamento_id, loja, MAX(visto_em) v FROM precos"
            "  GROUP BY filamento_id, loja) m"
            " ON m.filamento_id=p.filamento_id AND m.loja=p.loja AND m.v=p.visto_em"
            " JOIN filamentos f ON f.id=p.filamento_id WHERE f.user_id=?", (uid,))
        por_fil: dict[int, list[dict]] = {}
        for m in melhores:
            por_fil.setdefault(m["filamento_id"], []).append(m)
        return {
            "locais": linhas("SELECT * FROM locais WHERE user_id=? ORDER BY ordem,nome",
                             (uid,)),
            "filamentos": fs,
            "bobines": bs,
            "precos": por_fil,
            "lojas": lojas.LOJAS,
            "versao": VERSAO,
        }

    # ----------------------------------------------------------- POST/PATCH --
    def do_POST(self) -> None:  # noqa: N802
        self._escreve("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._escreve("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._escreve("DELETE")

    def _escreve(self, metodo: str) -> None:
        u = urllib.parse.urlparse(self.path)
        caminho, q = u.path, urllib.parse.parse_qs(u.query)
        corpo = self.corpo()

        if caminho == "/api/auth/register":
            email = (corpo.get("email") or "").strip().lower()
            pw = corpo.get("password") or ""
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                return self.erro("email inválido")
            if len(pw) < 8:
                return self.erro("password com pelo menos 8 caracteres")
            n = (linha("SELECT COUNT(*) n FROM users") or {}).get("n", 0)
            if n and not self.sessao():
                return self.erro("registo fechado", 403)
            if linha("SELECT 1 FROM users WHERE email=?", (email,)):
                return self.erro("email já registado")
            uid = cria_user(email, pw)
            tok = nova_sessao(uid)
            return self.json({"ok": True}, extra=self._cookie(tok))

        if caminho == "/api/auth/login":
            us = verifica_user(corpo.get("email") or "", corpo.get("password") or "")
            if not us:
                return self.erro("credenciais inválidas", 401)
            tok = nova_sessao(us["id"])
            return self.json({"ok": True}, extra=self._cookie(tok))

        if caminho == "/api/auth/logout":
            bruto = self.headers.get("Cookie")
            if bruto:
                c = cookies.SimpleCookie(bruto)
                if c.get(SESSION_COOKIE):
                    executa("DELETE FROM sessions WHERE token=?", (c[SESSION_COOKIE].value,))
            return self.json({"ok": True}, extra={
                "Set-Cookie": f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})

        us = self.exige()
        if not us:
            return
        uid = us["id"]
        t = agora()

        # ---- locais ----
        if caminho == "/api/locais" and metodo == "POST":
            campos = {k: corpo.get(k) for k in CAMPOS_LOCAL if k in corpo}
            if not (campos.get("nome") or "").strip():
                return self.erro("o local precisa de nome")
            if campos.get("pai_id") and not linha(
                    "SELECT 1 FROM locais WHERE id=? AND user_id=?", (campos["pai_id"], uid)):
                return self.erro("esse local não existe")
            cols = ["user_id", "criado_em"] + list(campos)
            vals = [uid, t] + [campos[k] for k in campos]
            nid = executa(f"INSERT INTO locais({','.join(cols)})"
                          f" VALUES({','.join('?' * len(cols))})", tuple(vals))
            return self.json({"ok": True, "id": nid})
        m = re.match(r"^/api/locais/(\d+)$", caminho)
        if m:
            lid = int(m.group(1))
            if not linha("SELECT 1 FROM locais WHERE id=? AND user_id=?", (lid, uid)):
                return self.erro("local desconhecido", 404)
            if metodo == "DELETE":
                executa("DELETE FROM locais WHERE id=? AND user_id=?", (lid, uid))
                return self.json({"ok": True})
            campos = {k: corpo[k] for k in CAMPOS_LOCAL if k in corpo}
            if "pai_id" in campos:
                bruto = campos["pai_id"]
                pai = int(bruto) if str(bruto or "").strip() not in ("", "0", "None") else None
                problema = valida_pai(uid, lid, pai)
                if problema:
                    return self.erro(problema)
                campos["pai_id"] = pai
            if campos:
                executa(f"UPDATE locais SET {','.join(f'{k}=?' for k in campos)}"
                        " WHERE id=? AND user_id=?", (*campos.values(), lid, uid))
            return self.json({"ok": True})

        # ---- filamentos ----
        if caminho == "/api/filamentos" and metodo == "POST":
            campos = {k: corpo[k] for k in CAMPOS_FILAMENTO if k in corpo}
            if not any((campos.get(k) or "") for k in ("marca", "material", "cor")):
                return self.erro("dá-lhe pelo menos marca, material ou cor")
            cols = ["user_id", "criado_em", "actualizado_em"] + list(campos)
            vals = [uid, t, t] + [campos[k] for k in campos]
            nid = executa(f"INSERT INTO filamentos({','.join(cols)})"
                          f" VALUES({','.join('?' * len(cols))})", tuple(vals))
            return self.json({"ok": True, "id": nid})
        m = re.match(r"^/api/filamentos/(\d+)$", caminho)
        if m:
            fid = int(m.group(1))
            if not linha("SELECT 1 FROM filamentos WHERE id=? AND user_id=?", (fid, uid)):
                return self.erro("filamento desconhecido", 404)
            if metodo == "DELETE":
                executa("DELETE FROM filamentos WHERE id=? AND user_id=?", (fid, uid))
                return self.json({"ok": True})
            campos = {k: corpo[k] for k in CAMPOS_FILAMENTO if k in corpo}
            arrastadas = 0
            if "peso_g" in campos:
                antes = linha("SELECT peso_g FROM filamentos WHERE id=? AND user_id=?",
                              (fid, uid)) or {}
                velho, novo_peso = float(antes.get("peso_g") or 0), float(campos["peso_g"] or 0)
                if novo_peso > 0 and velho > 0 and velho != novo_peso:
                    # Corrigir 1000 para 750 num filamento tem de corrigir as
                    # bobines dele. Só as que ainda estavam no peso antigo: uma
                    # que já tenha sido pesada à mão é dado real e não se toca --
                    # apenas se apara o restante ao que a bobine comporta.
                    arrastadas = altera(
                        "UPDATE bobines SET peso_liquido_g=?, actualizado_em=?"
                        " WHERE filamento_id=? AND user_id=? AND peso_liquido_g=?",
                        (novo_peso, t, fid, uid, velho))
                    executa("UPDATE bobines SET restante_g=peso_liquido_g"
                            " WHERE filamento_id=? AND user_id=? AND restante_g>peso_liquido_g",
                            (fid, uid))
            if campos:
                executa(f"UPDATE filamentos SET {','.join(f'{k}=?' for k in campos)},"
                        " actualizado_em=? WHERE id=? AND user_id=?",
                        (*campos.values(), t, fid, uid))
            return self.json({"ok": True, "bobines_ajustadas": arrastadas})
        m = re.match(r"^/api/filamentos/(\d+)/precos$", caminho)
        if m and metodo == "POST":
            return self.json(actualiza_precos(int(m.group(1)), uid))

        # ---- bobines ----
        if caminho == "/api/bobines" and metodo == "POST":
            campos = {k: corpo[k] for k in CAMPOS_BOBINE if k in corpo}
            fid = int(campos.get("filamento_id") or 0)
            f = linha("SELECT peso_g FROM filamentos WHERE id=? AND user_id=?", (fid, uid))
            if not f:
                return self.erro("essa bobine tem de apontar para um filamento teu")
            # Sem isto a coluna caía no seu DEFAULT de 1000 g e uma bobine de um
            # filamento de 750 g nascia com 1000 g -- o "restante" ficava a mentir
            # desde o primeiro dia. O peso do filamento é que manda.
            campos.setdefault("peso_liquido_g", float(f["peso_g"] or 1000))
            campos.setdefault("restante_g", float(campos["peso_liquido_g"]))
            campos["restante_g"] = _apara(campos["restante_g"], campos["peso_liquido_g"])
            campos["estado"] = _estado_pelo_peso(
                campos.get("estado", "selado"), campos["restante_g"], campos["peso_liquido_g"])
            cols = ["user_id", "criado_em", "actualizado_em"] + list(campos)
            vals = [uid, t, t] + [campos[k] for k in campos]
            nid = executa(f"INSERT INTO bobines({','.join(cols)})"
                          f" VALUES({','.join('?' * len(cols))})", tuple(vals))
            return self.json({"ok": True, "id": nid})
        m = re.match(r"^/api/bobines/(\d+)$", caminho)
        if m:
            bid = int(m.group(1))
            if not linha("SELECT 1 FROM bobines WHERE id=? AND user_id=?", (bid, uid)):
                return self.erro("bobine desconhecida", 404)
            if metodo == "DELETE":
                executa("DELETE FROM bobines WHERE id=? AND user_id=?", (bid, uid))
                return self.json({"ok": True})
            campos = {k: corpo[k] for k in CAMPOS_BOBINE if k in corpo}
            if "restante_g" in campos or "peso_liquido_g" in campos:
                b = linha("SELECT peso_liquido_g, restante_g FROM bobines"
                          " WHERE id=? AND user_id=?", (bid, uid)) or {}
                peso = float(campos.get("peso_liquido_g", b.get("peso_liquido_g")) or 0)
                rest = float(campos.get("restante_g", b.get("restante_g")) or 0)
                campos["restante_g"] = _apara(rest, peso)
                estado_actual = campos.get("estado", (b.get("estado") or "selado"))
                campos["estado"] = _estado_pelo_peso(estado_actual, campos["restante_g"], peso)
            if campos:
                executa(f"UPDATE bobines SET {','.join(f'{k}=?' for k in campos)},"
                        " actualizado_em=? WHERE id=? AND user_id=?",
                        (*campos.values(), t, bid, uid))
            return self.json({"ok": True})

        # ---- definições ----
        if caminho == "/api/definicoes" and metodo == "PATCH":
            if "preferencias" in corpo and isinstance(corpo["preferencias"], dict):
                novas = {k: corpo["preferencias"].get(k, v)
                         for k, v in prefs_de(uid).items()}
                executa("INSERT INTO settings(user_id,chave,valor) VALUES(?,?,?)"
                        " ON CONFLICT(user_id,chave) DO UPDATE SET valor=excluded.valor",
                        (uid, "preferencias", json.dumps(novas, ensure_ascii=False)))
            permitidas = ["fornecedor", "intervalo_precos_h"]
            permitidas += [m["chave"] for m in agente.FORNECEDORES.values()]
            permitidas += [f"modelo_{f}" for f in agente.FORNECEDORES]
            for chave in permitidas:
                if chave in corpo:
                    executa("INSERT INTO settings(user_id,chave,valor) VALUES(?,?,?)"
                            " ON CONFLICT(user_id,chave) DO UPDATE SET valor=excluded.valor",
                            (uid, chave, str(corpo[chave])))
            return self.json({"ok": True})

        # ---- agente de arrumação ----
        if caminho == "/api/agente/plano" and metodo == "POST":
            return self.json(self._plano(uid, corpo, t))
        if caminho == "/api/agente/aplicar" and metodo == "POST":
            return self.json(self._aplicar(uid, int(corpo.get("plano_id") or 0), t))
        if caminho == "/api/agente/anular" and metodo == "POST":
            return self.json(self._anular(uid, int(corpo.get("plano_id") or 0)))

        # ---- adicionar a partir de um resultado de loja, num pedido só ----
        if caminho == "/api/adicionar" and metodo == "POST":
            return self.json(self._adicionar(uid, corpo, t))

        return self.erro("rota desconhecida", 404)

    def _adicionar(self, uid: int, corpo: dict, t: int) -> dict:
        """Cria (ou reaproveita) o filamento e junta-lhe N bobines de uma vez.

        É isto que faz o "adicionar" ser um clique: o cartão da loja traz marca,
        material, cor, peso, preço e URL já preenchidos e daqui sai tudo gravado."""
        f = corpo.get("filamento") or {}
        fid = int(corpo.get("filamento_id") or 0)
        juntou = None
        if not fid:
            # já existe um igual? a comparação é por significado, não por letras
            existente = filamento_igual(uid, f)
            if existente:
                fid = existente["id"]
                juntou = " ".join(x for x in (existente["marca"], existente["material"],
                                              existente["cor"]) if x)
            else:
                campos = {k: f[k] for k in CAMPOS_FILAMENTO if k in f}
                cols = ["user_id", "criado_em", "actualizado_em"] + list(campos)
                vals = [uid, t, t] + [campos[k] for k in campos]
                fid = executa(f"INSERT INTO filamentos({','.join(cols)})"
                              f" VALUES({','.join('?' * len(cols))})", tuple(vals))
        # puxar a foto já, enquanto se sabe que o endereço é bom
        if (f.get("imagem") or "").strip():
            try:
                img_local(f["imagem"])
            except Exception:  # noqa: BLE001 - foto é um extra, não trava nada
                pass
        quantas = max(1, min(int(corpo.get("quantidade") or 1), 50))
        b = corpo.get("bobine") or {}
        peso = float(b.get("peso_liquido_g") or f.get("peso_g") or 1000)
        ids = []
        for _ in range(quantas):
            campos = {k: b[k] for k in CAMPOS_BOBINE if k in b}
            rest = _apara(b.get("restante_g") if b.get("restante_g") is not None else peso, peso)
            campos.update({"filamento_id": fid, "peso_liquido_g": peso, "restante_g": rest,
                           "estado": _estado_pelo_peso(
                               campos.get("estado") or b.get("estado") or "selado", rest, peso)})
            cols = ["user_id", "criado_em", "actualizado_em"] + list(campos)
            vals = [uid, t, t] + [campos[k] for k in campos]
            ids.append(executa(f"INSERT INTO bobines({','.join(cols)})"
                               f" VALUES({','.join('?' * len(cols))})", tuple(vals)))
        n = linha("SELECT COUNT(*) n FROM bobines WHERE filamento_id=? AND user_id=?",
                  (fid, uid))
        return {"ok": True, "filamento_id": fid, "bobines": ids,
                "juntou": juntou, "total_bobines": (n or {}).get("n", len(ids))}

    # ------------------------------------------------------ agente (preview) --
    def _plano(self, uid: int, corpo: dict, t: int) -> dict:
        d = {r["chave"]: r["valor"] for r in
             linhas("SELECT chave,valor FROM settings WHERE user_id=?", (uid,))}
        fornecedor = str(corpo.get("fornecedor") or d.get("fornecedor") or agente.PADRAO)
        if fornecedor not in agente.FORNECEDORES:
            fornecedor = agente.PADRAO
        meta = agente.FORNECEDORES[fornecedor]
        api_key = d.get(meta["chave"]) or ""
        if not api_key and fornecedor == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
        if not api_key:
            return {"erro": f"Põe a tua chave do {meta['nome']} em Definições para usar o agente."}
        inv = self._inventario(uid)
        instrucoes = str(corpo.get("instrucoes") or "")
        ok, r = agente.pede_plano(api_key, inv["locais"], inv["filamentos"],
                                  inv["bobines"], instrucoes,
                                  d.get(f"modelo_{fornecedor}") or agente.MODELOS[fornecedor],
                                  fornecedor)
        if not ok:
            return {"erro": r}
        pid = executa("INSERT INTO planos(user_id,instrucoes,plano,estado,criado_em)"
                      " VALUES(?,?,?,?,?)",
                      (uid, instrucoes, json.dumps(r, ensure_ascii=False), "proposto", t))
        # nada foi escrito no inventário: isto é só a proposta
        return {"ok": True, "plano_id": pid, "plano": r}

    # ------------------------------------------------------- agente (apply) --
    def _aplicar(self, uid: int, pid: int, t: int) -> dict:
        p = linha("SELECT * FROM planos WHERE id=? AND user_id=?", (pid, uid))
        if not p:
            return {"erro": "plano desconhecido"}
        if p["estado"] == "aplicado":
            return {"erro": "esse plano já foi aplicado"}
        plano = json.loads(p["plano"])
        locais = linhas("SELECT * FROM locais WHERE user_id=?", (uid,))
        por_nome = {(l["nome"] or "").strip().lower(): l["id"] for l in locais}
        reversao: dict = {"criados": [], "renomeados": [], "movidos": []}
        feito = {"criados": 0, "renomeados": 0, "movidos": 0}
        saltados: list[str] = []

        for novo in plano.get("locais_novos", []):
            nome = str(novo.get("nome") or "").strip()
            if not nome or nome.lower() in por_nome:
                continue
            pai = str(novo.get("pai") or "").strip().lower()
            nid = executa("INSERT INTO locais(user_id,nome,pai_id,tipo,capacidade,"
                          "criado_em) VALUES(?,?,?,?,?,?)",
                          (uid, nome, por_nome.get(pai), str(novo.get("tipo") or "prateleira"),
                           int(novo.get("capacidade") or 0), t))
            por_nome[nome.lower()] = nid
            reversao["criados"].append(nid)
            feito["criados"] += 1

        for ren in plano.get("locais_renomear", []):
            lid = int(ren.get("id") or 0)
            nome_novo = str(ren.get("nome_novo") or "").strip()
            antigo = linha("SELECT nome FROM locais WHERE id=? AND user_id=?", (lid, uid))
            if not antigo or not nome_novo:
                saltados.append(f"renomear local {lid}: não existe")
                continue
            executa("UPDATE locais SET nome=? WHERE id=? AND user_id=?", (nome_novo, lid, uid))
            reversao["renomeados"].append({"id": lid, "nome": antigo["nome"]})
            por_nome.pop((antigo["nome"] or "").strip().lower(), None)
            por_nome[nome_novo.lower()] = lid
            feito["renomeados"] += 1

        for mov in plano.get("movimentos", []):
            bid = int(mov.get("bobine_id") or 0)
            destino = por_nome.get(str(mov.get("para") or "").strip().lower())
            b = linha("SELECT local_id FROM bobines WHERE id=? AND user_id=?", (bid, uid))
            if not b:
                saltados.append(f"bobine {bid}: não existe")
                continue
            if destino is None:
                saltados.append(f"bobine {bid}: local \"{mov.get('para')}\" não existe")
                continue
            executa("UPDATE bobines SET local_id=?, actualizado_em=? WHERE id=? AND user_id=?",
                    (destino, t, bid, uid))
            reversao["movidos"].append({"bobine_id": bid, "local_id": b["local_id"]})
            feito["movidos"] += 1

        executa("UPDATE planos SET estado='aplicado', aplicado_em=?, reversao=? WHERE id=?",
                (t, json.dumps(reversao, ensure_ascii=False), pid))
        return {"ok": True, "feito": feito, "saltados": saltados}

    def _anular(self, uid: int, pid: int) -> dict:
        p = linha("SELECT * FROM planos WHERE id=? AND user_id=?", (pid, uid))
        if not p or p["estado"] != "aplicado":
            return {"erro": "só se anula um plano que tenha sido aplicado"}
        rev = json.loads(p["reversao"] or "{}")
        t = agora()
        for m in rev.get("movidos", []):
            executa("UPDATE bobines SET local_id=?, actualizado_em=? WHERE id=? AND user_id=?",
                    (m.get("local_id"), t, m["bobine_id"], uid))
        for r in rev.get("renomeados", []):
            executa("UPDATE locais SET nome=? WHERE id=? AND user_id=?",
                    (r["nome"], r["id"], uid))
        # locais criados só desaparecem se ficaram vazios — nunca levar bobines à frente
        presos = []
        for lid in rev.get("criados", []):
            n = linha("SELECT COUNT(*) n FROM bobines WHERE local_id=?", (lid,))
            if (n or {}).get("n", 0):
                presos.append(lid)
                continue
            executa("DELETE FROM locais WHERE id=? AND user_id=?", (lid, uid))
        executa("UPDATE planos SET estado='anulado' WHERE id=?", (pid,))
        return {"ok": True, "locais_mantidos": presos}

    def _cookie(self, token: str) -> dict:
        return {"Set-Cookie":
                f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_DIAS * 86400};"
                " HttpOnly; SameSite=Lax"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Bobina — logística de filamento 3D")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--data-dir", default=str(Path.home() / ".local/share/bobina"))
    args = ap.parse_args()

    abre_db(Path(args.data_dir))
    token_ponte()
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    threading.Thread(target=ciclo_tracker, daemon=True).start()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    print(f"Bobina {VERSAO} em http://{args.host}:{args.port}  (dados: {args.data_dir})",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _tracker_stop.set()
        srv.server_close()


if __name__ == "__main__":
    main()
