"""Pauta (Ordem do Dia) da sessão mais recente publicada."""
from __future__ import annotations

import html
import re

import coletar as c

RE_TITULO = re.compile(r"((?:Discuss[ãa]o [úu]nica|Primeira discuss[ãa]o|Segunda discuss[ãa]o)\s+(?:do|da)\s+(PLL|PDL|PLCL|PLCE|PLE|PR|VT|VP)\s*n?[ºo°]?\s*(\d+)\s*/\s*(\d{4}))", re.I)


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def coletar_pauta() -> tuple[dict, dict]:
    print("Coletando a pauta (Ordem do Dia)...")
    lista = c.get(f"{c.BASE}/votacoes/")
    lista.raise_for_status()
    sessoes = re.findall(r'href="([^"]*/ordem-do-dia/[^"]+)"[^>]*>(.*?)</a>', lista.text, re.I | re.S)
    proxima = re.search(r"(\d+ª?\s*SESS[ÃA]O[^<]{0,80}?EM BREVE)", _texto(lista.text), re.I)
    if not sessoes:
        return {}, {"aviso": "nenhuma Ordem do Dia encontrada"}
    url, rotulo = sessoes[-1]
    # A lista costuma vir em ordem cronológica; confere pela data no endereço.
    def data(u):
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", u)
        return f"{m.group(3)}{m.group(2)}{m.group(1)}" if m else ""
    url, rotulo = max(sessoes, key=lambda x: data(x[0]))
    pagina = c.get(url if url.startswith("http") else c.BASE + url)
    pagina.raise_for_status()
    corpo = pagina.text
    marcas = [m for m in RE_TITULO.finditer(corpo)]
    itens = []
    for i, m in enumerate(marcas):
        trecho = corpo[m.start(): marcas[i + 1].start() if i + 1 < len(marcas) else len(corpo)]
        txt = _texto(trecho)
        autoria = re.search(r"Autoria:\s*(.*?)(?:Assunto:|$)", txt)
        assunto = re.search(r"Assunto:\s*(.*?)(?:Projeto\b|Parecer|Relat[óo]rio|Emenda|$)", txt)
        links = [{"rotulo": _texto(r), "url": h} for h, r in re.findall(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>', trecho, re.I | re.S)]
        itens.append({
            "titulo": _texto(m.group(1)),
            "projeto": f"{m.group(2).upper()} {int(m.group(3)):03d}/{m.group(4)}",
            "autoria": (autoria.group(1).strip() if autoria else "")[:200],
            "assunto": (assunto.group(1).strip() if assunto else "")[:400],
            "documentos": links[:8],
        })
    # O mesmo projeto pode aparecer várias vezes (substitutivo, emendas): junta numa linha só.
    unidos = {}
    for it in itens:
        u = unidos.setdefault(it["projeto"], it)
        if u is not it:
            for campo in ("autoria", "assunto"):
                u[campo] = u[campo] or it[campo]
            u["documentos"] = (u["documentos"] + [d for d in it["documentos"] if d not in u["documentos"]])[:12]
    itens = list(unidos.values())
    return {"sessao": _texto(rotulo), "url": url, "data": data(url), "proxima": proxima.group(1) if proxima else None,
            "itens": itens}, {"itens": len(itens)}
