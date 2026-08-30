from __future__ import annotations

from copy import deepcopy


_CATALOG = {
    "schema": "sris_fictional_demo_catalog",
    "schema_version": "1.0",
    "catalog_version": "2026-08-30",
    "notice": (
        "Demonstração pública com dados integralmente fictícios. Qualquer semelhança "
        "com entidades, pessoas, locais ou projetos reais é coincidência."
    ),
    "missions": {
        "DEMO-MUN-001": {
            "id": "DEMO-MUN-001",
            "title": "Território Habitado 2035",
            "subtitle": "Articular PDM, habitação acessível e uma rede de refúgios climáticos.",
            "organization": "Município de Vale Sereno (entidade fictícia)",
            "domain": "Ordenamento, habitação e resiliência climática",
            "status": "Missão em avaliação — dados fictícios",
            "confidence": "Moderada",
            "decision": "DEC-DEMO-003 · Rede distribuída sob validação",
            "method_notice": (
                "Caso exclusivamente demonstrativo. Todos os nomes, valores, datas e "
                "resultados são fictícios e servem apenas para ilustrar o método SRIS."
            ),
            "situation": {
                "summary": (
                    "O município fictício enfrenta simultaneamente escassez de habitação a "
                    "preço comportável, edifícios devolutos e exposição crescente a ondas de "
                    "calor, incêndio, seca e tempestades. A revisão do PDM e a adaptação de "
                    "equipamentos públicos estavam a avançar em processos separados."
                ),
                "attention": [
                    {
                        "title": "Habitação e proteção climática eram tratadas separadamente.",
                        "description": "O PDM, a carta de riscos, o património devoluto e os equipamentos públicos não estavam ligados numa leitura única.",
                        "level": "Conflito de planeamento",
                    },
                    {
                        "title": "A urgência não elimina a necessidade de proteção social.",
                        "description": "Uma intervenção climática pode agravar preços ou deslocar residentes se os efeitos na oferta habitacional não forem avaliados.",
                        "level": "Condição de decisão",
                    },
                ],
                "chain": [
                    {"number": "01", "label": "Observação", "value": "Riscos e pressão habitacional", "note": "Zonas de calor, incêndio e tempestade sobrepõem-se a bairros com menor oferta acessível.", "state": "completed"},
                    {"number": "02", "label": "Evidência", "value": "Dossier territorial integrado", "note": "PDM, edifícios devolutos, acessibilidade, vulnerabilidade climática e capacidade dos equipamentos.", "state": "completed"},
                    {"number": "03", "label": "Hipótese", "value": "Rede distribuída", "note": "Reabilitar ativos existentes pode proteger residentes e ampliar oferta sem nova dispersão urbana.", "state": "completed"},
                    {"number": "04", "label": "Alternativas", "value": "3 comparadas", "note": "Grande centro único, rede de equipamentos e solução mista com habitação resiliente.", "state": "completed"},
                    {"number": "05", "label": "Decisão", "value": "Piloto em dois territórios", "note": "Solução mista condicionada a validação técnica, social e financeira.", "state": "completed"},
                    {"number": "06", "label": "Resultado", "value": "Ainda não demonstrado", "note": "A missão define primeiro baseline, indicadores e regras de atribuição.", "state": "pending"},
                    {"number": "07", "label": "Aprendizagem", "value": "Pendente de execução", "note": "Nenhuma conclusão é apresentada antes da medição e revisão humana.", "state": "learning"},
                ],
            },
            "analysis": {
                "central_question": (
                    "Que alterações ao PDM e que rede de edifícios devem ser priorizadas para "
                    "proteger a população de extremos climáticos sem agravar a escassez nem o "
                    "preço da habitação?"
                ),
                "available_evidence": (
                    "Cartografia fictícia do PDM e de riscos; inventário de edifícios públicos "
                    "e devolutos; tempos de acesso pedonal; procura e preços de habitação; "
                    "auditorias térmicas e estimativas preliminares de reabilitação."
                ),
                "unknowns": (
                    "Disponibilidade jurídica dos imóveis, procura real durante cada tipo de "
                    "evento, capacidade de operação prolongada e impacto das intervenções na "
                    "oferta e no preço da habitação."
                ),
                "alternatives": [
                    {"id": "ALT-DEMO-001", "title": "Centro climático municipal único", "state": "Comparada", "rationale": "Operação concentrada, mas acesso desigual e ponto único de falha."},
                    {"id": "ALT-DEMO-002", "title": "Rede de escolas e equipamentos adaptados", "state": "Comparada", "rationale": "Maior proximidade, exigindo coordenação e disponibilidade sazonal."},
                    {"id": "ALT-DEMO-003", "title": "Rede mista com reabilitação habitacional", "state": "Preferida sob validação", "rationale": "Combina proteção imediata, recuperação de ativos e oferta habitacional resiliente."},
                ],
            },
            "evidence": [
                {"id": "EVD-DEMO-001", "type": "Cartografia", "title": "Vulnerabilidade territorial combinada", "description": "Sobreposição fictícia de calor, incêndio, tempestade, mobilidade e vulnerabilidade social.", "method": "Análise multicritério com revisão técnica municipal.", "limitation": "A escala territorial não substitui avaliação de cada edifício.", "status": "Em revisão no cenário", "confidence": "Moderada"},
                {"id": "EVD-DEMO-002", "type": "Inventário", "title": "Edifícios e capacidade de adaptação", "description": "Equipamentos públicos e imóveis devolutos avaliados quanto a acesso, conforto térmico e uso compatível.", "method": "Triagem documental e auditoria técnica simulada.", "limitation": "Titularidade e custo de intervenção ainda não estão confirmados em todos os casos.", "status": "Parcialmente verificada", "confidence": "Moderada"},
                {"id": "EVD-DEMO-003", "type": "Baseline", "title": "Habitação acessível e deslocação", "description": "Linha de base fictícia para oferta, esforço financeiro das famílias e risco de deslocação.", "method": "Série municipal simulada com segmentação territorial.", "limitation": "A relação causal entre intervenção e preços exigirá acompanhamento longitudinal.", "status": "Baseline proposto", "confidence": "Baixa a moderada"},
            ],
            "learning": [
                {"id": "LRN-DEMO-001", "title": "Aprendizagem ainda não confirmada", "description": "A preferência por uma rede mista é uma decisão de piloto, não prova de impacto."},
                {"id": "LRN-DEMO-002", "title": "O efeito habitacional faz parte do resultado", "description": "Proteção climática, acessibilidade e preço da habitação serão medidos em conjunto para evitar uma melhoria aparente com dano social."},
            ],
        }
    },
}


def fictional_demo_catalog() -> dict:
    return deepcopy(_CATALOG)


def fictional_demo_mission(mission_code: str) -> dict | None:
    mission = _CATALOG["missions"].get(mission_code)
    return deepcopy(mission) if mission else None
