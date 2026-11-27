"""Gera painel/dados.js a partir de dados/*.json (projetos, votações, emendas por vereador)."""
import json
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


P = []
for chave, p in projetos.items():
    P.append({
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

NOMES = {k: v["nome"] for k, v in c.VEREADORES.items()}
NOMES.update({"mesa-diretora": "Mesa Diretora", "prefeito": "Prefeito"})
meta = json.loads((D / "coleta.json").read_text(encoding="utf-8"))
dados = {"nomes": NOMES, "P": P, "V": V, "E": E, "ok": OK, "cats": emendas["categorias"], "atualizado": meta["executado_em"][:10]}
(RAIZ / "painel" / "dados.js").write_text("window.DADOS=" + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
print(len(P), len(V), len(E), OK)
