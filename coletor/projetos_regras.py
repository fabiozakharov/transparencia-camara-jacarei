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
Segunda rodada (Fabio, 27/11/2026, ótica liberal: menos intervenção estatal, menos gasto público):
  positivos: fomentam a economia local; dão acesso a informação ou segurança; flexibilizam regras
    ou abrem a execução à iniciativa privada; geram acessibilidade.
  negativos: políticas ou programas vagos que geram gasto com ações para públicos específicos;
    passam da competência do vereador ou criam obrigações para a iniciativa privada;
    criam gratuidades, prioridades de atendimento ou vagas ("fura-fila"); repetem outro projeto;
    obrigações como exame toxicológico.
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
    # segunda rodada, exemplos e respostas do Fabio
    "PLL 014/2025": ("positivo", "Dá acesso a informação e segurança (exemplo do Fabio)", False),
    "PLL 016/2026": ("positivo", "Flexibiliza regra e abre execução à iniciativa privada (exemplo do Fabio)", False),
    "PLL 022/2026": ("negativo", "Política vaga em pauta íntima da família (exemplo do Fabio)", False),
    "PLL 029/2025": ("negativo", "Passa da competência do vereador e cria obrigações à iniciativa privada (exemplo do Fabio)", False),
    "PLL 034/2025": ("positivo", "Gera acessibilidade (exemplo do Fabio)", False),
    "PLL 041/2025": ("negativo", "Cria prioridade de atendimento e compete com lei federal (exemplo do Fabio)", False),
    "PLL 048/2026": ("negativo", "Projeto repetido (exemplo do Fabio)", False),
    "PLL 051/2026": ("negativo", "Projeto repetido (exemplo do Fabio)", False),
    "PLL 006/2025": ("negativo", "Exame toxicológico obrigatório: intervenção na liberdade", False),
    # segunda rodada, sugestões do Claude pela ótica liberal
    "PLL 002/2025": ("negativo", "Cria obrigação ao cidadão (microchip em animais)", True),
    "PLL 004/2025": ("negativo", "Restringe a liberdade de eventos", True),
    "PLL 007/2025": ("negativo", "Restringe a liberdade de eventos", True),
    "PLL 004/2026": ("positivo", "Fomenta a economia local (artesanato)", True),
    "PLL 008/2026": ("negativo", "Amplia fiscalização estatal (radar de ruído)", True),
    "PLL 009/2026": ("negativo", "Projeto repetido (radar de ruído)", True),
    "PLL 009/2025": ("negativo", "Programa com gasto público", True),
    "PLL 011/2025": ("negativo", "Campanha com gasto público", True),
    "PLL 012/2025": ("negativo", "Regulação exagerada (habitação de animais)", True),
    "PLL 013/2025": ("negativo", "Programa com gasto público", True),
    "PLL 015/2026": ("positivo", "Segurança (monitoramento das vias rurais)", True),
    "PLL 016/2025": ("negativo", "Gasto sem utilidade (troca de nome da Guarda)", True),
    "PLL 020/2025": ("positivo", "Segurança (câmeras em escolas)", True),
    "PLL 020/2026": ("positivo", "Menos burocracia (aceita receita particular)", True),
    "PLL 021/2025": ("positivo", "Acesso a informação e denúncia", True),
    "PLL 023/2026": ("negativo", "Gasto público para público específico", True),
    "PLL 024/2026": ("negativo", "Política vaga", True),
    "PLL 027/2026": ("negativo", "Programa para público específico", True),
    "PLL 028/2025": ("negativo", "Programa com gasto público", True),
    "PLL 029/2026": ("negativo", "Serviço exclusivo para público específico", True),
    "PLL 030/2025": ("negativo", "Intervenção nas escolas (hino obrigatório)", True),
    "PLL 032/2025": ("positivo", "Segurança (crimes digitais)", True),
    "PLL 032/2026": ("negativo", "Política vaga com gasto", True),
    "PLL 033/2026": ("positivo", "Ressarcimento ao município (menos gasto público)", True),
    "PLL 035/2026": ("negativo", "Prioridade de atendimento para categoria", True),
    "PLL 037/2026": ("negativo", "Política vaga", True),
    "PLL 038/2025": ("positivo", "Regula e abre serviço à iniciativa privada (crematório de animais)", True),
    "PLL 038/2026": ("positivo", "Informação e segurança (cadastro de violência doméstica)", True),
    "PLL 040/2025": ("negativo", "Programa com gasto público", True),
    "PLL 040/2026": ("negativo", "Política vaga", True),
    "PLL 042/2025": ("negativo", "Programa para público específico", True),
    "PLL 043/2026": ("positivo", "Acesso a informação (placas identificadas)", True),
    "PLL 044/2025": ("negativo", "Programa com gasto público", True),
    "PLL 048/2025": ("negativo", "Atividades alusivas a datas", True),
    "PLL 049/2025": ("positivo", "Segurança (crime organizado)", True),
    "PLL 050/2025": ("positivo", "Acesso a informação (vacinas)", True),
    "PLL 051/2025": ("negativo", "Programa com gasto público", True),
    "PLL 052/2025": ("positivo", "Moralidade: veda homenagem a condenados", True),
    "PLL 053/2025": ("positivo", "Moralidade: veda homenagem a condenados", True),
    "PLL 054/2025": ("positivo", "Moralidade: veda homenagem a condenados", True),
    "PLL 055/2025": ("positivo", "Moralidade: veda homenagem a condenados", True),
    "PLL 052/2026": ("negativo", "Programa para público específico", True),
    "PLL 053/2026": ("negativo", "Atendimento exclusivo para público específico", True),
    "PLL 054/2026": ("negativo", "Cria gratuidades e compete com lei federal", True),
    "PLL 056/2025": ("negativo", "Programa com gasto público", True),
    "PLL 057/2025": ("negativo", "Programa com gasto público", True),
    "PLL 058/2025": ("negativo", "Cria obrigação e benefício específico", True),
    "PLL 063/2025": ("positivo", "Gera acessibilidade", True),
    "PLL 064/2026": ("negativo", "Programa com gasto público", True),
    "PLL 066/2025": ("negativo", "Política vaga e tema de lei federal", True),
    "PLL 066/2026": ("negativo", "Política vaga", True),
    "PLL 075/2026": ("negativo", "Projeto repetido (política de mobilidade)", True),
    "PLL 067/2025": ("positivo", "Acesso a informação (agendamento de consultas)", True),
    "PLL 068/2025": ("negativo", "Política vaga", True),
    "PLL 069/2025": ("negativo", "Regulação de eventos privados", True),
    "PLL 069/2026": ("negativo", "Cria benefício para público específico", True),
    "PLL 071/2025": ("negativo", "Política vaga", True),
    "PLL 071/2026": ("negativo", "Programa com gasto público", True),
    "PLL 072/2025": ("negativo", "Política vaga", True),
    "PLL 072/2026": ("positivo", "Acesso a informação (compartilhamento de dados)", True),
    "PLL 073/2026": ("negativo", "Cria benefício com gasto público", True),
    "PLL 075/2025": ("negativo", "Política vaga", True),
    "PLL 076/2025": ("negativo", "Programa com gasto público", True),
    "PLL 076/2026": ("negativo", "Ação para público específico", True),
    "PLL 077/2026": ("negativo", "Obrigação à iniciativa privada", True),
    "PLL 078/2026": ("negativo", "Programa para público específico", True),
    "PLL 079/2025": ("positivo", "Segurança nas escolas", True),
    "PLL 080/2025": ("negativo", "Programa com gasto público", True),
    "PLL 081/2025": ("negativo", "Gasto público obrigatório", True),
    "PLL 082/2025": ("negativo", "Programa vago", True),
    "PLL 083/2025": ("positivo", "Flexibiliza regra e fomenta economia local (venda de alimentos)", True),
    "PLL 084/2025": ("negativo", "Gratuidade para público específico", True),
    "PLL 086/2025": ("positivo", "Segurança (PROERD)", True),
    "PLL 088/2025": ("negativo", "Política vaga", True),
    "PLL 090/2025": ("negativo", "Política para público específico", True),
    "PLL 092/2025": ("negativo", "Gasto público (regime 24h)", True),
    "PLL 093/2025": ("positivo", "Menos burocracia (aceitação de receitas)", True),
    "PLL 094/2025": ("negativo", "Amplia estrutura e gasto público", True),
    "PLL 095/2025": ("positivo", "Acesso a informação (documento de medicamentos)", True),
    "PLL 096/2025": ("negativo", "Política vaga", True),
    "PLL 098/2025": ("negativo", "Obrigação à iniciativa privada (carrinhos adaptados)", True),
    "PLL 099/2025": ("negativo", "Programa com gasto público", True),
    "PLL 102/2025": ("positivo", "Segurança viária (faixa de pedestre)", True),
    "PLL 103/2025": ("negativo", "Amplia fiscalização estatal (decibelímetro)", True),
    "PLL 104/2025": ("negativo", "Prioridade de atendimento para categoria", True),
    "PLL 106/2025": ("positivo", "Segurança (vandalismo)", True),
    "PLL 107/2025": ("positivo", "Segurança com participação privada (vizinhança solidária)", True),
    "PLL 108/2025": ("positivo", "Segurança com participação privada (videomonitoramento)", True),
    "PLL 113/2025": ("negativo", "Política para público específico", True),
    "PLL 119/2025": ("positivo", "Informação e segurança (contador nos semáforos)", True),
    "PLL 121/2025": ("negativo", "Programa com gasto público", True),
    "PLL 126/2025": ("negativo", "Programa com gasto público", True),
    "PLL 128/2025": ("negativo", "Programa para público específico", True),
    "PLL 129/2025": ("negativo", "Projeto repetido (altas habilidades)", True),
    "PLL 131/2025": ("negativo", "Garantia de vaga (prioridade)", True),
    "PLL 132/2025": ("positivo", "Segurança (câmeras em UMSF e UPA)", True),
    "PLL 137/2025": ("positivo", "Regulamenta e abre serviço privado (mototáxi)", True),
    "PLL 140/2025": ("negativo", "Programa com gasto público", True),
    "PLL 141/2025": ("negativo", "Programa com gasto público", True),
    "PR 001/2025": ("negativo", "Restringe liberdade (porte de armas)", True),
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
