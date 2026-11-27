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
# Cadeiras que mudaram de titular durante a legislatura: (sai, entra).
SUBSTITUICOES = [("hernani-barreto", "rogerio-timoteo")]
RE_LISTA = re.compile(r"seguintes\s+Vereadores\s*:(.*?)(?:\.\s|\n\s*\n)", re.S | re.I)
RE_NOME_ATA = re.compile(r"(\d{1,2})\s*[ªaº]?\s*-?\s*(SO|SE)\b.*?(\d{2})[.-](\d{2})[.-](\d{4})", re.I)
RE_JUSTIFICATIVA = re.compile(r"[^.\n]*(?:n[aã]o se fize(?:ram|ram-se)? presente|n[aã]o se fez presente|ausen[ct]|justificad)[^.\n]*\.", re.I)


def texto_docx(conteudo: bytes) -> str:
    from docx import Document  # python-docx

    doc = Document(io.BytesIO(conteudo))
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)


def presentes_na_ata(texto: str) -> list[str] | None:
    """Lê a lista "compareceram ... os seguintes Vereadores: NOME – PARTIDO; ..." do início da ata."""
    m = RE_LISTA.search(texto)
    if not m:
        return None
    ids = set()
    for parte in re.split(r";|\se\s", m.group(1)):
        ids.update(identificar(re.sub(r"[–-].*", "", parte)))
    return sorted(ids)


def coletar_presencas() -> tuple[dict, dict]:
    print("Coletando atas das sessões...")
    pasta = DADOS / "atas_texto"
    pasta.mkdir(parents=True, exist_ok=True)
    itens = listar_midia(search="Ata", mime_type=MIME_DOCX)
    sessoes, falhas, sem_lista = {}, [], []
    for item in itens:
        nome = Path(item["source_url"]).stem
        m = RE_NOME_ATA.search(nome)
        if not m:  # sessões solenes, audiências públicas etc.
            continue
        numero, tipo, dia, mes, ano = int(m.group(1)), m.group(2).upper(), m.group(3), m.group(4), m.group(5)
        data = f"{ano}-{mes}-{dia}"
        chave = f"{data}-{tipo}{numero:02d}"
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
        presentes = presentes_na_ata(texto)
        if presentes is None:
            sem_lista.append(nome)
            continue
        justificativas = [j.strip() for j in RE_JUSTIFICATIVA.findall(texto) if identificar(j)]
        sessoes[chave] = {
            "tipo": "ordinaria" if tipo == "SO" else "extraordinaria",
            "numero": numero,
            "data": data,
            "url": item["source_url"],
            "presentes": presentes,
            "observacoes": justificativas[:5],
        }

    # Quem ocupava cada cadeira em cada data: o substituto entra a partir da
    # primeira sessão em que aparece presente.
    entrada = {}
    for sai, entra in SUBSTITUICOES:
        datas = [s["data"] for s in sessoes.values() if entra in s["presentes"]]
        entrada[(sai, entra)] = min(datas) if datas else "9999-12-31"
    por_vereador = {vid: {"sessoes": 0, "presencas": 0, "faltas": 0, "datas_faltas": []} for vid in VEREADORES}
    for s in sorted(sessoes.values(), key=lambda x: x["data"]):
        cadeiras = set(VEREADORES)
        for (sai, entra), desde in entrada.items():
            cadeiras.discard(entra if s["data"] < desde else sai)
        s["ausentes"] = sorted(cadeiras - set(s["presentes"]))
        for vid in cadeiras:
            pv = por_vereador[vid]
            pv["sessoes"] += 1
            if vid in s["presentes"]:
                pv["presencas"] += 1
            else:
                pv["faltas"] += 1
                pv["datas_faltas"].append(s["data"])
    for pv in por_vereador.values():
        pv["percentual_presenca"] = round(100 * pv["presencas"] / pv["sessoes"], 1) if pv["sessoes"] else None
    return {"por_vereador": por_vereador, "sessoes": dict(sorted(sessoes.items()))}, {
        "sessoes_lidas": len(sessoes),
        "atas_sem_lista_de_presenca": sem_lista,
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
    try:
        import legislativo as leg

        projetos, meta["projetos"] = leg.coletar_projetos()
        salvar("projetos.json", projetos)
        salvar("projetos_por_vereador.json", leg.painel_por_vereador(projetos))
    except Exception as erro:
        erros.append(f"projetos: {erro}")
    try:
        sessoes = json.loads((DADOS / "presencas.json").read_text(encoding="utf-8"))["sessoes"]
        votacoes = leg.votacoes_das_atas(sessoes)
        boletins, meta["boletins"] = leg.coletar_boletins()
        for v in votacoes:
            b = boletins.get(f"{v['data']}-{v['sessao'].split('-')[-1]}|{v['projeto']}")
            v["votos_nominais"] = b["votos"] if b else {}
            v["boletim"] = b["url"] if b else None
        salvar("votacoes.json", votacoes)
        meta["votacoes"] = {"itens": len(votacoes), "com_boletim": sum(1 for v in votacoes if v["boletim"])}
    except Exception as erro:
        erros.append(f"votacoes: {erro}")
    try:
        import emendas as em

        itens, meta["emendas"] = em.coletar_emendas()
        salvar("emendas.json", {"categorias": [n for n, _ in em.CATEGORIAS] + ["Outros"], "itens": itens, "resumo": em.resumo(itens)})
    except Exception as erro:
        erros.append(f"emendas: {erro}")
    try:
        import pauta as pt

        pauta, meta["pauta"] = pt.coletar_pauta()
        salvar("pauta.json", pauta)
    except Exception as erro:
        erros.append(f"pauta: {erro}")
    meta["erros"] = erros
    salvar("coleta.json", meta)
    print(json.dumps(meta, ensure_ascii=False, indent=1)[:3000])
    return 1 if len(erros) >= 5 else 0


if __name__ == "__main__":
    sys.exit(main())
