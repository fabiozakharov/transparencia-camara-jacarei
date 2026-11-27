"""Ranking dos vereadores: nota de 0 a 10 a partir dos dados públicos já coletados em dados/.

Metodologia aprovada pelo Fabio (inspirada no Ranking dos Políticos, ranking.org.br, simplificada):

    critério               peso   como vira nota de 0 a 10
    presença               10%    100% = 10; cada ponto percentual abaixo tira 0,5
    fiscalização           20%    requerimentos + pedidos de informação por sessão no cargo; maior = 10
    projetos de lei        20%    apresentado = 1, aprovado = 3, honraria = 0,25, por sessão no cargo; maior = 10
    indicações             10%    por sessão no cargo, com teto: chegar à mediana da Câmara = 10
    economia de gabinete   15%    gasto por sessão no cargo; menor = 10, maior = 0
    votações nominais      10%    % de boletins em que votou SIM ou NÃO (presidente não conta)
    emendas impositivas    15%    média de pontos por real destinado (tabela PONTOS_EMENDA)

Quando um critério não tem dado para um vereador, o peso dele é redistribuído entre os demais.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import date

import coletar as c

PESOS = {
    "presenca": 0.10, "fiscalizacao": 0.20, "projetos": 0.20, "indicacoes": 0.10,
    "gastos": 0.15, "votacoes": 0.10, "emendas": 0.15,
}
ROTULOS = {
    "presenca": "Presença", "fiscalizacao": "Fiscalização", "projetos": "Projetos de lei",
    "indicacoes": "Indicações", "gastos": "Economia de gabinete", "votacoes": "Votações nominais",
    "emendas": "Emendas impositivas",
}
DESCRICOES = {
    "presenca": "100% de presença = 10. Cada ponto percentual abaixo tira 0,5.",
    "fiscalizacao": "Requerimentos e pedidos de informação por sessão no cargo. Quem mais fez = 10.",
    "projetos": "Projeto apresentado = 1, aprovado = 3, honraria = 0,25, por sessão no cargo. Quem mais pontuou = 10.",
    "indicacoes": "Indicações por sessão no cargo, com teto: chegar à mediana da Câmara já vale 10.",
    "gastos": "Gastos de gabinete por sessão no cargo. Quem gastou menos = 10, quem gastou mais = 0.",
    "votacoes": "Parte dos boletins de votação nominal em que votou SIM ou NÃO. Abstenção ou ausência = zero.",
    "emendas": "Média dos pontos por real destinado: saúde, educação e segurança 10; assistência social, obras e meio ambiente 6; cultura 3; entidades esportivas, escolas de samba, festas e destinos sem justificativa −5.",
}

ANOS = ("2025", "2026")
TIPOS_VEREADOR = {"PLL", "PLCL", "PDL", "PR"}
RE_HONRARIA = re.compile(
    r"t[ií]tulo|cidadan|cidad[ãa]o|denomina|medalha|comenda|honra|diploma|homenag|utilidade p[úu]blica|"
    r"dia municipal|institui o dia|data comemorativa|calend[áa]rio|semana municipal", re.I)
MIN_VOTOS_BOLETIM = 12  # boletins com OCR incompleto ficam de fora

# --------------------------------------------------------------- emendas
PONTOS_EMENDA = {
    "Primordial": 10, "Secundária": 6, "Cultura": 3, "Sem relevância ou sem justificativa": -5,
}
RE_NEGATIVO = re.compile(r"samba|g\.?\s?r\.?\s?e\.?\s?s\b|g\.?r\.?c\.?e\.?s|carnaval|festa\b|festa de|show|reggae|eventos?\b|tendas?\b", re.I)
RE_SEGURANCA = re.compile(r"guarda municipal|defesa civil|seguran[çc]a p[úu]blica|videomonitor|c[âa]meras? de seguran", re.I)
RE_ENTIDADE = re.compile(r"associa|clube|club\b|instituto|team\b|equipe|esporte clube|\be\.?\s?c\.?\b|atl[ée]tica|liga\b", re.I)
RE_ESPORTIVA = re.compile(r"esportiv|esporte clube|atl[ée]tic|futebol|futsal|rugby|handebol|basquet|v[ôo]lei|taekwondo|nata[çc][ãa]o|jud[ôo]|capoeira", re.I)
RE_ESTRUTURA = re.compile(r"reforma|manuten[çc][ãa]o da quadra|quadra|academias? ao ar livre|academia ao livre|alambrado|grama|campo (de futebol|society)|pra[çc]a", re.I)
RE_SOCIAL = re.compile(r"autist|ado[çc][ãa]o|ampara menores|\bjam\b|humanit|cestas?|doutores coloridos|apae|idoso|crian|"
                       r"vulnerab|kair[óo]s|guri na ro[çc]a|dedicar|fraternidade|lar\b|rotary|banco de", re.I)
RE_ANIMAL = re.compile(r"vira.?lata|patas|protetoras|apijac|prote[çc][ãa]o animal|animais", re.I)


def faixa_emenda(item: dict) -> str:
    texto = f"{item['destino']} {item['orgao']}"
    cat = item["categoria"]
    if cat in ("Saúde", "Educação"):
        return "Primordial"
    if RE_SEGURANCA.search(texto):
        return "Primordial"
    if RE_NEGATIVO.search(texto):
        return "Sem relevância ou sem justificativa"
    if RE_ESPORTIVA.search(texto) and RE_ENTIDADE.search(texto):
        return "Sem relevância ou sem justificativa"
    if cat == "Esporte":
        # Obra em espaço público (quadra, academia ao ar livre) conta como obra; repasse a entidade esportiva, não.
        if RE_ESTRUTURA.search(item["destino"]) and not RE_ENTIDADE.search(item["destino"]):
            return "Secundária"
        return "Sem relevância ou sem justificativa"
    if cat in ("Assistência social", "Obras e meio ambiente"):
        return "Secundária"
    if RE_SOCIAL.search(texto) or RE_ANIMAL.search(texto):
        return "Secundária"
    if cat == "Cultura":
        return "Cultura"
    return "Sem relevância ou sem justificativa"


def nota_emendas(emendas: dict) -> dict:
    cota = {}
    por = {}
    for i in emendas.get("itens", []):
        if i["subemenda"]:
            continue
        f = faixa_emenda(i)
        d = por.setdefault(i["vereador"], {"valor": 0.0, "pontos": 0.0, "faixas": {}, "itens": []})
        d["valor"] += i["valor"]
        d["pontos"] += i["valor"] * PONTOS_EMENDA[f]
        d["faixas"][f] = round(d["faixas"].get(f, 0) + i["valor"], 2)
        d["itens"].append({"destino": i["destino"], "valor": i["valor"], "faixa": f, "exercicio": i["exercicio"]})
    # cota de referência = maior soma lida por exercício (a cota é igual para todos)
    for i in emendas.get("itens", []):
        if not i["subemenda"]:
            cota[i["exercicio"]] = 0
    for ex in cota:
        somas = {}
        for i in emendas["itens"]:
            if i["exercicio"] == ex and not i["subemenda"]:
                somas[i["vereador"]] = somas.get(i["vereador"], 0) + i["valor"]
        cota[ex] = max(somas.values())
    cota_total = sum(cota.values())
    out = {}
    for vid, d in por.items():
        if d["valor"] <= 0:
            continue
        cobertura = d["valor"] / cota_total if cota_total else 0
        out[vid] = {
            "nota": max(0.0, min(10.0, d["pontos"] / d["valor"])),
            "cobertura": round(100 * cobertura, 1),
            "faixas": d["faixas"],
            "itens": d["itens"],
        }
    return out


# --------------------------------------------------------------- demais critérios
def ler(nome: str, padrao=None):
    arq = c.DADOS / nome
    if not arq.exists():
        return padrao
    return json.loads(arq.read_text(encoding="utf-8"))


def aprovado(chave: str, p: dict, ultimo: dict) -> bool:
    if p.get("norma"):
        return True
    vs = ultimo.get(chave)
    return bool(vs and vs[-1]["resultado"].startswith("aprovad"))


def br(n: float, casas: int = 1) -> str:
    return f"{n:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calcular() -> dict:
    presencas = ler("presencas.json", {"por_vereador": {}, "sessoes": {}})
    trabalhos = ler("trabalhos.json", {})
    projetos = ler("projetos.json", {})
    votacoes = ler("votacoes.json", [])
    emendas = ler("emendas.json", {})
    gastos = ler("gastos_gabinete.json", {})

    ids = list(c.VEREADORES)
    pv = presencas["por_vereador"]
    sessoes = {vid: (pv.get(vid) or {}).get("sessoes", 0) for vid in ids}
    em_exercicio = {k: set(s["presentes"]) | set(s.get("ausentes", [])) for k, s in presencas["sessoes"].items()}

    bruto: dict[str, dict] = {vid: {} for vid in ids}
    detalhe: dict[str, dict] = {vid: {} for vid in ids}

    # presença
    for vid in ids:
        p = pv.get(vid)
        if p and p["sessoes"]:
            bruto[vid]["presenca"] = p["percentual_presenca"]
            detalhe[vid]["presenca"] = f"{p['presencas']} de {p['sessoes']} sessões ({br(p['percentual_presenca'])}%)"

    # fiscalização e indicações
    for vid in ids:
        anos = {a: d for a, d in trabalhos.get(vid, {}).items() if a in ANOS}
        req = sum(d.get("requerimentos", 0) for d in anos.values())
        ped = sum(d.get("pedidos_de_informacao", 0) for d in anos.values())
        ind = sum(d.get("indicacoes", 0) for d in anos.values())
        if sessoes[vid]:
            bruto[vid]["fiscalizacao"] = (req + ped) / sessoes[vid]
            bruto[vid]["indicacoes"] = ind / sessoes[vid]
            detalhe[vid]["fiscalizacao"] = f"{req} requerimentos e {ped} pedidos de informação"
            detalhe[vid]["indicacoes"] = f"{ind} indicações"

    # projetos
    ultimo: dict = {}
    for v in sorted(votacoes, key=lambda x: x["data"]):
        ultimo.setdefault(v["projeto"], []).append(v)
    contagem = {vid: {"apresentados": 0, "aprovados": 0, "honrarias": 0, "pontos": 0.0} for vid in ids}
    for chave, p in projetos.items():
        if p["tipo"] not in TIPOS_VEREADOR:
            continue
        honra = bool(RE_HONRARIA.search(p.get("assunto", "")))
        ok = aprovado(chave, p, ultimo)
        for vid in p["autores"]:
            if vid not in contagem:
                continue
            k = contagem[vid]
            if honra:
                k["honrarias"] += 1
                k["pontos"] += 0.25
            else:
                k["apresentados"] += 1
                k["aprovados"] += int(ok)
                k["pontos"] += 3 if ok else 1
    for vid in ids:
        if sessoes[vid]:
            k = contagem[vid]
            bruto[vid]["projetos"] = k["pontos"] / sessoes[vid]
            detalhe[vid]["projetos"] = f"{k['apresentados']} projetos ({k['aprovados']} aprovados) e {k['honrarias']} honrarias"

    # gastos de gabinete (dados/gastos_gabinete.json: {vid: {ano: total}})
    for vid in ids:
        g = gastos.get("vereadores", {}).get(vid)
        if g and sessoes[vid]:
            total = sum(v for v in g.values() if v)
            bruto[vid]["gastos"] = total / sessoes[vid]
            detalhe[vid]["gastos"] = "R$ " + br(total, 0) + " (" + ", ".join(f"{a}: R$ {br(v, 0)}" for a, v in sorted(g.items()) if v) + ")"

    # votações nominais
    part = {vid: [0, 0] for vid in ids}
    for v in votacoes:
        votos = v.get("votos_nominais") or {}
        if len(votos) < MIN_VOTOS_BOLETIM:
            continue
        chave = v["sessao"]
        cadeiras = em_exercicio.get(chave, set(ids))
        for vid in cadeiras:
            if vid not in part or votos.get(vid) == "presidente":
                continue
            part[vid][1] += 1
            if votos.get(vid) in ("sim", "nao"):
                part[vid][0] += 1
    for vid, (votou, total) in part.items():
        if total:
            bruto[vid]["votacoes"] = votou / total
            detalhe[vid]["votacoes"] = f"votou em {votou} de {total} votações nominais"

    # emendas
    em = nota_emendas(emendas)
    for vid, d in em.items():
        if vid in bruto:
            bruto[vid]["emendas"] = d["nota"]
            neg = d["faixas"].get("Sem relevância ou sem justificativa", 0)
            txt = f"R$ {br(neg, 0)} em destinos sem relevância ou sem justificativa"
            if d["cobertura"] < 95:
                txt += f" (coleta parcial: {br(d['cobertura'])}% da cota lida)"
            detalhe[vid]["emendas"] = txt

    # notas de 0 a 10
    def serie(k):
        return [b[k] for b in bruto.values() if k in b]

    notas: dict[str, dict] = {vid: {} for vid in ids}
    mx = {k: max(serie(k)) for k in PESOS if serie(k)}
    mn = {k: min(serie(k)) for k in PESOS if serie(k)}
    med_ind = statistics.median(serie("indicacoes")) if serie("indicacoes") else 0
    for vid, b in bruto.items():
        n = notas[vid]
        if "presenca" in b:
            n["presenca"] = max(0.0, 10 - 0.5 * (100 - b["presenca"]))
        for k in ("fiscalizacao", "projetos"):
            if k in b:
                n[k] = 10 * b[k] / mx[k] if mx[k] else 0.0
        if "indicacoes" in b:
            n["indicacoes"] = min(10.0, 10 * b["indicacoes"] / med_ind) if med_ind else 0.0
        if "gastos" in b:
            amp = mx["gastos"] - mn["gastos"]
            n["gastos"] = 10 * (mx["gastos"] - b["gastos"]) / amp if amp else 10.0
        if "votacoes" in b:
            n["votacoes"] = 10 * b["votacoes"]
        if "emendas" in b:
            n["emendas"] = b["emendas"]

    vereadores = []
    for vid in ids:
        n = notas[vid]
        if not n:
            continue
        peso = sum(PESOS[k] for k in n)
        nota = sum(PESOS[k] * v for k, v in n.items()) / peso
        vereadores.append({
            "id": vid,
            "nome": c.VEREADORES[vid]["nome"],
            "nota": round(nota, 1),
            "criterios": {k: {"nota": round(n[k], 1), "detalhe": detalhe[vid].get(k, "")} for k in PESOS if k in n},
            "sem_dados": [k for k in PESOS if k not in n],
        })
    vereadores.sort(key=lambda x: (-x["nota"], x["nome"]))
    for i, v in enumerate(vereadores):
        v["posicao"] = i + 1 if i == 0 or v["nota"] != vereadores[i - 1]["nota"] else vereadores[i - 1]["posicao"]

    return {
        "atualizado": date.today().isoformat(),
        "pesos": PESOS,
        "rotulos": ROTULOS,
        "descricoes": DESCRICOES,
        "pontos_emenda": PONTOS_EMENDA,
        "vereadores": vereadores,
        "emendas_classificadas": {vid: d["itens"] for vid, d in sorted(em.items())},
    }


if __name__ == "__main__":
    r = calcular()
    c.salvar("ranking.json", r)
    for v in r["vereadores"]:
        print(v["posicao"], v["nome"], v["nota"], {k: x["nota"] for k, x in v["criterios"].items()})
