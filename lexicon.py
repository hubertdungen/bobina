#!/usr/bin/env python3
"""Léxico do Bobina: sinónimos PT/EN/DE/ES para marcas, materiais, cores e formatos.

A pesquisa da app é feita no browser, mas o léxico vive aqui e é servido em
/api/lexicon -- assim há UMA tabela só, partilhada entre a pesquisa do inventário
e o casamento dos resultados das lojas. Cada grupo é {canónico: [aliases]}.

Regra de ouro dos aliases: escrevem-se já normalizados (minúsculas, sem acentos),
porque é assim que são comparados. `norm()` faz a normalização dos dois lados.
"""
from __future__ import annotations

import re
import unicodedata

# Uma palavra como "azure" é marca (AzureFilm) E cor (azul-claro). Não se escolhe:
# o token expande para os dois grupos e casa com qualquer um deles. É o que faz
# funcionar o "ASA Azure Preto" do enunciado sem escrever "azurefilm".

CORES: dict[str, list[str]] = {
    "preto": ["black", "negro", "noir", "schwarz", "nero", "jet black", "deep black",
              "carbon black", "midnight", "obsidian", "onyx", "ebony", "pitch black",
              "traffic black", "space black", "charcoal"],
    "branco": ["white", "blanc", "weiss", "bianco", "blanco", "pure white", "cotton white",
               "natural white", "snow", "neve", "polar", "traffic white", "arctic"],
    "cinzento": ["grey", "gray", "cinza", "grigio", "gris", "grau", "anthracite", "antracite",
                 "graphite", "grafite", "slate", "ardosia", "ash", "cinza escuro", "nardo",
                 "gunmetal", "steel", "aco", "titanium", "titanio", "concrete", "cimento"],
    "prateado": ["silver", "prata", "metallic silver", "argento", "silber", "chrome", "cromado",
                 "aluminium", "aluminio", "platinum", "platina"],
    "dourado": ["gold", "ouro", "golden", "oro", "gelb gold", "champagne", "brass gold"],
    "bronze": ["bronze", "brass", "latao", "antique bronze"],
    "cobre": ["copper", "cobre", "rose gold", "ouro rosa"],
    "azul": ["blue", "bleu", "blau", "blu", "azul", "navy", "azul marinho", "marinho", "marine",
             "cobalt", "cobalto", "sky", "sky blue", "celeste", "ceu", "azure", "azzurro",
             "ultramarine", "ultramarino", "sapphire", "safira", "denim", "royal blue",
             "azul royal", "petrol", "petroleo", "indigo", "steel blue", "ice blue", "gelo"],
    "turquesa": ["turquoise", "turquesa", "teal", "cyan", "ciano", "aqua", "agua", "aquamarine",
                 "agua marinha", "mint blue", "verde agua", "peacock"],
    "verde": ["green", "vert", "grun", "gruen", "verde", "olive", "oliva", "olivgrun",
              "mint", "menta", "lime", "lima", "limao verde", "forest", "floresta", "emerald",
              "esmeralda", "sage", "salvia", "pistachio", "pistacho", "army", "military",
              "militar", "khaki green", "apple green", "verde maca", "grass", "relva",
              "traffic green", "neon green", "verde neon"],
    "amarelo": ["yellow", "jaune", "gelb", "giallo", "amarillo", "amarelo", "lemon", "limao",
                "mustard", "mostarda", "sunflower", "girassol", "sun", "sol", "banana",
                "traffic yellow", "canary", "canario", "neon yellow"],
    "laranja": ["orange", "arancione", "naranja", "laranja", "tangerine", "tangerina",
                "amber", "ambar", "apricot", "alperce", "peach", "pessego", "pumpkin",
                "abobora", "traffic orange", "neon orange", "rust", "ferrugem"],
    "vermelho": ["red", "rouge", "rot", "rosso", "rojo", "vermelho", "crimson", "carmim",
                 "scarlet", "escarlate", "ruby", "rubi", "cherry", "cereja", "blood",
                 "sangue", "traffic red", "fire engine red", "wine", "vinho", "burgundy",
                 "bordeaux", "bordo", "brick", "tijolo", "coral", "salmon", "salmao"],
    "rosa": ["pink", "rose", "rosa", "pinke", "fuchsia", "fucsia", "magenta", "hot pink",
             "rosa choque", "pastel pink", "rosa pastel", "blush", "bubblegum", "flamingo"],
    "roxo": ["purple", "violet", "violeta", "roxo", "lila", "lilas", "lilac", "lavender",
             "lavanda", "plum", "ameixa", "grape", "uva", "aubergine", "beringela",
             "mauve", "amethyst", "ametista", "indigo purple"],
    "castanho": ["brown", "marron", "braun", "marrone", "marrom", "castanho", "chocolate",
                 "coffee", "cafe", "wood", "madeira", "walnut", "nogueira", "oak", "carvalho",
                 "terracotta", "terracota", "caramel", "caramelo", "tan", "mahogany",
                 "mogno", "leather", "cabedal", "cork", "cortica"],
    "bege": ["beige", "bege", "sand", "areia", "cream", "creme", "ivory", "marfim",
             "khaki", "caqui", "nude", "bone", "osso", "vanilla", "baunilha", "almond",
             "amendoa", "linen", "linho", "wheat", "trigo"],
    "transparente": ["transparent", "clear", "transparente", "natural", "cristal", "crystal",
                     "translucent", "translucido", "glass", "vidro", "colorless", "sem cor",
                     "incolor", "klar", "naturel", "uncolored"],
    "multicor": ["rainbow", "arco iris", "arcoiris", "multicolor", "multi color", "gradient",
                 "gradiente", "tricolor", "dual color", "duas cores", "galaxy", "galaxia",
                 "coextrusion"],
}

MARCAS: dict[str, list[str]] = {
    "azurefilm": ["azure", "azure film", "azurefilm"],
    "esun": ["esun", "e sun", "e-sun", "epla", "esun pla"],
    "sunlu": ["sunlu"],
    "polymaker": ["polymaker", "polylite", "polyterra", "polymax", "polyflex", "polysonic",
                  "polymide", "panchroma"],
    "prusa": ["prusa", "prusament", "prusa polymers", "prusa original"],
    "bambulab": ["bambu", "bambulab", "bambu lab", "bambu studio"],
    "spectrum": ["spectrum", "spectrum filaments", "spectrumfilaments", "smart abs"],
    "elegoo": ["elegoo", "elegoo rapid"],
    "qidi": ["qidi", "qidi tech", "qidi3d", "qidi technology"],
    "creality": ["creality", "creality hyper", "ender filament", "cr pla"],
    "anycubic": ["anycubic"],
    "extrudr": ["extrudr", "greentec", "greentec pro", "xpetg", "durapro"],
    "fillamentum": ["fillamentum", "extrafill", "timberfill", "vinyl"],
    "3djake": ["3djake", "3d jake", "jake", "ecopla", "nicefilaments"],
    "eryone": ["eryone"],
    "overture": ["overture"],
    "devildesign": ["devil", "devil design", "devildesign"],
    "fiberlogy": ["fiberlogy", "fiberflex", "fibersilk", "fibersatin", "easy pla", "easy petg"],
    "fiberthree": ["fiberthree", "f3", "fiber three"],
    "colorfabb": ["colorfabb", "ngen", "woodfill", "corkfill", "bronzefill"],
    "formfutura": ["formfutura", "easyfil", "hdglass", "titanx", "atlas", "python flex"],
    "filamentpm": ["filament pm", "filamentpm", "plastspol"],
    "rosa3d": ["rosa", "rosa3d", "rosa 3d", "refill"],
    "printme": ["print me", "printme", "ecoline", "swift pet"],
    "nobufil": ["nobufil"],
    "addnorth": ["addnorth", "add north", "add:north", "x pla", "textura", "adamant"],
    "verbatim": ["verbatim", "durabio"],
    "kimya": ["kimya", "armor"],
    "recreus": ["recreus", "filaflex"],
    "smartfil": ["smartfil", "smart materials"],
    "filoalfa": ["filoalfa", "alfaplus", "grafylon"],
    "treed": ["treed", "treed filaments", "monumental"],
    "kexcelled": ["kexcelled"],
    "geeetech": ["geeetech"],
    "amolen": ["amolen"],
    "hatchbox": ["hatchbox"],
    "flashforge": ["flashforge", "adventurer filament"],
    "kingroon": ["kingroon"],
    "tinmorry": ["tinmorry"],
    "jayo": ["jayo"],
    "ziro": ["ziro"],
    "torwell": ["torwell"],
    "iemai": ["iemai"],
    "ultimaker": ["ultimaker", "um filament"],
    "raise3d": ["raise3d", "raise 3d", "premium pla"],
    "ninjatek": ["ninjatek", "ninjaflex", "cheetah", "armadillo"],
    "matterhackers": ["matterhackers", "build series", "pro series", "nylonx"],
    "protopasta": ["protopasta", "proto pasta"],
    "sainsmart": ["sainsmart"],
    "winkle": ["winkle"],
    "herz": ["herz", "herz filament"],
    "noctuo": ["noctuo"],
    "realfilament": ["real filament", "realfilament", "real"],
    "francofil": ["francofil"],
    "filaticum": ["filaticum"],
    "gembird": ["gembird"],
    "dasfilament": ["das filament", "dasfilament"],
    "filamentworld": ["filamentworld", "filament world"],
    "evolt": ["evolt"],
    "corexy": ["corexy", "core xy"],
}

MATERIAIS: dict[str, list[str]] = {
    "pla": ["pla", "pla+", "pla plus", "plaplus", "pla pro", "tough pla", "ecopla", "ingeo",
            "hf pla", "high speed pla", "pla basic", "pla matte", "pla silk", "pla meta",
            "polyterra", "polylite pla", "pla lw", "lw pla", "lightweight pla", "pla aero"],
    "petg": ["petg", "pet g", "pet-g", "rpetg", "petg hf", "xpetg", "ngen", "swift pet",
             "easy petg", "petg basic"],
    "pctg": ["pctg", "pct g"],
    "abs": ["abs", "abs+", "abs plus", "smart abs", "abs gf", "absx"],
    "asa": ["asa", "asa x", "asa-x", "asax", "asa aero", "asa cf", "asa gf"],
    "tpu": ["tpu", "tpe", "flex", "flexible", "flexivel", "95a", "98a", "85a", "filaflex",
            "ninjaflex", "polyflex", "fiberflex", "elastico", "elastic", "soft"],
    "nylon": ["nylon", "pa", "pa6", "pa12", "pa11", "poliamida", "polyamide", "nylonx",
              "pa6 gf", "pa cf", "ppa"],
    "pc": ["pc", "policarbonato", "polycarbonate", "pc cf", "pc max", "pc abs"],
    "pva": ["pva", "bvoh", "soluvel", "soluble", "suporte soluvel", "support"],
    "hips": ["hips", "hi ps"],
    "pp": ["pp", "polipropileno", "polypropylene"],
    "peek": ["peek", "pei", "ultem", "pps", "psu", "peki"],
    "resina": ["resina", "resin", "standard resin", "abs like", "water washable"],
    "compositos": ["wood", "madeira", "woodfill", "cork", "cortica", "corkfill", "metal fill",
                   "bronzefill", "marble", "marmore", "ceramic", "ceramica", "glow", "gitd",
                   "glow in the dark", "fosforescente", "brilha no escuro"],
}

# Modificadores: acabamento, reforço, formato. Vivem à parte porque combinam com
# qualquer material -- "PETG CF preto" tem de casar por PETG, por CF e por preto.
MODIFICADORES: dict[str, list[str]] = {
    "cf": ["cf", "carbon", "carbono", "fibra de carbono", "carbon fiber", "carbon fibre",
           "kohlefaser"],
    "gf": ["gf", "glass", "fibra de vidro", "glass fiber", "glass fibre", "glasfaser"],
    "mate": ["matte", "mate", "fosco", "matt", "matte finish"],
    "seda": ["silk", "seda", "sedoso", "silky", "shine", "brilhante", "glossy"],
    "acetinado": ["satin", "acetinado", "fibersatin"],
    "gliter": ["glitter", "sparkle", "purpurina", "brilhantes", "twinkling", "starlight"],
    "fosforescente": ["glow", "gitd", "luminous", "fosforescente", "brilha no escuro",
                      "glow in the dark"],
    "alta velocidade": ["high speed", "hs", "rapid", "rapido", "turbo", "hyper", "fast"],
    "alta temperatura": ["ht", "high temp", "alta temperatura", "heat resistant"],
    "reciclado": ["recycled", "reciclado", "refill", "recycling", "eco"],
    "termocromico": ["thermochromic", "termocromico", "muda de cor", "color change",
                     "uv reactive", "uv"],
}

FORMATOS: dict[str, list[str]] = {
    "1.75": ["1.75", "1,75", "175mm", "1.75mm", "1 75"],
    "2.85": ["2.85", "2,85", "285mm", "2.85mm", "3.00", "3mm", "3 mm"],
    "250g": ["250g", "250 g", "0.25kg"],
    "500g": ["500g", "500 g", "0.5kg", "0,5kg", "meio quilo"],
    "750g": ["750g", "750 g", "0.75kg"],
    "1kg": ["1kg", "1 kg", "1000g", "1000 g", "um quilo", "quilo"],
    "2kg": ["2kg", "2 kg", "2000g"],
    "3kg": ["3kg", "3 kg", "3000g"],
    "5kg": ["5kg", "5 kg", "5000g"],
    "refil": ["refill", "refil", "sem bobine", "spoolless", "sem carretel", "masterspool"],
}

ESTADOS: dict[str, list[str]] = {
    "selado": ["selado", "sealed", "fechado", "novo", "por abrir", "vacuo", "selada"],
    "aberto": ["aberto", "open", "opened", "em uso", "a usar", "usado", "aberta"],
    "vazio": ["vazio", "empty", "acabado", "gasto", "fim", "vazia"],
    "arquivado": ["arquivado", "archived", "guardado", "fora de uso"],
}

GRUPOS: dict[str, dict[str, list[str]]] = {
    "cor": CORES,
    "marca": MARCAS,
    "material": MATERIAIS,
    "modificador": MODIFICADORES,
    "formato": FORMATOS,
    "estado": ESTADOS,
}


def norm(s: str) -> str:
    """Minúsculas, sem acentos, pontuação reduzida a espaço -- exceto + . , que
    distinguem PLA+ de PLA e 1.75 de 175."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace(",", ".")
    s = re.sub(r"[^a-z0-9+.\s-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def build_index() -> dict:
    """Alias normalizado -> lista de {grupo, canonico}. Um alias pode cair em mais
    do que um grupo ("azure" = marca AzureFilm e cor azul) e é isso que se quer."""
    idx: dict[str, list[dict]] = {}
    for grupo, tabela in GRUPOS.items():
        for canonico, aliases in tabela.items():
            for alias in [canonico, *aliases]:
                key = norm(alias)
                if not key:
                    continue
                entry = {"g": grupo, "c": canonico}
                bucket = idx.setdefault(key, [])
                if entry not in bucket:
                    bucket.append(entry)
    return idx


def expand(termo: str) -> set[str]:
    """Todos os aliases equivalentes a um termo, ele próprio incluído."""
    key = norm(termo)
    out = {key}
    for hit in build_index().get(key, []):
        tabela = GRUPOS[hit["g"]]
        out.add(norm(hit["c"]))
        out.update(norm(a) for a in tabela[hit["c"]])
    return {o for o in out if o}


def payload() -> dict:
    """O que vai para o browser em /api/lexicon."""
    return {
        "grupos": {g: {c: [norm(a) for a in [c, *al]] for c, al in t.items()}
                   for g, t in GRUPOS.items()},
        "index": build_index(),
    }


if __name__ == "__main__":
    import json
    p = payload()
    print(f"{len(p['index'])} aliases em {sum(len(t) for t in p['grupos'].values())} termos canónicos")
    for teste in ["azure", "black", "preto", "asa", "cf", "1kg"]:
        print(f"  {teste!r:12} -> {sorted(expand(teste))[:8]}")
