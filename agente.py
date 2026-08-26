#!/usr/bin/env python3
"""Agente de arrumação do Bobina.

Propõe nomes para os espaços e onde arrumar cada bobine, olhando para o que
existe e para o espaço disponível. Devolve sempre um PLANO em JSON -- nunca
escreve na base de dados. Quem aplica é o server.py, e só depois de o plano ter
sido visto (Preview -> Apply), guardando a reversão para se poder anular.

A chamada à API da Anthropic vai em urllib à mão, e não pelo SDK oficial, pela
mesma razão que no Rumo: estas apps correm com o python3 do sistema, arrancadas
pelo cron, sem virtualenv e sem dependências instaladas. Manter isso vale mais
aqui do que a comodidade do SDK.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_TOKENS = 16000

# O Claude é a omissão, mas o agente não fica preso a ele: quem tiver chave da
# OpenAI, do Gemini ou do DeepSeek escolhe em Definições e usa a que quiser.
MODELOS = {
    "anthropic": os.environ.get("BOBINA_ANTHROPIC_MODEL", "claude-opus-5"),
    "openai": os.environ.get("BOBINA_OPENAI_MODEL", "gpt-4o"),
    "gemini": os.environ.get("BOBINA_GEMINI_MODEL", "gemini-2.0-flash"),
    "deepseek": os.environ.get("BOBINA_DEEPSEEK_MODEL", "deepseek-chat"),
}
FORNECEDORES = {
    "anthropic": {"nome": "Claude (Anthropic)", "chave": "anthropic_api_key"},
    "openai": {"nome": "GPT (OpenAI)", "chave": "openai_api_key"},
    "gemini": {"nome": "Gemini (Google)", "chave": "gemini_api_key"},
    "deepseek": {"nome": "DeepSeek", "chave": "deepseek_api_key"},
}
PADRAO = "anthropic"
MODELO = MODELOS["anthropic"]

SISTEMA = """És o organizador de um inventário de filamento para impressão 3D, em Portugal.
Falas português de Portugal.

Recebes o inventário (locais de arrumação e bobines) e devolves UM plano de
arrumação. Regras:

- Agrupa por critérios úteis a quem imprime: material junto (o ASA e o ABS
  cheiram e convém estarem juntos e arejados), higroscópicos (PETG, TPU, Nylon,
  PVA) em caixa seca, e o que se usa mais à mão da impressora.
- Respeita a capacidade de cada local. Nunca ponhas mais bobines num local do
  que a capacidade indicada (capacidade 0 significa desconhecida — nesse caso
  sê conservador e diz-lo num aviso).
- Só propões locais novos se forem mesmo precisos. Nomes curtos, concretos e em
  português ("Caixa seca PETG", "Estante A — prateleira 2"), nada de nomes
  genéricos tipo "Zona 1".
- Cada movimento e cada nome novo leva um "porque" de uma linha, em linguagem
  simples.
- Se algo não der para decidir com o que tens, diz nos avisos em vez de inventar.

Respondes SÓ com um objecto JSON, sem texto à volta e sem cercas de código:

{
  "resumo": "duas ou três frases sobre o que propões e porquê",
  "locais_novos": [{"nome": "...", "tipo": "sala|estante|prateleira|caixa|gaveta|impressora|outro",
                    "pai": "nome de um local existente ou null", "capacidade": 0, "porque": "..."}],
  "locais_renomear": [{"id": 1, "nome_novo": "...", "porque": "..."}],
  "movimentos": [{"bobine_id": 1, "para": "nome do local de destino", "porque": "..."}],
  "avisos": ["..."]
}

O campo "para" tem de ser exactamente o nome de um local existente ou de um dos
locais que propuseste em "locais_novos". Listas vazias quando não há nada a propor."""


def _http_json(url: str, corpo: dict, cabecalhos: dict, etiqueta: str,
               timeout: int = 180) -> tuple[bool, object]:
    pedido = urllib.request.Request(
        url, data=json.dumps(corpo).encode("utf-8"), method="POST",
        headers={**cabecalhos, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")
        try:
            d = json.loads(detalhe)
            detalhe = (d.get("error") or {}).get("message") or d.get("message") or detalhe
        except Exception:  # noqa: BLE001
            pass
        return False, f"Erro {e.code} da API {etiqueta}: {detalhe}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def chama_claude(api_key: str, prompt: str, modelo: str = "") -> tuple[bool, str]:
    """Uma ida à Messages API. Devolve (ok, texto_ou_erro)."""
    corpo = json.dumps({
        "model": modelo or MODELOS["anthropic"],
        "max_tokens": MAX_TOKENS,
        # arrumar um inventário é raciocínio a sério (capacidade, agrupamentos,
        # conflitos), por isso vale a pena o adaptive thinking
        "thinking": {"type": "adaptive"},
        "system": SISTEMA,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    pedido = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=corpo, method="POST",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=180) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")
        try:
            detalhe = json.loads(detalhe).get("error", {}).get("message", detalhe)
        except Exception:  # noqa: BLE001
            pass
        return False, f"Erro {e.code} da API Anthropic: {detalhe}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"

    if dados.get("stop_reason") == "refusal":
        return False, "O modelo recusou o pedido."
    texto = "".join(b.get("text", "") for b in dados.get("content", [])
                    if b.get("type") == "text")
    if not texto.strip():
        return False, "A API respondeu sem texto."
    return True, texto


def chama_openai(api_key: str, prompt: str, modelo: str = "") -> tuple[bool, str]:
    ok, d = _http_json(
        "https://api.openai.com/v1/chat/completions",
        {"model": modelo or MODELOS["openai"],
         "messages": [{"role": "system", "content": SISTEMA},
                      {"role": "user", "content": prompt}]},
        {"Authorization": f"Bearer {api_key}"}, "OpenAI")
    if not ok:
        return False, str(d)
    try:
        return True, d["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return False, "A API OpenAI respondeu sem texto."


def chama_gemini(api_key: str, prompt: str, modelo: str = "") -> tuple[bool, str]:
    m = modelo or MODELOS["gemini"]
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
           f"?key={urllib.parse.quote(api_key)}")
    ok, d = _http_json(url, {
        "systemInstruction": {"parts": [{"text": SISTEMA}]},
        "contents": [{"parts": [{"text": prompt}]}],
    }, {}, "Gemini")
    if not ok:
        return False, str(d)
    try:
        return True, d["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return False, "A API Gemini respondeu sem texto."


def chama_deepseek(api_key: str, prompt: str, modelo: str = "") -> tuple[bool, str]:
    ok, d = _http_json(
        "https://api.deepseek.com/chat/completions",
        {"model": modelo or MODELOS["deepseek"],
         "messages": [{"role": "system", "content": SISTEMA},
                      {"role": "user", "content": prompt}]},
        {"Authorization": f"Bearer {api_key}"}, "DeepSeek")
    if not ok:
        return False, str(d)
    try:
        return True, d["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return False, "A API DeepSeek respondeu sem texto."


CHAMADAS = {
    "anthropic": chama_claude,
    "openai": chama_openai,
    "gemini": chama_gemini,
    "deepseek": chama_deepseek,
}


def extrai_json(texto: str) -> dict | None:
    """O modelo é instruído a responder só JSON, mas às vezes embrulha em ```json.
    Tolera-se as duas formas em vez de falhar por causa de três backticks."""
    texto = texto.strip()
    cerca = re.search(r"```(?:json)?\s*(.+?)```", texto, re.S)
    if cerca:
        texto = cerca.group(1).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    i, j = texto.find("{"), texto.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(texto[i:j + 1])
        except json.JSONDecodeError:
            return None
    return None


def descreve_inventario(locais: list[dict], filamentos: list[dict],
                        bobines: list[dict]) -> str:
    """O inventário em texto compacto. Só o que serve para decidir arrumação —
    preços e URLs ficam de fora para não gastar contexto à toa."""
    por_id = {f["id"]: f for f in filamentos}
    ocupacao: dict[int, int] = {}
    for b in bobines:
        if b.get("local_id"):
            ocupacao[b["local_id"]] = ocupacao.get(b["local_id"], 0) + 1

    linhas = ["LOCAIS (id | nome | tipo | dentro de | capacidade | bobines lá agora)"]
    nomes = {l["id"]: l["nome"] for l in locais}
    for l in locais:
        pai = nomes.get(l.get("pai_id")) or "—"
        cap = l.get("capacidade") or 0
        linhas.append(f"  {l['id']} | {l['nome']} | {l.get('tipo') or '?'} | {pai} | "
                      f"{cap or 'desconhecida'} | {ocupacao.get(l['id'], 0)}")

    linhas.append("")
    linhas.append("BOBINES (id | marca material cor | estado | restante | onde está)")
    for b in bobines:
        f = por_id.get(b["filamento_id"], {})
        nome = " ".join(x for x in [f.get("marca"), f.get("material"), f.get("cor")] if x)
        onde = nomes.get(b.get("local_id")) or "SEM LOCAL"
        rest = b.get("restante_g")
        linhas.append(f"  {b['id']} | {nome or '?'} | {b.get('estado') or '?'} | "
                      f"{round(rest) if rest else 0} g | {onde}")
    if len(bobines) == 0:
        linhas.append("  (nenhuma)")
    return "\n".join(linhas)


def pede_plano(api_key: str, locais: list[dict], filamentos: list[dict],
               bobines: list[dict], instrucoes: str = "",
               modelo: str = "", fornecedor: str = PADRAO) -> tuple[bool, dict | str]:
    prompt = descreve_inventario(locais, filamentos, bobines)
    if instrucoes.strip():
        prompt += f"\n\nPEDIDO DE QUEM ARRUMA:\n{instrucoes.strip()}"
    else:
        prompt += ("\n\nPEDIDO DE QUEM ARRUMA:\nArruma isto da melhor maneira "
                   "com o espaço que existe.")
    chamar = CHAMADAS.get(fornecedor) or chama_claude
    ok, texto = chamar(api_key, prompt, modelo)
    if not ok:
        return False, texto
    plano = extrai_json(texto)
    if plano is None:
        return False, "Não consegui ler o plano que o modelo devolveu."
    # normalizar: melhor uma lista vazia do que um KeyError lá à frente
    for chave in ("locais_novos", "locais_renomear", "movimentos", "avisos"):
        if not isinstance(plano.get(chave), list):
            plano[chave] = []
    plano["resumo"] = str(plano.get("resumo") or "")
    return True, plano
