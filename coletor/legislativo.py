"""Projetos, votações (pelas atas) e boletins de votação nominal (PDF escaneado, via OCR)."""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

import coletar as c

TIPOS_PROJETO = ["PLL", "PDL", "PLCL", "PR", "PLE", "PLCE"]
RE_DOC = re.compile(
    r"^\s*(?:(LEI(?: COMPLEMENTAR)?|RESOLU[ÇC][ÃA]O|DECRETO LEGISLATIVO|DL)\s*n?º?\s*([\d.]+)\s*[–-]\s*)?"
    r"(?:(\d{2})_?([\w .]+?)\s*[–-]\s*)?"
    r"(PLL|PDL|PLCL|PLCE|PLE|PR)\s*n?º?\s*(\d{1,3})[./](\d{4})\s*[–-]?\s*"
    r"(?:(\d{2})_([\w .]+?)\s*[–-]\s*)?(.*)$",
    re.I,
)


def _limpa(t: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(t)).strip(" –-")


def coletar_projetos() -> tuple[dict, dict]:
    print("Coletando documentos de projetos...")
    projetos: dict = {}
    ignorados = 0
    for tipo in TIPOS_PROJETO:
        for item in c.listar_midia(search=tipo):
            if not item.get("source_url", "").lower().endswith(".pdf"):
                continue
            titulo = _limpa(item["title"]["rendered"])
            m = RE_DOC.match(titulo)
            if not m or m.group(5).upper() != tipo:
                ignorados += 1
                continue
            norma, norma_num = m.group(1), m.group(2)
            etapa_num = m.group(3) or m.group(8)
            etapa = (m.group(4) or m.group(9) or "").strip()
            numero, ano = int(m.group(6)), int(m.group(7))
            if ano < 2025:
                continue
            resto = [p.strip() for p in re.split(r"\s[–-]\s|\s[–-]|[–-]\s", m.group(10)) if p.strip()]
            parece_autor = len(resto) >= 2 and (len(resto[0].split()) <= 4 or c.identificar(resto[0])
                                                 or re.search(r"mesa|prefeit", resto[0], re.I))
            autor_txt = resto[0] if parece_autor else ""
            assunto = " – ".join(resto[1:] if parece_autor else resto)
            chave = f"{tipo} {numero:03d}/{ano}"
            p = projetos.setdefault(chave, {
                "tipo": tipo, "numero": numero, "ano": ano, "autoria_texto": "", "autores": [],
                "assunto": "", "norma": None, "documentos": [],
            })
            if autor_txt and not p["autoria_texto"]:
                p["autoria_texto"] = autor_txt
            if "mesa" in autor_txt.lower():
                p["autores"] = sorted(set(p["autores"]) | {"mesa-diretora"})
            elif tipo in ("PLE", "PLCE") or "prefeit" in autor_txt.lower():
                p["autores"] = ["prefeito"]
            else:
                p["autores"] = sorted(set(p["autores"]) | set(c.identificar(autor_txt)))
            if len(assunto) > len(p["assunto"]) and not assunto.endswith("…"):
                p["assunto"] = assunto
            elif not p["assunto"]:
                p["assunto"] = assunto
            if norma:
                p["norma"] = f"{norma.title()} {norma_num}"
            p["documentos"].append({"etapa": f"{etapa_num or ''} {etapa}".strip(), "data": item["date"][:10], "url": item["source_url"]})
    for p in projetos.values():
        p["documentos"].sort(key=lambda d: (d["data"], d["etapa"]))
        vistos, docs = set(), []
        for d in p["documentos"]:
            if d["url"] not in vistos:
                vistos.add(d["url"])
                docs.append(d)
        p["documentos"] = docs
    return dict(sorted(projetos.items())), {"projetos": len(projetos), "titulos_fora_do_padrao": ignorados}


NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
           "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13}
RE_ITEM = re.compile(
    r"(Discuss[ãa]o [úu]nica|Primeira discuss[ãa]o|Segunda discuss[ãa]o|Discuss[ãa]o)\s+(?:do|da)\s+"
    r"(PLL|PDL|PLCL|PLCE|PLE|PR|VT|VP)\s*n?[ºo°]?\s*(\d+)\s*/\s*(\d{4})(.*?)(?=\n\s*\d+\.\s|\Z)",
    re.I | re.S,
)


def _num(txt: str) -> int | None:
    txt = c.normalizar(txt)
    if txt.isdigit():
        return int(txt)
    return NUMEROS.get(txt)


def _conta(trecho: str, palavra: str) -> int | None:
    m = re.search(r"(\d+|[a-zçãéê]+)\s*(?:\(\s*[^)]*\))?\s*(?:votos?\s+)?" + palavra, trecho, re.I)
    if m:
        n = _num(m.group(1))
        if n is not None:
            return n
    m = re.search(r"(?:votos?\s+)?" + palavra + r"\w*\s*\(?(\d+)\)?", trecho, re.I)
    return int(m.group(1)) if m else None


def votacoes_das_atas(sessoes: dict) -> list[dict]:
    pasta = c.DADOS / "atas_texto"
    saida = []
    for chave, s in sessoes.items():
        arq = pasta / f"{Path(s['url']).stem}.txt"
        if not arq.exists():
            continue
        texto = arq.read_text(encoding="utf-8")
        for m in RE_ITEM.finditer(texto):
            corpo = re.sub(r"\s+", " ", m.group(5))
            autoria = re.search(r"Autoria:\s*(.*?)\.\s*Assunto:", corpo)
            assunto = re.search(r"Assunto:\s*(.*?)(?:\.\s*(?:Encerrada|Resultado|Retirad|Adiad|Vista)|$)", corpo)
            res = re.search(r"(?:projeto|veto|parecer)\s+(?:foi\s+)?(?:submetido[^,]*,\s*tendo sido\s+)?(APROVAD[OA]|REJEITAD[OA]|MANTIDO|DERRUBADO|RETIRAD[OA]|ADIAD[OA])", corpo, re.I) or re.search(r"\b(APROVAD[OA]|REJEITAD[OA]|RETIRAD[OA]|ADIAD[OA]|VISTA|PREJUDICAD[OA]|MANTIDO|DERRUBADO)\b", corpo, re.I)
            depois = corpo[res.start():] if res else corpo
            saida.append({
                "sessao": chave,
                "data": s["data"],
                "fase": m.group(1),
                "projeto": f"{m.group(2).upper()} {int(m.group(3)):03d}/{m.group(4)}",
                "autoria": autoria.group(1).strip() if autoria else "",
                "assunto": assunto.group(1).strip()[:400] if assunto else "",
                "resultado": res.group(1).lower() if res else "não identificado",
                "favoraveis": _conta(depois, "favor"),
                "contrarios": 0 if re.search(r"sem votos? contr", depois, re.I) else _conta(depois, "contr"),
                "abstencoes": _conta(depois, "absten"),
                "ausencias": _conta(depois, "aus[êe]ncia"),
                "nominal": bool(re.search(r"nominal", depois, re.I)),
            })
    return saida


# ---------------------------------------------------------------- boletins (OCR)
RE_BOLETIM = re.compile(r"(\d{1,2})\s*[ªa]?\s*(SO|SE)\s*[–-]\s*(\d{2})\.(\d{2})\.(\d{4})\s*[–-]\s*Boletim\s+(PLL|PDL|PLCL|PLCE|PLE|PR|VT|VP)\s*n?º?\s*(\d+)[./](\d{4})", re.I)
VOTOS = [("sim", r"\bSIM\b|FAVOR[ÁA]VEL"), ("nao", r"\bN[ÃA]O\b|CONTR[ÁA]RI"), ("abstencao", r"ABST"), ("ausente", r"AUSENTE|N[ÃA]O VOTOU|AUS[ÊE]NCIA"), ("presidente", r"PRESID")]


def ocr_pdf(conteudo: bytes) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "b.pdf"
        pdf.write_bytes(conteudo)
        texto = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        if len(texto.strip()) > 80:
            return texto
        subprocess.run(["pdftoppm", "-r", "300", "-png", str(pdf), str(Path(tmp) / "p")], check=True)
        partes = []
        for img in sorted(Path(tmp).glob("p*.png")):
            partes.append(subprocess.run(["tesseract", str(img), "-", "-l", "por", "--psm", "6"],
                                         capture_output=True, text=True).stdout)
        return "\n".join(partes)


def votos_do_boletim(texto: str) -> dict:
    votos = {}
    for linha in texto.splitlines():
        ids = c.identificar(linha)
        if len(ids) != 1:
            continue
        for rotulo, padrao in VOTOS:
            if re.search(padrao, linha, re.I):
                votos[ids[0]] = rotulo
                break
    return votos


def coletar_boletins() -> tuple[dict, dict]:
    print("Coletando boletins de votação nominal...")
    if not (shutil.which("tesseract") and shutil.which("pdftoppm")):
        return {}, {"aviso": "tesseract/poppler não instalados; boletins ignorados"}
    pasta = c.DADOS / "boletins_texto"
    pasta.mkdir(parents=True, exist_ok=True)
    escolhidos: dict = {}
    for item in c.listar_midia(search="Boletim", mime_type="application/pdf"):
        titulo = _limpa(item["title"]["rendered"])
        m = RE_BOLETIM.search(titulo)
        if not m:
            continue
        chave = f"{m.group(5)}-{m.group(4)}-{m.group(3)}-{m.group(2).upper()}{int(m.group(1)):02d}|{m.group(6).upper()} {int(m.group(7)):03d}/{m.group(8)}"
        # Quando há duas versões, a Câmara republica com sufixo "-1"; fica a mais recente.
        if chave not in escolhidos or item["date"] > escolhidos[chave]["date"]:
            escolhidos[chave] = item
    boletins, falhas = {}, []
    for chave, item in sorted(escolhidos.items()):
        destino = pasta / f"{Path(item['source_url']).stem}.txt"
        if destino.exists():
            texto = destino.read_text(encoding="utf-8")
        else:
            try:
                r = c.get(item["source_url"])
                r.raise_for_status()
                texto = ocr_pdf(r.content)
            except Exception as erro:
                falhas.append({"arquivo": item["source_url"], "erro": str(erro)[:200]})
                continue
            destino.write_text(texto, encoding="utf-8")
        sessao, projeto = chave.split("|")
        boletins[chave] = {"sessao": sessao, "projeto": projeto, "url": item["source_url"], "votos": votos_do_boletim(texto)}
    return boletins, {"boletins": len(boletins), "com_votos_lidos": sum(1 for b in boletins.values() if b["votos"]), "falhas": falhas}


def painel_por_vereador(projetos: dict) -> dict:
    por = defaultdict(list)
    for chave, p in projetos.items():
        for a in p["autores"]:
            por[a].append(chave)
    return {k: sorted(v) for k, v in sorted(por.items())}
