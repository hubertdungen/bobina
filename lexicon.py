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
               "natural white", "snow", "neve", "polar", "traffic white", "arctic",
               "glacier white", "blanco glaciar", "glaciar", "glacier", "hueso"],
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
    # "hyper" sozinho saiu: há "PETG Hyper Speed" de meia dúzia de marcas
    "creality": ["creality", "creality hyper", "ender filament", "cr pla"],
    "anycubic": ["anycubic"],
    "extrudr": ["extrudr", "greentec", "greentec pro", "xpetg", "durapro"],
    "fillamentum": ["fillamentum", "extrafill", "timberfill", "vinyl"],
    "3djake": ["3djake", "3d jake", "jake", "nicefilaments"],
    "eryone": ["eryone"],
    "overture": ["overture"],
    "devildesign": ["devil", "devil design", "devildesign"],
    "fiberlogy": ["fiberlogy", "fiberflex", "fibersilk", "fibersatin", "easy pla", "easy petg"],
    "fiberthree": ["fiberthree", "f3", "fiber three"],
    "colorfabb": ["colorfabb", "ngen", "woodfill", "corkfill", "bronzefill"],
    "formfutura": ["formfutura", "easyfil", "hdglass", "titanx", "atlas", "python flex"],
    "filamentpm": ["filament pm", "filamentpm", "plastspol"],
    # "refill" saiu daqui: é palavra genérica de catálogo (bobine sem carretel),
    # e estava a fazer passar por Rosa3D todos os "PLA Silk (Refill) ... Azurefilm"
    "rosa3d": ["rosa3d", "rosa 3d"],
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
    "realfilament": ["real filament", "realfilament"],
    "francofil": ["francofil"],
    "filaticum": ["filaticum"],
    "gembird": ["gembird"],
    "dasfilament": ["das filament", "dasfilament"],
    "filamentworld": ["filamentworld", "filament world"],
    "repraptpt": ["reprap pt", "reprap", "repraptpt"],
    "3dfilament": ["3d filament"],
    "professionallab": ["professional lab", "prof. lab", "prof lab", "professionallab"],
    "lotactree": ["lotactree", "lotactre"],
    "thefilament": ["the filament", "thefilament"],
    "3dpower": ["3dpower", "3d power"],
    "letsprint": ["let s print", "lets print", "let's print", "letsprint"],
    "smartprint": ["smart print", "smartprint"],
    "3dfils": ["3dfils", "3d fils", "esfil"],
    "oqonos": ["oqonos"],
    "sakata3d": ["sakata", "sakata3d", "sakata 3d"],
    "leon3d": ["leon3d", "leon 3d"],
    "bq": ["bq filament", "witbox"],
    "filanora": ["filanora"],
    "3dfilaprint": ["3dfilaprint"],
    "yousu": ["yousu"],
    "tianse": ["tianse"],
    "creamy": ["creamy 3d", "creamy3d"],
    "gst3d": ["gst3d", "gst 3d"],
    "arianeplast": ["arianeplast", "ariane plast"],
    "neofil3d": ["neofil3d", "neofil 3d"],
    "fiberforce": ["fiberforce", "fiber force"],
    "evolt": ["evolt"],
    "corexy": ["corexy", "core xy"],
}


# ---------------------------------------------------------- nomes das marcas --
# As chaves de MARCAS são minúsculas e sem espaços porque é assim que se compara.
# Para MOSTRAR não servem: ninguém escreve "azurefilm" nem "bambulab". Esta tabela
# é a forma como cada marca escreve o seu próprio nome.
MARCAS_NOME: dict[str, str] = {
    "azurefilm": "AzureFilm", "esun": "eSUN", "sunlu": "SUNLU",
    "polymaker": "Polymaker", "prusa": "Prusament", "bambulab": "Bambu Lab",
    "spectrum": "Spectrum", "elegoo": "ELEGOO", "qidi": "QIDI",
    "creality": "Creality", "anycubic": "Anycubic", "extrudr": "Extrudr",
    "fillamentum": "Fillamentum", "3djake": "3DJAKE", "eryone": "Eryone",
    "overture": "Overture", "devildesign": "Devil Design", "fiberlogy": "Fiberlogy",
    "fiberthree": "Fiberthree", "colorfabb": "colorFabb", "formfutura": "FormFutura",
    "filamentpm": "Filament PM", "rosa3d": "Rosa3D", "printme": "Print-Me",
    "nobufil": "Nobufil", "addnorth": "Add:North", "verbatim": "Verbatim",
    "kimya": "Kimya", "recreus": "Recreus", "smartfil": "Smartfil",
    "filoalfa": "FiloAlfa", "treed": "TreeD", "kexcelled": "Kexcelled",
    "geeetech": "Geeetech", "amolen": "AMOLEN", "hatchbox": "HATCHBOX",
    "flashforge": "FlashForge", "kingroon": "Kingroon", "tinmorry": "TINMORRY",
    "jayo": "JAYO", "ziro": "ZIRO", "torwell": "Torwell", "iemai": "IEMAI",
    "ultimaker": "UltiMaker", "raise3d": "Raise3D", "ninjatek": "NinjaTek",
    "matterhackers": "MatterHackers", "protopasta": "Proto-pasta",
    "sainsmart": "SainSmart", "winkle": "Winkle", "herz": "Herz",
    "noctuo": "Noctuo", "realfilament": "Real Filament", "francofil": "Francofil",
    "filaticum": "Filaticum", "gembird": "Gembird", "dasfilament": "Das Filament",
    "filamentworld": "FilamentWorld", "evolt": "Evolt", "corexy": "Core XY",
    "repraptpt": "RepRap PT", "3dfilament": "3D Filament",
    "professionallab": "Professional Lab", "lotactree": "Lotactree",
    "thefilament": "The Filament", "3dpower": "3DPower", "letsprint": "Let's Print",
    "smartprint": "Smart Print", "3dfils": "3DFILS", "oqonos": "OQONOS",
    "sakata3d": "Sakata3D", "leon3d": "Leon3D", "bq": "BQ", "filanora": "Filanora",
    "3dfilaprint": "3DFilaPrint", "yousu": "YOUSU", "tianse": "TIANSE",
    "creamy": "Creamy 3D", "gst3d": "GST3D", "arianeplast": "ArianePlast",
    "neofil3d": "Neofil3D", "fiberforce": "Fiberforce",
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


# ---------------------------------------------------------------- cores em hex --
# Para desenhar a bobine com a cor certa quando não há foto da loja. As chaves são
# nomes como aparecem mesmo nos catálogos de filamento (a maioria em inglês, que é
# como as lojas escrevem, mais os equivalentes portugueses). Os compostos ("wood
# ash", "ocean blue") vêm aqui inteiros porque valem mais do que a média das
# partes; o resto resolve-se por mistura e por modificadores.
CORES_HEX: dict[str, str] = {
    # neutros
    "preto": "#141414", "black": "#141414", "negro": "#141414",
    "jet black": "#0d0d0d", "deep black": "#101010", "traffic black": "#1a1a1a",
    "galaxy black": "#17161c", "carbon black": "#1c1c1e", "obsidian": "#14161a",
    "onyx": "#151517", "midnight": "#12172a", "charcoal": "#36393d",
    "branco": "#f4f5f7", "white": "#f4f5f7", "cotton white": "#f7f6f2",
    "pure white": "#fbfbfb", "natural white": "#f2efe6", "traffic white": "#f1f2f4",
    "polar white": "#f6f8fa", "snow": "#fafcfd", "neve": "#fafcfd",
    # a Core XY vende a Winkle com os nomes espanhóis do fabricante
    "glacier white": "#eef4f7", "blanco glaciar": "#eef4f7", "glaciar": "#eef4f7",
    "glacier": "#eef4f7", "blanco": "#f4f5f7", "hueso": "#e5e0d4",
    "cinzento": "#7b828c", "grey": "#7b828c", "gray": "#7b828c", "cinza": "#7b828c",
    "gris": "#7b828c", "gris claro": "#b6bcc4", "gris oscuro": "#4a4f57",
    "light grey": "#b6bcc4", "dark grey": "#4a4f57", "ash grey": "#9aa0a6",
    "anthracite": "#3a3f45", "antracite": "#3a3f45", "graphite": "#43474d",
    "grafite": "#43474d", "slate": "#5b6672", "nardo grey": "#6f7377",
    "gunmetal": "#4b5158", "steel": "#8a9198", "aco": "#8a9198",
    "concrete": "#9b9a95", "cimento": "#9b9a95", "titanium": "#8e9195",
    # metálicos
    "prateado": "#c9ccd1", "silver": "#c9ccd1", "prata": "#c9ccd1", "plateado": "#c9ccd1",
    "chrome": "#d7dbe0", "aluminium": "#c2c7cc", "platinum": "#d5d7d8",
    "dourado": "#d4af37", "gold": "#d4af37", "ouro": "#d4af37", "dorado": "#d4af37",
    "champagne": "#e3d5a8", "brass": "#b5952f", "latao": "#b5952f",
    "bronze": "#8c6239", "copper": "#b45f2b", "cobre": "#b45f2b",
    "rose gold": "#d9a08a", "ouro rosa": "#d9a08a",
    # azuis
    "azul": "#2563eb", "blue": "#2563eb",
    "light blue": "#7cb6f2", "dark blue": "#16357a", "azul escuro": "#16357a",
    "navy": "#12224f", "azul marinho": "#12224f", "marine": "#123a63",
    "cobalt": "#1b4bb5", "cobalto": "#1b4bb5", "royal blue": "#2b4bc7",
    "sky blue": "#87c5ec", "sky": "#87c5ec", "celeste": "#9fd3f0",
    "ocean blue": "#12628f", "azure": "#4c9fe0", "azzurro": "#4c9fe0",
    "ultramarine": "#2a3fa8", "sapphire": "#183a8c", "safira": "#183a8c",
    "denim": "#4a6fa0", "petrol": "#11525c", "petroleo": "#11525c",
    "indigo": "#3b3a8f", "ice blue": "#cfe4ef", "gelo": "#cfe4ef",
    "pastel blue": "#a8c8ea", "arctic blue": "#b9d9e6",
    # turquesas / verdes-água
    "turquesa": "#14b8a6", "turquoise": "#14b8a6", "teal": "#0f8f86",
    "cyan": "#22c3d6", "ciano": "#22c3d6", "aqua": "#4fd1c5",
    "aquamarine": "#6fd6c0", "agua marinha": "#6fd6c0", "peacock": "#0d7a83",
    "mint": "#8fdcb5", "menta": "#8fdcb5", "pastel mint": "#b6e7cd",
    "verde agua": "#69c6b0",
    # verdes
    "verde": "#16a34a", "green": "#16a34a",
    "light green": "#7fd08a", "dark green": "#0d5c2c", "verde escuro": "#0d5c2c",
    "olive": "#6b7a2f", "oliva": "#6b7a2f", "lime": "#9fd525", "lima": "#9fd525",
    "forest": "#14532d", "floresta": "#14532d", "emerald": "#0f9d63",
    "esmeralda": "#0f9d63", "sage": "#9aab8a", "salvia": "#9aab8a",
    "pistachio": "#b3cf87", "pistacho": "#b3cf87", "army green": "#4b5320",
    "military": "#4b5320", "militar": "#4b5320", "apple green": "#7ac142",
    "grass": "#3f9b35", "relva": "#3f9b35", "traffic green": "#1a7a3c",
    "neon green": "#4dff4d", "verde neon": "#4dff4d", "pastel green": "#bfe6bf",
    # amarelos / laranjas
    "amarelo": "#eab308", "yellow": "#eab308", "amarillo": "#eab308",
    "lemon": "#f2e14c", "limao": "#f2e14c", "mustard": "#c9971f",
    "mostarda": "#c9971f", "sunflower": "#f4c025", "girassol": "#f4c025",
    "banana": "#f0dd85", "canary": "#f7e04a", "traffic yellow": "#f3c000",
    "neon yellow": "#eaff2b", "pastel yellow": "#f6ecab",
    "laranja": "#f97316", "orange": "#f97316", "naranja": "#f97316", "tangerine": "#f2812f",
    "tangerina": "#f2812f", "amber": "#e8a33d", "ambar": "#e8a33d",
    "apricot": "#f2b183", "alperce": "#f2b183", "peach": "#f7b9a0",
    "pessego": "#f7b9a0", "pumpkin": "#e4762a", "abobora": "#e4762a",
    "traffic orange": "#e2610f", "neon orange": "#ff6a13", "rust": "#9c4a1a",
    "ferrugem": "#9c4a1a",
    # vermelhos / rosas
    "vermelho": "#dc2626", "red": "#dc2626", "rojo": "#dc2626",
    "dark red": "#7f1414", "vermelho escuro": "#7f1414", "crimson": "#b81c37",
    "carmim": "#b81c37", "scarlet": "#e02a1c", "escarlate": "#e02a1c",
    "ruby": "#9b1b33", "rubi": "#9b1b33", "cherry": "#b3202f", "cereja": "#b3202f",
    "blood red": "#7a1015", "traffic red": "#c8102e", "fire engine red": "#d21f28",
    "wine": "#6d1a2e", "vinho": "#6d1a2e", "burgundy": "#5c1a2b",
    "bordeaux": "#5c1a2b", "bordo": "#5c1a2b", "brick": "#9c4a3c",
    "tijolo": "#9c4a3c", "coral": "#f27059", "salmon": "#f2947a",
    "salmao": "#f2947a", "terracotta": "#b5573a", "terracota": "#b5573a",
    "rosa": "#ec4899", "pink": "#ec4899", "hot pink": "#f7318f",
    "rosa choque": "#f7318f", "fuchsia": "#d926a9", "fucsia": "#d926a9",
    "magenta": "#c026a3", "pastel pink": "#f7c2d5", "rosa pastel": "#f7c2d5",
    "blush": "#eebcbc", "bubblegum": "#f79fc4", "flamingo": "#f18aa0",
    # roxos
    "roxo": "#8b5cf6", "purple": "#8b5cf6", "morado": "#8b5cf6", "violet": "#8757e0",
    "violeta": "#8757e0", "lilac": "#c3a8ea", "lilas": "#c3a8ea",
    "lavender": "#c4b5e8", "lavanda": "#c4b5e8", "plum": "#6b2f5e",
    "ameixa": "#6b2f5e", "grape": "#5b2a8a", "uva": "#5b2a8a",
    "aubergine": "#4a2340", "beringela": "#4a2340", "mauve": "#a67fa6",
    "amethyst": "#8b62c4", "ametista": "#8b62c4",
    # castanhos / madeiras / areias
    "castanho": "#6b4423", "brown": "#6b4423", "marrom": "#6b4423", "marron": "#6b4423",
    "chocolate": "#4b2f21", "coffee": "#4a3427", "cafe": "#4a3427",
    "caramel": "#a9722e", "caramelo": "#a9722e", "tan": "#c2996b",
    "mahogany": "#5b2f26", "mogno": "#5b2f26", "leather": "#8a5a35",
    "cabedal": "#8a5a35", "walnut": "#5d4033", "nogueira": "#5d4033",
    "oak": "#b08b56", "carvalho": "#b08b56", "cork": "#c19a6b",
    "cortica": "#c19a6b", "bamboo": "#c9a86a",
    # os "wood" são uma família por si, e puxam todos para o claro
    "wood": "#b1885a", "madeira": "#b1885a",
    "wood light": "#cdab7d", "light wood": "#cdab7d", "madeira clara": "#cdab7d",
    "wood dark": "#7a5636", "dark wood": "#7a5636", "madeira escura": "#7a5636",
    "wood ash": "#c4b39a", "ash wood": "#c4b39a", "ash": "#c4b39a",
    "birch": "#dcc39b", "pine": "#c9a978", "ebony wood": "#3b2f2a",
    # bege / areia / marfim
    "bege": "#d9c9a8", "beige": "#d9c9a8",
    "sand": "#dcc9a0", "areia": "#dcc9a0", "desert sand": "#e0c9a6",
    "cream": "#f0e6d2", "creme": "#f0e6d2", "ivory": "#f2ecdc",
    "marfim": "#f2ecdc", "vanilla": "#f2e8c9", "baunilha": "#f2e8c9",
    "almond": "#e6d2b5", "amendoa": "#e6d2b5", "linen": "#e8e0d0",
    "linho": "#e8e0d0", "wheat": "#e2cd9a", "trigo": "#e2cd9a",
    "khaki": "#b0a06a", "caqui": "#b0a06a", "nude": "#e0c2ab",
    "bone": "#e5e0d4", "osso": "#e5e0d4", "stone": "#b8b0a4",
    "pedra": "#b8b0a4", "clay": "#b07d63", "barro": "#b07d63",
    # especiais
    "transparente": "#dfe7ee", "transparent": "#dfe7ee", "clear": "#dfe7ee",
    "natural": "#e8e4da", "cristal": "#e2edf3", "crystal": "#e2edf3",
    "glass": "#dce9ef", "vidro": "#dce9ef",
    "glow": "#c7f5b8", "fosforescente": "#c7f5b8", "glow in the dark": "#c7f5b8",
    "rainbow": "#8b5cf6", "arco iris": "#8b5cf6", "multicolor": "#8b5cf6",
    "galaxy": "#2a2350", "galaxia": "#2a2350", "marble": "#dcd8d2",
    "marmore": "#dcd8d2", "pearl": "#eae6e0", "perola": "#eae6e0",
    "granite": "#8d8b88", "granito": "#8d8b88",
}

# Palavras que não são cor mas mexem com ela. O valor é o que fazem: escurecer,
# clarear, dessaturar, saturar. Aplicam-se depois de a cor base estar escolhida.
MODIF_COR: dict[str, str] = {
    "dark": "escurecer", "escuro": "escurecer", "escura": "escurecer",
    "deep": "escurecer", "night": "escurecer", "midnight": "escurecer",
    "light": "clarear", "claro": "clarear", "clara": "clarear",
    "pale": "clarear", "palido": "clarear", "soft": "clarear",
    "pastel": "pastel", "baby": "pastel", "bebe": "pastel", "powder": "pastel",
    "suave": "pastel", "leve": "clarear",
    "neon": "saturar", "fluo": "saturar", "fluor": "saturar",
    "fluorescent": "saturar", "bright": "saturar", "vivid": "saturar",
    "intense": "saturar", "vibrant": "saturar",
    "matte": "dessaturar", "mate": "dessaturar", "fosco": "dessaturar",
    "silk": "brilho", "seda": "brilho", "silky": "brilho", "shine": "brilho",
    "satin": "brilho", "acetinado": "brilho", "metallic": "brilho",
    "metalico": "brilho", "pearl": "brilho", "sparkle": "brilho",
    "glitter": "brilho", "twinkling": "brilho",
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
        "hex": {norm(k): v for k, v in CORES_HEX.items()},
        "marcas_nome": MARCAS_NOME,
        "modif": {norm(k): v for k, v in MODIF_COR.items()},
    }


if __name__ == "__main__":
    import json
    p = payload()
    print(f"{len(p['index'])} aliases em {sum(len(t) for t in p['grupos'].values())} termos canónicos")
    for teste in ["azure", "black", "preto", "asa", "cf", "1kg"]:
        print(f"  {teste!r:12} -> {sorted(expand(teste))[:8]}")
