"""Gera painel/dados.js a partir de dados/*.json (projetos, votações, emendas por vereador)."""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "coletor"))
import coletar as c  # noqa: E402

D = RAIZ / "dados"
projetos = json.loads((D / "projetos.json").read_text(encoding="utf-8"))
votacoes = json.loads((D / "votacoes.json").read_text(encoding="utf-8"))
emendas = json.loads((D / "emendas.json").read_text(encoding="utf-8"))

ultimo = {}
for v in sorted(votacoes, key=lambda x: x["data"]):
    ultimo.setdefault(v["projeto"], []).append(v)


def situacao(chave, p):
    if p.get("norma"):
        return "Virou norma"
    vs = ultimo.get(chave, [])
    if vs:
        r = vs[-1]["resultado"]
        if r.startswith("aprovad"):
            return "Aprovado"
        if r.startswith("rejeitad"):
            return "Rejeitado"
        if r.startswith("retirad"):
            return "Retirado"
    return "Em tramitação"


RE_HONRA = re.compile(r"t[ií]tulo|cidad[aã]|medalha|honra|pr[eê]mio|diploma|comenda|m[eé]rito", re.I)
P = []
for chave, p in projetos.items():
    pareceres = [[d["etapa"], d["url"], d["data"]] for d in p["documentos"] if re.search(r"parecer|relat", d["etapa"], re.I)]
    P.append({
        "pc": sorted(pareceres, key=lambda x: x[2]), "h": 1 if p["tipo"] == "PDL" and RE_HONRA.search(p["assunto"]) else 0,
        "k": chave, "t": p["tipo"], "a": p["autores"], "s": p["assunto"][:220], "n": p.get("norma"),
        "st": situacao(chave, p), "u": p["documentos"][0]["url"] if p["documentos"] else "",
        "d": p["documentos"][0]["data"] if p["documentos"] else "",
    })

V = []
for v in votacoes:
    nom = v.get("votos_nominais") or {}
    sims = sum(1 for x in nom.values() if x == "sim")
    completo = bool(nom) and v["favoraveis"] is not None and sims == v["favoraveis"]
    V.append({
        "d": v["data"], "k": v["projeto"], "s": v["assunto"][:200], "au": v["autoria"][:80], "r": v["resultado"],
        "f": v["favoraveis"], "c": v["contrarios"], "ab": v["abstencoes"], "au_": v["ausencias"],
        "nom": nom if completo else {}, "b": v.get("boletim"),
    })

conf = {(x["vereador"]): abs(x["soma_itens"] - 818879.22) < 0.05 for x in emendas.get("conferencia", []) if not x.get("subemenda")} if "conferencia" in emendas else {}
E = [{"v": i["vereador"], "x": i["exercicio"], "c": i["categoria"], "d": i["destino"], "o": i["orgao"], "val": i["valor"], "u": i["documento"]}
     for i in emendas["itens"] if not i["subemenda"]]
somas = {}
for i in E:
    somas[i["v"]] = somas.get(i["v"], 0) + i["val"]
OK = {v: abs(s - 818879.22) < 0.05 for v, s in somas.items()}

def ler(nome, padrao):
    arq = D / nome
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else padrao


# Vetos do prefeito: o autor é quem fez o projeto vetado ("de autoria do Vereador X").
VT = []
for v in votacoes:
    if v["projeto"].split(" ")[0] not in ("VT", "VP"):
        continue
    autor = re.search(r"de autoria d[oa] Vereador[a]? ([^,.;]+)", v["assunto"])
    lei = re.search(r"Lei(?: Complementar)? n\.?º?\s*([\d.]+/\d{4})", v["assunto"])
    r = v["resultado"]
    VT.append({"k": v["projeto"], "d": v["data"], "s": re.sub(r"Registrou-se.*|FASE DO EXPEDIENTE.*", "", v["assunto"])[:260],
               "a": c.identificar(autor.group(1)) if autor else [], "lei": lei.group(1) if lei else "",
               "r": "Veto derrubado" if r.startswith(("rejeitad", "derrubad")) else "Veto mantido" if r.startswith(("aprovad", "mantid")) else r.capitalize(),
               "f": v["favoraveis"], "c": v["contrarios"]})

ranking = ler("ranking.json", None)
R = None
if ranking:
    R = {"rot": ranking.get("rotulos", {}), "desc": ranking.get("descricoes", {}), "pesos": ranking.get("pesos", {}),
         "v": [{"id": x["id"], "pos": x["posicao"], "nota": x["nota"], "sd": x.get("sem_dados", []),
                "c": {k: [y["nota"], y.get("detalhe", "")] for k, y in x["criterios"].items()}} for x in ranking["vereadores"]],
         "at": ranking.get("atualizado", "")}
sit = {x["k"]: x["st"] for x in P}
PL = [{"k": x["projeto"], "s": x["assunto"][:240], "a": x["autores"], "c": x["classe"], "m": x["motivo"], "sg": 1 if x.get("sugerido") else 0,
       "pt": x.get("pontos_autor", 0), "n": x.get("norma"), "d": x.get("data") or "", "u": x.get("url") or "", "st": sit.get(x["projeto"], "")}
      for x in (ranking or {}).get("projetos_classificados", [])]
AP = [{"n": a["numero"], "d": a["data"], "t": a["tema"], "co": a["comissao"], "p": a["presentes"], "m": a["conduziram"], "u": a["url"]}
      for a in ler("audiencias.json", [])]
NT = [{"d": n["data"], "t": n["titulo"], "u": n["url"], "x": n["destaque"], "c": n["citados"], "r": n["resumo"][:200]}
      for n in ler("noticias.json", [])]
LI = [{"m": l["modalidade"], "t": l["titulo"], "a": l["ano"], "st": l["status"], "o": l["objeto"], "d": l["data"], "u": l["url"]}
      for l in ler("licitacoes.json", [])]
PA = ler("pauta.json", {})

NOMES = {k: v["nome"] for k, v in c.VEREADORES.items()}
NOMES.update({"mesa-diretora": "Mesa Diretora", "prefeito": "Prefeito"})
meta = json.loads((D / "coleta.json").read_text(encoding="utf-8"))
dados = {"nomes": NOMES, "P": P, "V": V, "E": E, "ok": OK, "cats": emendas["categorias"], "VT": VT, "R": R, "PL": PL, "AP": AP, "NT": NT, "LI": LI, "PA": PA, "atualizado": meta["executado_em"][:10]}
(RAIZ / "painel" / "dados.js").write_text("window.DADOS=" + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
print(len(P), len(V), len(E), len(VT), len(AP), len(NT), len(LI), bool(R), OK)
