"""Coletor de dados públicos da Câmara Municipal de Jacareí (legislatura 2025-2028).

Só faz leituras (GET) no site oficial. Gera arquivos em dados/:
  - trabalhos.json  : indicações, requerimentos, pedidos de informação, moções etc.
                      por vereador e por ano, contados pelos PDFs publicados
  - presencas.json  : presença/ausência por sessão, extraída das atas (.docx)
  - atas_texto/     : texto bruto de cada ata, para conferência
  - coleta.json     : metadados da última execução (data, totais, avisos)
"""
from __future__ import annotations

import html
import io
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.jacarei.sp.leg.br"
API_MEDIA = f"{BASE}/wp-json/wp/v2/media"
INICIO = "2025-01-01T00:00:00"
DADOS = Path(__file__).resolve().parent.parent / "dados"
PAUSA = 0.4  # segundos entre requisições, para não sobrecarregar o site

SESSAO = requests.Session()
SESSAO.headers["User-Agent"] = "transparencia-camara-jacarei-coletor/1.0 (+github)"

# Vereadores da legislatura. "chaves" são formas como o nome aparece
# no fim dos títulos dos arquivos ("ind [2025] 0740 [trabalho] juex") e nas atas.
VEREADORES = {
    "paulinho-do-esporte": {"nome": "Paulinho do Esporte", "chaves": ["paulinho do esporte", "pesporte", "p esporte", "paulinho esporte"]},
    "daniel-mariano": {"nome": "Daniel Mariano", "chaves": ["daniel mariano", "daniel"]},
    "maria-amelia": {"nome": "Maria Amélia", "chaves": ["maria amelia", "amelia", "m amelia"]},
    "jean-araujo": {"nome": "Jean Araújo", "chaves": ["jean araujo", "jean"]},
    "gabriel-belem": {"nome": "Gabriel Belém", "chaves": ["gabriel belem", "gabriel"]},
    "juex-almeida": {"nome": "Juex Almeida", "chaves": ["juex almeida", "juex"]},
    "luis-flavio": {"nome": "Luís Flávio", "chaves": ["luis flavio", "flavinho", "flavio"]},
    "marcelo-dantas": {"nome": "Marcelo Dantas", "chaves": ["marcelo dantas", "marcelo", "m dantas", "dantas"]},
    "netho-alves": {"nome": "Netho Alves", "chaves": ["netho alves", "netho"]},
    "paulinho-dos-condutores": {"nome": "Paulinho dos Condutores", "chaves": ["paulinho dos condutores", "pcondutores", "p condutores", "condutores"]},
    "rogerio-timoteo": {"nome": "Rogério Timóteo", "chaves": ["rogerio timoteo", "rogerio", "timoteo"]},
    "siufarne": {"nome": "Siufarne do Cidade Salvador", "chaves": ["siufarne"]},
    "valmir": {"nome": "Valmir do Parque Meia Lua", "chaves": ["valmir do parque meia lua", "valmir do meia lua", "valmir"]},
    "hernani-barreto": {"nome": "Hernani Barreto", "chaves": ["hernani barreto", "hernani"]},
}

TIPOS = {
    "ind": "indicacoes",
    "req": "requerimentos",
    "ped": "pedidos_de_informacao",
    "moc": "mocoes",
    "mo": "mocoes",
}

RE_TRABALHO = re.compile(r"^\s*([a-z]+)\s*\[(\d{4})\]\s*(\d+)\s*\[trabalho\]\s*(.+?)\s*$", re.I)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9 ]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def identificar(trecho: str) -> list[str]:
    """Devolve os ids de vereador citados num trecho (nome de arquivo ou texto)."""
    t = " " + normalizar(trecho) + " "
    achados = []
    for vid, v in VEREADORES.items():
        for chave in sorted(v["chaves"], key=len, reverse=True):
            if f" {chave} " in t:
                achados.append(vid)
                break
    return achados


def get(url: str, **params) -> requests.Response:
    for tentativa in range(4):
        try:
            r = SESSAO.get(url, params=params, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            time.sleep(PAUSA)
            return r
        except (requests.RequestException, requests.HTTPError) as erro:
            espera = 5 * (tentativa + 1)
            print(f"  falha em {url} ({erro}); nova tentativa em {espera}s", file=sys.stderr)
            time.sleep(espera)
    raise RuntimeError(f"Não foi possível acessar {url}")


def listar_midia(**filtros) -> list[dict]:
    """Percorre todas as páginas da API de mídia do WordPress com os filtros dados."""
    itens, pagina = [], 1
    while True:
        r = get(API_MEDIA, per_page=100, page=pagina, after=INICIO, orderby="date", order="asc",
                _fields="id,date,title,source_url,mime_type", **filtros)
        if r.status_code == 400 and pagina > 1:  # passou da última página
            break
        r.raise_for_status()
        lote = r.json()
        itens.extend(lote)
        total_paginas = int(r.headers.get("X-WP-TotalPages", "1"))
        print(f"  página {pagina}/{total_paginas} ({len(lote)} itens)")
        if pagina >= total_paginas or not lote:
            break
        pagina += 1
    return itens


def coletar_trabalhos() -> tuple[dict, dict]:
    print("Coletando trabalhos (indicações, requerimentos, pedidos, moções)...")
    itens = listar_midia(search="[trabalho]")
    vistos = set()
    contagem: dict = defaultdict(lambda: defaultdict(Counter))
    nao_identificados = Counter()
    tipos_desconhecidos = Counter()
    for item in itens:
        titulo = html.unescape(item["title"]["rendered"])
        m = RE_TRABALHO.match(titulo)
        if not m:
            continue
        prefixo, ano, numero, autores = m.group(1).lower(), m.group(2), int(m.group(3)), m.group(4)
        chave_unica = (prefixo, ano, numero, normalizar(autores))
        if chave_unica in vistos:  # o mesmo trabalho às vezes é publicado duas vezes
            continue
        vistos.add(chave_unica)
        tipo = TIPOS.get(prefixo)
        if tipo is None:
            tipos_desconhecidos[prefixo] += 1
            tipo = f"outros_{prefixo}"
        ids = identificar(autores)
        if not ids:
            nao_identificados[autores] += 1
        for vid in ids:
            contagem[vid][ano][tipo] += 1
    saida = {
        vid: {ano: dict(tipos) for ano, tipos in sorted(anos.items())}
        for vid, anos in sorted(contagem.items())
    }
    avisos = {
        "itens_lidos": len(itens),
        "trabalhos_unicos": len(vistos),
        "autores_nao_identificados": dict(nao_identificados.most_common(50)),
        "prefixos_desconhecidos": dict(tipos_desconhecidos),
    }
    return saida, avisos


MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
RE_AUSENTES = re.compile(r"(ausen[ct]\w*|n[aã]o compareceu|n[aã]o compareceram|faltou|faltaram|justificad\w*|licen[cç]a)", re.I)
RE_PRESENTES = re.compile(r"(presen[ct]\w*|responderam|respondeu)", re.I)


def texto_docx(conteudo: bytes) -> str:
    from docx import Document  # python-docx

    doc = Document(io.BytesIO(conteudo))
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)


def analisar_presenca(texto: str) -> dict:
    """Heurística: procura frases de chamada/presença e de ausência e os nomes nelas.

    O formato das atas pode variar; por isso o texto completo fica salvo em
    dados/atas_texto/ para conferência e ajuste desta função.
    """
    frases = re.split(r"(?<=[.;\n])", texto)
    ausentes, presentes = set(), set()
    for frase in frases:
        ids = identificar(frase)
        if not ids:
            continue
        if RE_AUSENTES.search(frase):
            ausentes.update(ids)
        elif RE_PRESENTES.search(frase):
            presentes.update(ids)
    presentes -= ausentes
    return {"presentes": sorted(presentes), "ausentes": sorted(ausentes)}


RE_ATA = re.compile(r"ata", re.I)


def coletar_presencas() -> tuple[dict, dict]:
    print("Coletando atas das sessões...")
    pasta = DADOS / "atas_texto"
    pasta.mkdir(parents=True, exist_ok=True)
    itens = listar_midia(search="Ata", mime_type=MIME_DOCX)
    sessoes, falhas = {}, []
    for item in itens:
        titulo = html.unescape(item["title"]["rendered"])
        if not RE_ATA.search(titulo) or "solene" in titulo.lower() or "audi" in titulo.lower():
            continue
        nome = Path(item["source_url"]).stem
        destino = pasta / f"{nome}.txt"
        if destino.exists():
            texto = destino.read_text(encoding="utf-8")
        else:
            try:
                r = get(item["source_url"])
                r.raise_for_status()
                texto = texto_docx(r.content)
            except Exception as erro:  # arquivo corrompido ou formato antigo
                falhas.append({"arquivo": item["source_url"], "erro": str(erro)[:200]})
                continue
            destino.write_text(texto, encoding="utf-8")
        sessoes[nome] = {
            "titulo": titulo,
            "data_publicacao": item["date"][:10],
            "url": item["source_url"],
            "resumo": "resumo" in titulo.lower(),
            **analisar_presenca(texto),
        }
    por_vereador = {vid: {"sessoes_com_registro": 0, "ausencias": 0} for vid in VEREADORES}
    for s in sessoes.values():
        for vid in s["presentes"] + s["ausentes"]:
            por_vereador[vid]["sessoes_com_registro"] += 1
        for vid in s["ausentes"]:
            por_vereador[vid]["ausencias"] += 1
    return {"por_vereador": por_vereador, "sessoes": dict(sorted(sessoes.items()))}, {
        "atas_lidas": len(sessoes),
        "falhas": falhas,
    }


def salvar(nome: str, dados) -> None:
    DADOS.mkdir(parents=True, exist_ok=True)
    (DADOS / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    meta = {"executado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fonte": BASE}
    erros = []
    try:
        trabalhos, meta["trabalhos"] = coletar_trabalhos()
        salvar("trabalhos.json", trabalhos)
    except Exception as erro:
        erros.append(f"trabalhos: {erro}")
    try:
        presencas, meta["presencas"] = coletar_presencas()
        salvar("presencas.json", presencas)
    except Exception as erro:
        erros.append(f"presencas: {erro}")
    meta["erros"] = erros
    salvar("coleta.json", meta)
    print(json.dumps(meta, ensure_ascii=False, indent=1)[:3000])
    return 1 if len(erros) == 2 else 0


if __name__ == "__main__":
    sys.exit(main())
