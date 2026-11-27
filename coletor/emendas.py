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

RE_NUM = re.compile(r"^(?:R[$S]\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})$")
RE_ORG_INICIO = re.compile(r"^(Secretaria|Secr?\.|Funda[cç][aã]o|SAAE|Instituto)", re.I)
RE_ORG_DENTRO = re.compile(r"\s(Secretaria\s+(?:de|da|do)\b.*|Funda[cç][aã]o Cultural.*)$", re.I)
RE_LIXO = re.compile(r"P R A Ç A|PRAÇA DOS TRÊS|C[ÂA]MARA MUNICIPAL DE JACARE|PAL[ÁA]CIO DA LIBERDADE|^\s*Destino\s*$|Valor em Reais|^\s*\d+\s*$", re.I)
ORG_CATEGORIA = [
    ("Saúde", r"sa[uú]de"), ("Educação", r"educa"), ("Esporte", r"esporte"), ("Cultura", r"cultu"),
    ("Assistência social", r"assist"),
    ("Obras e meio ambiente", r"infraestrutura|meio ambiente|obras|mobilidade|urbanismo|servi[cç]os p[uú]blicos|habita"),
]


def categoria(destino: str, orgao: str) -> str:
    for nome, padrao in ORG_CATEGORIA:
        if re.search(padrao, orgao, re.I):
            return nome
    t = destino.lower()
    for nome, padrao in CATEGORIAS:
        if re.search(padrao, t):
            return nome
    return "Outros"


def valor(txt: str) -> float:
    return float(txt.replace(".", "").replace(",", "."))


def _segmentos(linha: str):
    for m in re.finditer(r"\S+(?: \S+)*", linha):
        yield m.start(), m.group(0)


def itens_da_emenda(texto: str) -> list[dict]:
    """Lê as tabelas "Descrição da Atividade | Secretaria de Destino | Valor" pela posição das colunas.

    Descrições e órgãos quebram em várias linhas acima e abaixo do valor; cada fragmento
    é ligado à linha de valor mais próxima dentro da mesma tabela.
    """
    itens = []
    linhas = texto.splitlines()
    dentro, bloco = False, []

    def fecha():
        vals = [(i, v) for i, (_, _, v) in enumerate(bloco) if v]
        if not vals:
            return
        # Uma linha só com o valor que é a soma das anteriores é o total da tabela.
        if len(vals) > 1:
            i_ult, v_ult = vals[-1]
            d_ult, o_ult, _ = bloco[i_ult]
            if not d_ult.strip() and abs(valor(v_ult) - sum(valor(v) for _, v in vals[:-1])) < 0.02:
                vals = vals[:-1]
        grupos = {i: ([], []) for i, _ in vals}
        idx = [i for i, _ in vals]
        conector = re.compile(r"(\b(de|da|do|das|dos|para|a|o|e|em|no|na|com|ao)|[,(\-–])\s*$", re.I)
        ultima_desc = {i: bloco[i][0] for i in idx}
        for i, (desc, org, _) in enumerate(bloco):
            if not desc and not org:
                continue
            if i in grupos:
                alvo = i
            else:
                ant = max((j for j in idx if j < i), default=None)
                prox = min((j for j in idx if j > i), default=None)
                if ant is None:
                    alvo = prox
                elif prox is None:
                    alvo = ant
                elif desc:
                    continua = desc[:1].islower() or desc[:1] in ")-–" or bool(conector.search(ultima_desc[ant] or ""))
                    # sem pista, a linha vai para o valor mais próximo (empate: o seguinte)
                    alvo = ant if continua else (prox if (prox - i) <= (i - ant) else ant)
                else:
                    alvo = prox if (prox - i) <= (i - ant) else ant
            if desc:
                grupos[alvo][0].append(desc)
                ultima_desc[alvo] = desc
            if org and (alvo != i or True):
                grupos[alvo][1].append(org)
        for i, v in vals:
            d = re.sub(r"\s+", " ", " ".join(grupos[i][0])).strip(" -–")
            o = re.sub(r"\s+", " ", " ".join(grupos[i][1])).strip(" -–")
            itens.append({"destino": d[:200], "orgao": o[:80], "valor": valor(v), "categoria": categoria(d, o)})

    for linha in linhas:
        if re.search(r"Descri[cç][aã]o da Atividade", linha, re.I):
            fecha(); bloco = []; dentro = True
            continue
        if not dentro:
            continue
        if re.match(r"\s*Total\b", linha, re.I):
            fecha(); bloco = []; dentro = False
            continue
        if RE_LIXO.search(linha) or re.match(r"\s*Art\.?\s*\d", linha):
            if re.match(r"\s*Art\.?\s*\d", linha):
                fecha(); bloco = []; dentro = False
            continue
        desc, org, val = [], [], None
        for pos, seg in _segmentos(linha):
            if RE_NUM.match(seg):
                val = RE_NUM.match(seg).group(1)
            elif pos >= 60 or RE_ORG_INICIO.match(seg):
                org.append(seg)
            else:
                m = RE_ORG_DENTRO.search(seg)
                if m:
                    desc.append(seg[: m.start()]); org.append(m.group(1))
                else:
                    desc.append(seg)
        bloco.append((" ".join(desc), " ".join(org), val))
    fecha()
    if not itens:
        itens = itens_ocr(texto)
    return [i for i in itens if i["valor"] > 0]


RE_LINHA_OCR = re.compile(r"^(.*?)\s*\|?\s*((?:Secretaria|Funda[cç][aã]o|SAAE)[^|\d]*?)?\s*\|?\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*\|?\s*$", re.I)


def itens_ocr(texto: str) -> list[dict]:
    """Para PDFs escaneados: cada linha termina em valor; linhas seguintes sem valor completam a descrição."""
    itens, dentro, atual = [], False, None
    for linha in texto.splitlines():
        l = linha.strip()
        if re.search(r"seguinte forma", l, re.I):
            dentro = True
            continue
        if not dentro or not l:
            continue
        if re.match(r"(Total|Art\.?\s*\d)", l, re.I):
            dentro = re.match(r"Total", l, re.I) is None and dentro
            if re.match(r"Total", l, re.I):
                dentro = False
            atual = None
            continue
        m = RE_LINHA_OCR.match(l)
        if m and m.group(1):
            atual = {"destino": m.group(1).strip(" |-–"), "orgao": (m.group(2) or "").strip(" |"), "valor": valor(m.group(3))}
            itens.append(atual)
        elif atual and re.fullmatch(r"[\wÀ-ú().,;/º°ª\- ]{12,}", l) and sum(ch.isalpha() for ch in l) > 0.7 * len(l.replace(" ", "")):
            if not RE_LIXO.search(l) and not re.search(r"Secretaria|Funda[cç]", l):
                atual["destino"] = (atual["destino"] + " " + l).strip()[:200]
    for i in itens:
        i["categoria"] = categoria(i["destino"], i["orgao"])
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
