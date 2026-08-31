from __future__ import annotations

from copy import deepcopy


_CATALOG = {
    "schema": "sris_fictional_demo_catalog",
    "schema_version": "1.0",
    "catalog_version": "2026-08-31",
    "notice": (
        "Demonstração pública com dados integralmente fictícios. Qualquer semelhança "
        "com entidades, pessoas, locais ou projetos reais é coincidência."
    ),
    "missions": {
        "DEMO-TA-001": {
            "id": "DEMO-TA-001",
            "title": "Eficiência Hoteleira 2026",
            "subtitle": "Distinguir ocupação, operação e anomalia antes de intervir nos consumos.",
            "organization": "Hotel Horizonte Verde (unidade fictícia)",
            "domain": "Alojamento turístico · sustentabilidade e eficiência de recursos",
            "status": "Missão em avaliação — dados fictícios",
            "confidence": "Moderada",
            "decision": "Piloto de medição aprovado",
            "decision_code": "DEC-TA-003",
            "method_notice": (
                "Caso exclusivamente demonstrativo. Todos os nomes, valores, datas e "
                "resultados são fictícios e servem apenas para ilustrar o método SRIS."
            ),
            "situation": {
                "summary": (
                    "Uma unidade de alojamento fictícia registou um aumento de 15% no "
                    "consumo total de água e de 9% no consumo de energia face ao período "
                    "anterior. No mesmo intervalo alteraram-se a ocupação, o funcionamento "
                    "da lavandaria, a rega e várias rotinas de manutenção. O aumento bruto "
                    "não permite concluir, por si só, que existe ineficiência."
                ),
                "attention": [
                    {
                        "title": "O indicador bruto mistura consumo e atividade.",
                        "description": "Sem normalização por quarto-noite ocupado e por serviço operacional, maior consumo pode refletir apenas maior atividade.",
                        "level": "Problema de comparação",
                    },
                    {
                        "title": "Reduzir recursos não pode degradar a experiência.",
                        "description": "Conforto, higiene, qualidade do serviço e carga de trabalho são condições da decisão, não efeitos secundários invisíveis.",
                        "level": "Condição de decisão",
                    },
                ],
                "chain": [
                    {"number": "01", "label": "Observação", "value": "+15% água · +9% energia", "note": "Variações totais registadas num período com atividade diferente.", "state": "completed"},
                    {"number": "02", "label": "Evidência", "value": "Baseline operacional", "note": "Faturas, contadores, ocupação, lavandaria, rega, manutenção e ocorrências.", "state": "completed"},
                    {"number": "03", "label": "Hipótese", "value": "Causas concorrentes", "note": "Ocupação, fuga, rega, lavandaria e procedimentos permanecem separados.", "state": "completed"},
                    {"number": "04", "label": "Alternativas", "value": "3 comparadas", "note": "Substituição de equipamentos, protocolo operacional ou lavandaria externa.", "state": "completed"},
                    {"number": "05", "label": "Decisão", "value": "Medição dirigida", "note": "Piloto de oito semanas antes de investimento generalizado.", "state": "completed"},
                    {"number": "06", "label": "Ação", "value": "Instrumentar e testar", "note": "Submedição, inspeção de fugas e protocolo operacional controlado.", "state": "open"},
                    {"number": "07", "label": "Resultado", "value": "Ainda não demonstrado", "note": "Água e energia serão comparadas por atividade, custo e qualidade do serviço.", "state": "pending"},
                    {"number": "08", "label": "Aprendizagem", "value": "Pendente de execução", "note": "Nenhuma conclusão é publicada antes da medição e revisão humana.", "state": "learning"},
                ],
            },
            "analysis": {
                "central_question": (
                    "Que intervenção reduz o consumo de água e energia por quarto-noite "
                    "ocupado, com viabilidade operacional e económica, sem degradar a "
                    "experiência do hóspede nem transferir o impacto para outro serviço?"
                ),
                "available_evidence": (
                    "Faturas e leituras mensais fictícias; quartos-noite ocupados; ciclos "
                    "de lavandaria; horários de rega; ocorrências de manutenção; custos "
                    "operacionais e registos de reclamações e conforto."
                ),
                "unknowns": (
                    "Distribuição do consumo por zona; existência e dimensão de fugas; "
                    "efeito meteorológico na rega; consumo efetivo da lavandaria; adesão "
                    "da equipa e impacto da intervenção na experiência do hóspede."
                ),
                "alternatives": [
                    {"id": "ALT-TA-001", "title": "Substituir equipamentos em todos os quartos", "state": "Comparada", "rationale": "Pode reduzir consumo, mas antecipa investimento antes de confirmar causas, baseline e efeito na experiência."},
                    {"id": "ALT-TA-002", "title": "Medição dirigida e protocolo operacional", "state": "Preferida sob validação", "rationale": "Combina submedição, inspeção de fugas e teste controlado, preservando a possibilidade de comparar antes e depois."},
                    {"id": "ALT-TA-003", "title": "Externalizar a lavandaria", "state": "Comparada", "rationale": "Reduz consumo interno aparente, mas pode transferir custo e impacto ambiental sem melhorar a eficiência do sistema."},
                ],
            },
            "evidence": [
                {"id": "EVD-TA-001", "type": "Baseline", "title": "Consumo por quarto-noite ocupado", "description": "Série fictícia normaliza água e energia pela atividade real da unidade.", "method": "Cruzamento mensal entre contadores, faturas e quartos-noite ocupados.", "limitation": "A medição geral ainda não separa quartos, lavandaria, cozinha e rega.", "status": "Em revisão no cenário", "confidence": "Moderada"},
                {"id": "EVD-TA-002", "type": "Operação", "title": "Ocorrências, lavandaria e rega", "description": "Registos fictícios ligam alterações de procedimento e manutenção aos consumos.", "method": "Linha temporal operacional com validação pela equipa da unidade.", "limitation": "Alguns registos são manuais e podem estar incompletos.", "status": "Parcialmente verificada", "confidence": "Moderada"},
                {"id": "EVD-TA-003", "type": "Qualidade do serviço", "title": "Conforto e experiência do hóspede", "description": "A decisão inclui reclamações, conforto, higiene e continuidade do serviço.", "method": "Indicadores operacionais e questionário breve antes e depois do teste.", "limitation": "Atribuição exige amostra e período comparáveis.", "status": "Protocolo proposto", "confidence": "Baixa a moderada"},
            ],
            "business_case": {
                "notice": (
                    "Valores exclusivamente fictícios para demonstrar a leitura económica da missão. "
                    "São identificados como baseline, orçamento ou projeção; nenhum corresponde a um "
                    "resultado real de cliente."
                ),
                "currency": "EUR",
                "baseline": {
                    "status": "Baseline anual fictícia",
                    "annual_resource_spend_eur": 142000,
                    "avoidable_operating_loss_eur": 18600,
                    "revenue_at_risk_eur": 9000,
                },
                "pilot": {
                    "status": "Orçamento fictício",
                    "duration_weeks": 8,
                    "investment_eur": 12800,
                    "equipment_eur": 8900,
                    "internal_people_cost_eur": 3900,
                    "internal_hours": 92,
                    "planned_interruption_hours": 6,
                },
                "projection": {
                    "status": "Cenário central fictício — não demonstrado",
                    "direct_savings_eur_per_year": 13600,
                    "protected_revenue_eur_per_year": 4200,
                    "recurring_cost_eur_per_year": 2400,
                    "net_benefit_eur_per_year": 15400,
                    "payback_months": 10,
                    "net_return_3y_eur": 33400,
                    "roi_3y_percent": 261,
                },
                "actual": {
                    "status": "Pendente de medição",
                    "net_benefit_eur_per_year": None,
                    "payback_months": None,
                    "roi_3y_percent": None,
                },
                "human_resources": [
                    {"role": "Direção", "hours": 16},
                    {"role": "Operações", "hours": 36},
                    {"role": "Manutenção", "hours": 28},
                    {"role": "Finanças e dados", "hours": 12},
                ],
                "material_resources": [
                    {"resource": "Subcontadores temporários", "quantity": 6},
                    {"resource": "Registadores acústicos de fugas", "quantity": 2},
                    {"resource": "Analisador portátil de energia", "quantity": 1},
                    {"resource": "Kit de registo e protocolo de medição", "quantity": 1},
                ],
                "formulas": [
                    "Benefício líquido anual = poupança direta + receita protegida − custo recorrente.",
                    "Retorno líquido a 3 anos = benefício líquido anual × 3 − investimento inicial.",
                    "ROI a 3 anos = retorno líquido a 3 anos ÷ investimento inicial.",
                ],
            },
            "learning": [
                {"id": "LRN-TA-001", "title": "Normalizar antes de classificar", "description": "Uma variação total não deve ser tratada como ineficiência sem considerar ocupação e atividade operacional."},
                {"id": "LRN-TA-002", "title": "Aprendizagem ainda não confirmada", "description": "A alternativa preferida é uma decisão de teste, não prova de poupança, retorno ou impacto."},
            ],
        }
    },
}


def fictional_demo_catalog() -> dict:
    return deepcopy(_CATALOG)


def fictional_demo_mission(mission_code: str) -> dict | None:
    mission = _CATALOG["missions"].get(mission_code)
    return deepcopy(mission) if mission else None
