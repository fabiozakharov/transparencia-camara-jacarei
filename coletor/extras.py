"""Dados complementares: audiências públicas, notícias por vereador e licitações da Câmara."""
from __future__ import annotations

import html
import re
from pathlib import Path

import coletar as c

RE_AP = re.compile(r"(\d{1,2})\s*[ªaº]?\s*-?\s*AP\b.*?(\d{2})-(\d{2})-(\d{4})-?(.*)", re.I)


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def coletar_audiencias() -> tuple[list, dict]:
    """Audiências públicas desde 2025: tema, comissão, data e vereadores presentes (lista do início da ata)."""
    print("Coletando audiências públicas...")
    pasta = c.DADOS / "atas_texto"
    pasta.mkdir(parents=True, exist_ok=True)
    saida, falhas = [], []
    for item in c.listar_midia(search="AP", mime_type=c.MIME_DOCX):
        nome = Path(item["source_url"]).stem
        m = RE_AP.search(nome)
        if not m or "Ata" not in nome:
            continue
        destino = pasta / f"{nome}.txt"
        if destino.exists():
            texto = destino.read_text(encoding="utf-8")
        else:
            try:
                r = c.get(item["source_url"])
                r.raise_for_status()
                texto = c.texto_docx(r.content)
            except Exception as erro:
                falhas.append({"arquivo": item["source_url"], "erro": str(erro)[:200]})
                continue
            destino.write_text(texto, encoding="utf-8")
        tema = re.search(r"[“\"](.+?)[”\"]", texto[:1500])
        comissao = re.search(r"\n\s*(Comiss[ãa]o[^\n]{5,120}(?:\n[^\n]{3,80})?)\n", texto[:1500])
        mesa = re.search(r"Mesa Diretora foi composta pel[oa]s? Vereador[ea]s? (.*?)\.\s", texto, re.S)
        saida.append({
            "numero": int(m.group(1)),
            "data": f"{m.group(4)}-{m.group(3)}-{m.group(2)}",
            "tema": (tema.group(1) if tema else m.group(5).replace("-", " ")).strip()[:200],
            "comissao": re.sub(r"\s+", " ", comissao.group(1)).strip() if comissao else "",
            "conduziram": sorted(c.identificar(mesa.group(1))) if mesa else [],
            "url": item["source_url"],
        })
    for a in saida:
        a["presentes"] = sorted(set(a["conduziram"]) | set(c.presentes_na_ata(Path(pasta / (Path(a["url"]).stem + ".txt")).read_text(encoding="utf-8")) or []))
    saida.sort(key=lambda x: x["data"], reverse=True)
    return saida, {"audiencias": len(saida), "falhas": falhas}


# Nas notícias só valem nomes completos ou apelidos inconfundíveis: "Daniel" ou "Gabriel" sozinhos
# aparecem em textos que não tratam do vereador.
CHAVES_NOTICIA = {vid: [v["chaves"][0]] for vid, v in c.VEREADORES.items()}
for vid, extra in {"luis-flavio": ["flavinho"], "netho-alves": ["netho"], "juex-almeida": ["juex"],
                   "siufarne": ["siufarne"], "valmir": ["valmir"], "hernani-barreto": ["hernani"],
                   "rogerio-timoteo": ["timoteo"], "maria-amelia": ["amelia"]}.items():
    CHAVES_NOTICIA[vid] += extra


def citados_na_noticia(texto: str) -> list[str]:
    t = " " + c.normalizar(texto) + " "
    return [vid for vid, chaves in CHAVES_NOTICIA.items() if any(f" {k} " in t for k in chaves)]


def coletar_noticias() -> tuple[list, dict]:
    """Notícias do site da Câmara desde 2025 e os vereadores citados no título ou no texto."""
    print("Coletando notícias...")
    saida, pagina, total = [], 1, 1
    while pagina <= total:
        r = c.get(f"{c.BASE}/wp-json/wp/v2/posts", per_page=100, page=pagina, after="2025-01-01T00:00:00",
                  _fields="date,link,title,content")
        if r.status_code == 400:
            break
        r.raise_for_status()
        total = int(r.headers.get("X-WP-TotalPages", 1))
        for p in r.json():
            titulo = _texto(p["title"]["rendered"])
            corpo = _texto(p["content"]["rendered"])
            no_titulo = citados_na_noticia(titulo)
            citados = citados_na_noticia(corpo)
            saida.append({
                "data": p["date"][:10], "titulo": titulo, "url": p["link"],
                "destaque": sorted(no_titulo), "citados": sorted(set(citados) | set(no_titulo)),
                "resumo": corpo[:260],
            })
        pagina += 1
    return saida, {"noticias": len(saida), "paginas": total}


PAGINAS_LICITACAO = {
    "Pregão": ["/licitacoes/pregoes-cm/", "/licitacoes/pregao/pregoes-2025/"],
    "Concorrência": ["/licitacoes/concorrencia/"],
    "Convite": ["/licitacoes/convite/"],
    "Tomada de preços": ["/licitacoes/tomada-de-preco/"],
    "Dispensa": ["/licitacoes/dispensa/", "/licitacoes/dispensa/dispensas-2025/"],
}
RE_ITEM_LIC = re.compile(r'<a[^>]+href="([^"]*/licitacoes/[^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
RE_NUM_LIC = re.compile(r"n[º°o.]?\s*([\d.]+)\s*/\s*(20\d\d)", re.I)
RE_STATUS = re.compile(r"\((CONCLU[ÍI]D[OA]|EM ANDAMENTO|REVOGAD[OA]|SUSPENS[OA]|DESERT[OA]|FRACASSAD[OA]|ANULAD[OA]|CANCELAD[OA]|ABERT[OA]|HOMOLOGAD[OA])\)", re.I)


def coletar_licitacoes() -> tuple[list, dict]:
    print("Coletando licitações da Câmara...")
    vistos, saida, falhas = set(), [], []
    for modalidade, caminhos in PAGINAS_LICITACAO.items():
        for caminho in caminhos:
            try:
                r = c.get(c.BASE + caminho)
                r.raise_for_status()
            except Exception as erro:
                falhas.append({"pagina": caminho, "erro": str(erro)[:200]})
                continue
            corpo = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
            marcas = [m for m in RE_ITEM_LIC.finditer(corpo) if RE_NUM_LIC.search(_texto(m.group(2)))]
            for i, m in enumerate(marcas):
                titulo = _texto(m.group(2))
                num = RE_NUM_LIC.search(titulo)
                if int(num.group(2)) < 2025 or m.group(1) in vistos:
                    continue
                vistos.add(m.group(1))
                fim = marcas[i + 1].start() if i + 1 < len(marcas) else min(len(corpo), m.end() + 4000)
                resto = _texto(corpo[m.end():fim])
                status = RE_STATUS.search(titulo + " " + resto[:60])
                datas = re.findall(r"\d{2}/\d{2}/20\d\d", resto)
                desc = RE_STATUS.sub("", resto)
                desc = re.split(r"ANOS ANTERIORES|Abertura|Data\b|Plataforma|E-?mail", desc, flags=re.I)[0].strip(" -–:")
                saida.append({
                    "modalidade": modalidade, "titulo": RE_STATUS.sub("", titulo).strip(), "ano": int(num.group(2)),
                    "status": status.group(1).capitalize() if status else "",
                    "objeto": desc[:300], "data": datas[0] if datas else "",
                    "url": m.group(1) if m.group(1).startswith("http") else c.BASE + m.group(1),
                })
    return saida, {"licitacoes": len(saida), "falhas": falhas}
