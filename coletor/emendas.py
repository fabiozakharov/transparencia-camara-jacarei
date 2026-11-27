"""Emendas impositivas dos vereadores: destino, valor e categoria de cada item."""
from __future__ import annotations

import re
from pathlib import Path

import coletar as c
from legislativo import ocr_pdf

# Páginas da Câmara com os PDFs das emendas impositivas desta legislatura.
PAGINAS = {
    "LOA 2026": f"{c.BASE}/trabalhos-gerais/emendas-impositivas-2025/",
    "LOA 2027": f"{c.BASE}/trabalhos-gerais/emendas-impositivas-2026/",
}

# Poucas categorias, de propósito. A ordem importa: a primeira que casar vence.
CATEGORIAS = [
    ("Saúde", r"sa[uú]de|hospital|santa casa|ubs|upa\b|m[eé]dic|cl[ií]nic|exame|resson[aâ]ncia|farm[aá]cia|onco|cepac|caps\b|odonto|ambul[aâ]n"),
    ("Educação", r"educa[cç]|escola|emeb|emei|creche|ensino|alfabetiz|biblioteca"),
    ("Esporte", r"esport|futebol|quadra|campo\b|gin[aá]sio|basquete|v[oô]lei|handebol|rugby|jud[oô]|karat|atl[eé]t|academia|skate|capoeira|nata[cç]"),
    ("Cultura", r"cultur|fun?da[cç][aã]o cultural|teatro|m[uú]sica|banda|coral|[oó]pera|cine|arte\b|artes\b|festival|carnaval|folclor|evento"),
    ("Assistência social", r"assist[eê]ncia|social|lar |lar$|abrigo|idoso|crian[cç]a|apae|defici|vulnerab|mulher|fraterno|caridade|ozanam|provid[eê]ncia|comunidade terap|depend[eê]ncia"),
    ("Obras e meio ambiente", r"obra|pra[cç]a|pavimenta|asfalt|ilumina|poste|led\b|cal[cç]ada|reforma|alambrado|grama|meio ambiente|[aá]rea verde|parque|animal|animais|prote[cç][aã]o animal|ambiental|playground|brinquedo"),
]

RE_VALOR = re.compile(r"R\$\s*([\d.]{1,12},\d{2})")
RE_UNIDADE = re.compile(r"(Secretaria\s+(?:Municipal\s+)?de\s+[A-Za-zÀ-ú ]+?(?=\s{2,}|,|\.|$|\s+R\$|\s+-)|Funda[cç][aã]o\s+Cultural[A-Za-zÀ-ú ]*|SAAE|Instituto de Previd[eê]ncia)", re.I)
RE_TOTAL = re.compile(r"\btotal\b|\bsubtotal\b|\bsoma\b", re.I)


def categoria(texto: str) -> str:
    t = texto.lower()
    for nome, padrao in CATEGORIAS:
        if re.search(padrao, t):
            return nome
    return "Outros"


def valor(txt: str) -> float:
    return float(txt.replace(".", "").replace(",", "."))


def itens_da_emenda(texto: str) -> list[dict]:
    """Cada linha com um valor em R$ é um item; a descrição pode vir em linhas anteriores sem valor."""
    itens, unidade, pendente = [], "", []
    for linha in texto.splitlines():
        bruta = linha.strip()
        if not bruta:
            pendente = []
            continue
        u = RE_UNIDADE.search(bruta)
        valores = RE_VALOR.findall(bruta)
        if u and not valores:
            unidade = re.sub(r"\s+", " ", u.group(1)).strip()
            pendente = []
            continue
        if not valores:
            if len(bruta) < 200:
                pendente = (pendente + [bruta])[-2:]
            continue
        if RE_TOTAL.search(bruta):
            pendente = []
            continue
        desc = RE_VALOR.sub("", bruta).strip()
        u = RE_UNIDADE.search(desc)
        if u:
            unidade = re.sub(r"\s+", " ", u.group(1)).strip()
            desc = desc.replace(u.group(0), "")
        desc = re.sub(r"\s{2,}", " ", " ".join(pendente + [desc])).strip(" |-–:")
        pendente = []
        if len(desc) < 3:
            continue
        v = valor(valores[-1])
        itens.append({"destino": desc[:200], "orgao": unidade, "valor": v, "categoria": categoria(f"{desc} {unidade}")})
    return itens


def coletar_emendas() -> tuple[list[dict], dict]:
    print("Coletando emendas impositivas...")
    pasta = c.DADOS / "emendas_texto"
    pasta.mkdir(parents=True, exist_ok=True)
    saida, avisos = [], {"arquivos": 0, "conferencia": []}
    for exercicio, url in PAGINAS.items():
        r = c.get(url)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        links = re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', r.text, re.I | re.S)
        vistos = set()
        for href, rotulo in links:
            rotulo_txt = re.sub(r"<[^>]+>", " ", rotulo)
            nome = Path(href).stem
            if href in vistos or "manual" in nome.lower() or "PELOML" in nome:
                continue
            vistos.add(href)
            autores = c.identificar(rotulo_txt) or c.identificar(nome.replace("-", " ").replace("_", " "))
            if not autores:
                continue
            destino = pasta / f"{nome}.txt"
            if destino.exists():
                texto = destino.read_text(encoding="utf-8")
            else:
                arq = c.get(href)
                arq.raise_for_status()
                texto = ocr_pdf(arq.content)
                destino.write_text(texto, encoding="utf-8")
            avisos["arquivos"] += 1
            sub = "subemenda" in nome.lower() or "subemenda" in rotulo_txt.lower()
            itens = itens_da_emenda(texto)
            total = round(sum(i["valor"] for i in itens), 2)
            avisos["conferencia"].append({"exercicio": exercicio, "vereador": autores[0], "arquivo": href,
                                          "subemenda": sub, "itens": len(itens), "soma_itens": total})
            for i in itens:
                saida.append({"exercicio": exercicio, "vereador": autores[0], "subemenda": sub, "documento": href, **i})
    return saida, avisos


def resumo(itens: list[dict]) -> dict:
    """Totais por vereador e categoria (só emendas originais; subemendas ficam listadas à parte)."""
    out: dict = {}
    for i in itens:
        if i["subemenda"]:
            continue
        v = out.setdefault(i["exercicio"], {}).setdefault(i["vereador"], {})
        v[i["categoria"]] = round(v.get(i["categoria"], 0) + i["valor"], 2)
    return out
