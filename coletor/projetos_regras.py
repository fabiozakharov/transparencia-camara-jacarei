"""Classificação dos projetos de vereadores para o ranking (regras do Fabio, 27/11/2026).

Negativos (−1):
  - repetem lei estadual ou federal (texto igual ou quase igual);
  - criam regulação exagerada, pouco explicada ou pouco útil;
  - aumentam salário de vereador, prefeito, vice ou secretários;
  - aumentam ou criam impostos (fora da reforma tributária);
  - criam dias, semanas ou datas comemorativas.
Positivos (+1):
  - diminuem burocracia ou impostos, geram transparência, sustam outros atos,
    reduzem benefícios da classe política.
Autor e coautores recebem a pontuação em dobro.
O resto fica "a definir" (vale 0) até o Fabio decidir a regra.

MANUAL guarda a decisão caso a caso; as regras por palavra-chave cobrem os casos óbvios
e os projetos novos. "sugerido": True marca uma avaliação feita pelo Claude que o Fabio
ainda não conferiu.
"""
from __future__ import annotations

import re

PONTOS = {"positivo": 1, "negativo": -1, "a definir": 0}
PESO_AUTOR = 2

# --- regras automáticas -------------------------------------------------------
REGRAS = [
    ("negativo", "Cria data comemorativa", re.compile(
        r"\bdia\b(?! a dia)|\bdias? municipa|semana|calend[áa]rio|inclui a encontros|institui e inclui", re.I)),
    ("negativo", "Aumenta salário de agente político", re.compile(
        r"subs[íi]dio|reajuste.*(vereador|prefeit|secret)|remunera[çc][ãa]o.*(vereador|prefeit|secret)", re.I)),
    ("negativo", "Cria ou aumenta imposto", re.compile(r"(cria|institui|majora|aumenta).*(taxa|tributo|imposto|contribui[çc][ãa]o)", re.I)),
    ("positivo", "Susta outro ato", re.compile(r"\bsusta", re.I)),
    ("positivo", "Diminui imposto", re.compile(r"anistia|isen[çc][ãa]o|incentivo fiscal|redu[çz].*(imposto|tribut|taxa)", re.I)),
    ("positivo", "Gera transparência", re.compile(
        r"transpar[êe]ncia|or[çc]amento cidad|transmiss[ãa]o da programa|painel municipal de consulta|"
        r"posi[çc][ãa]o do paciente na fila|divulga[çc][ãa]o de atendimento|presta[çc][ãa]o de informa[çc][õo]es", re.I)),
    ("positivo", "Diminui burocracia", re.compile(r"desburocrat|simplifica|dispensa de", re.I)),
]

GRUPOS_A_DEFINIR = [
    ("Honrarias (títulos, medalhas, selos, prêmios)", re.compile(r"t[íi]tulo|cidadan|medalha|selo|pr[êe]mio|homenagem", re.I)),
    ("Utilidade pública", re.compile(r"utilidade p[úu]blica|interesse p[úu]blico", re.I)),
    ("Nome de rua, praça ou viela", re.compile(r"denomina|denomia|\brua\b|viela|pra[çc]a|avenida", re.I)),
    ("Alteração de lei existente", re.compile(r"altera|revoga", re.I)),
    ("Saúde", re.compile(r"sa[úu]de|sus\b|m[ée]dic|vacina|tea\b|autis|paciente|enferm|psicol|oncol|diabet|card|infarto|varizes|bucal|terapia|medicamento|receita", re.I)),
    ("Segurança e violência", re.compile(r"viol[êe]ncia|crime|drog|seguran|vandal|v[íi]deo|c[âa]mera|monitor|abuso|ass[ée]dio|guarda|armas|vizinhan|hipersexual|adultiza|proerd|bombeiro", re.I)),
    ("Trânsito e mobilidade", re.compile(r"tr[âa]nsit|radar|mobilidade|sem[áa]foro|faixa de pedestre|mototáxi|mototaxi|sinaliza|vias|motoboy|entrega|placa|postes", re.I)),
    ("Animais e meio ambiente", re.compile(r"anima|abelha|eco|res[íi]duo|horta|ra[çc][ãa]o", re.I)),
    ("Educação e infância", re.compile(r"escol|creche|crian|inf[âa]nc|educa|matr[íi]cula|rec[ée]m|primeira inf", re.I)),
]

# --- decisões caso a caso -----------------------------------------------------
MANUAL = {
    # exemplos dados pelo Fabio
    "PLL 003/2026": ("negativo", "Repete lei estadual (exemplo do Fabio)", False),
    "PLL 028/2026": ("negativo", "Regulação exagerada (exemplo do Fabio)", False),
    # sugestões do Claude: repetem lei estadual ou federal
    "PLL 025/2025": ("negativo", "Repete lei federal (Libras: Lei 10.436/2002 e Decreto 5.626/2005)", True),
    "PLL 030/2026": ("negativo", "Repete lei federal (Libras: Lei 10.436/2002 e Decreto 5.626/2005)", True),
    "PLL 041/2026": ("negativo", "Repete lei federal (prioridade a idosos: Estatuto da Pessoa Idosa)", True),
    "PLL 036/2026": ("negativo", "Repete leis federal e estadual antifumo (Lei 9.294/1996 e Lei SP 13.541/2009)", True),
    "PLL 031/2025": ("negativo", "Repete lei federal (telemedicina: Lei 14.510/2022)", True),
    "PLL 134/2025": ("negativo", "Repete lei federal (ozonioterapia: Lei 14.648/2023)", True),
    "PLL 036/2025": ("negativo", "Repete lei federal (dados pessoais: LGPD, Lei 13.709/2018)", True),
    "PLL 031/2026": ("negativo", "Trata de prova em processo, assunto de lei federal", True),
    "PLL 077/2025": ("negativo", "Repete lei federal (alienação parental: Lei 12.318/2010)", True),
    # sugestões do Claude: regulação exagerada
    "PLL 007/2026": ("negativo", "Regulação exagerada (obriga entrega na portaria por motoboys)", True),
    "PLL 118/2025": ("negativo", "Regulação exagerada (exige exames cardiológicos em academias)", True),
    "PLL 039/2026": ("negativo", "Regulação exagerada (obrigação sobre recolhimento de brinquedos)", True),
    # sugestões do Claude: datas comemorativas que o título não deixa claro
    "PLL 100/2025": ("negativo", "Cria data comemorativa (Insanos Moto Clube no calendário)", True),
    "PLL 079/2026": ("negativo", "Cria data comemorativa (festa no calendário oficial)", True),
    # sugestões do Claude: positivos
    "PLL 060/2025": ("positivo", "Regras de moralidade para nomeação de agentes públicos", True),
    "PLL 047/2026": ("positivo", "Converte multas em serviço comunitário (menos ônus ao cidadão)", True),
    "PLL 015/2025": ("positivo", "Revoga exigência de prazo (menos burocracia)", True),
}


def classificar(chave: str, assunto: str) -> dict:
    if chave in MANUAL:
        classe, motivo, sug = MANUAL[chave]
        return {"classe": classe, "motivo": motivo, "sugerido": sug}
    for classe, motivo, rx in REGRAS:
        if rx.search(assunto or ""):
            return {"classe": classe, "motivo": motivo, "sugerido": False}
    grupo = next((g for g, rx in GRUPOS_A_DEFINIR if rx.search(assunto or "")), "Outros programas e políticas")
    return {"classe": "a definir", "motivo": grupo, "sugerido": False}
