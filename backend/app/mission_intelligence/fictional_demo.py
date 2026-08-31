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
            "confidence_definition": (
                "Evidência suficiente para autorizar um teste controlado, mas ainda "
                "insuficiente para afirmar causa, poupança ou retorno."
            ),
            "property_profile": {
                "rooms": 84,
                "average_occupancy_percent": 68,
                "annual_available_room_nights": 30660,
                "annual_occupied_room_nights": 20849,
                "operating_model": "Lavandaria, cozinha, piscina e rega operadas internamente",
            },
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
                "decision_matrix": {
                    "scale": "1 = fraco · 5 = forte",
                    "criteria": [
                        {"id": "traceability", "label": "Rastreabilidade"},
                        {"id": "effectiveness", "label": "Eficácia"},
                        {"id": "cost", "label": "Custo"},
                        {"id": "risk", "label": "Risco controlado"},
                        {"id": "reversibility", "label": "Reversibilidade"},
                        {"id": "experience", "label": "Experiência"},
                        {"id": "robustness", "label": "Robustez"},
                    ],
                    "rows": [
                        {"alternative_id": "ALT-TA-001", "label": "Substituição geral", "scores": [2, 4, 2, 2, 1, 3, 2], "total": 16},
                        {"alternative_id": "ALT-TA-002", "label": "Medição dirigida", "scores": [5, 4, 4, 4, 5, 4, 5], "total": 31},
                        {"alternative_id": "ALT-TA-003", "label": "Lavandaria externa", "scores": [2, 3, 3, 2, 3, 3, 2], "total": 18},
                    ],
                },
            },
            "evidence": [
                {"id": "EVD-TA-001", "type": "Baseline", "title": "Consumo por quarto-noite ocupado", "description": "Série fictícia normaliza água e energia pela atividade real da unidade.", "method": "Cruzamento mensal entre contadores, faturas e quartos-noite ocupados.", "limitation": "A medição geral ainda não separa quartos, lavandaria, cozinha e rega.", "status": "Em revisão no cenário", "confidence": "Moderada"},
                {"id": "EVD-TA-002", "type": "Operação", "title": "Ocorrências, lavandaria e rega", "description": "Registos fictícios ligam alterações de procedimento e manutenção aos consumos.", "method": "Linha temporal operacional com validação pela equipa da unidade.", "limitation": "Alguns registos são manuais e podem estar incompletos.", "status": "Parcialmente verificada", "confidence": "Moderada"},
                {"id": "EVD-TA-003", "type": "Qualidade do serviço", "title": "Conforto e experiência do hóspede", "description": "A decisão inclui reclamações, conforto, higiene e continuidade do serviço.", "method": "Indicadores operacionais e questionário breve antes e depois do teste.", "limitation": "Atribuição exige amostra e período comparáveis.", "status": "Protocolo proposto", "confidence": "Baixa a moderada"},
            ],
            "evidence_graph": {
                "nodes": [
                    {"id": "EVD-TA-001", "kind": "Evidência", "label": "Consumo normalizado", "detail": "Faturas e contadores cruzados com quartos-noite ocupados. Limitação: a leitura geral ainda mistura zonas."},
                    {"id": "EVD-TA-002", "kind": "Evidência", "label": "Operação e ocorrências", "detail": "Lavandaria, rega e manutenção na mesma linha temporal. Limitação: parte do registo é manual."},
                    {"id": "EVD-TA-003", "kind": "Evidência", "label": "Qualidade do serviço", "detail": "Conforto, higiene e reclamações funcionam como condições de decisão, ainda com amostra limitada."},
                    {"id": "HYP-TA-001", "kind": "Hipótese", "label": "Causas concorrentes", "detail": "Ocupação, fuga, rega, lavandaria e procedimento continuam separados até existir medição dirigida."},
                    {"id": "ALT-TA-002", "kind": "Alternativa", "label": "Medição dirigida", "detail": "Alternativa preferida sob validação porque preserva comparação, rastreabilidade e reversibilidade."},
                    {"id": "DEC-TA-003", "kind": "Decisão", "label": "Autorizar piloto", "detail": "Piloto de oito semanas aprovado; não constitui prova de poupança nem decisão de investimento generalizado."},
                ],
                "links": [
                    {"from": "EVD-TA-001", "to": "HYP-TA-001"},
                    {"from": "EVD-TA-002", "to": "HYP-TA-001"},
                    {"from": "EVD-TA-003", "to": "HYP-TA-001"},
                    {"from": "HYP-TA-001", "to": "ALT-TA-002"},
                    {"from": "ALT-TA-002", "to": "DEC-TA-003"},
                ],
            },
            "business_case": {
                "notice": (
                    "Valores exclusivamente fictícios para demonstrar a leitura económica da missão. "
                    "São identificados como baseline, orçamento ou projeção; nenhum corresponde a um "
                    "resultado real de cliente."
                ),
                "currency": "EUR",
                "baseline": {
                    "status": "Baseline anual fictícia",
                    "water_consumption_m3_per_year": 15000,
                    "water_tariff_eur_per_m3": 2.0,
                    "energy_consumption_kwh_per_year": 509091,
                    "energy_tariff_eur_per_kwh": 0.22,
                    "annual_resource_spend_eur": 142000,
                    "annual_resource_spend_basis": "12 meses de faturas fictícias de água e energia.",
                    "avoidable_operating_loss_eur": 18600,
                    "avoidable_operating_loss_basis": "Horas de manutenção, desperdício e indisponibilidade operacional estimados.",
                    "revenue_at_risk_eur": 9000,
                    "revenue_at_risk_basis": "Compensações, indisponibilidade de quartos e incidentes de serviço possíveis; não realizados.",
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
                "selected_scenario_id": "central",
                "scenario_scope_note": (
                    "A redução de água é mais ambiciosa porque o cenário inclui fuga e rega; "
                    "a energia considera apenas otimização operacional, sem substituição geral de equipamentos."
                ),
                "scenarios": [
                    {
                        "id": "prudent",
                        "label": "Prudente",
                        "status": "Projeção fictícia — não demonstrada",
                        "water_saving_m3_per_year": 1400,
                        "water_tariff_eur_per_m3": 2.0,
                        "energy_saving_kwh_per_year": 22000,
                        "energy_tariff_eur_per_kwh": 0.22,
                        "direct_savings_eur_per_year": 7640,
                        "protected_revenue_eur_per_year": 1800,
                        "protected_revenue_basis": "Dois incidentes evitados × 900 € de receita sob risco.",
                        "recurring_cost_eur_per_year": 2400,
                        "recurring_cost_basis": "Monitorização, calibração e manutenção anual.",
                        "net_benefit_eur_per_year": 7040,
                        "payback_months": 22,
                        "net_return_3y_eur": 8320,
                        "roi_3y_percent": 65,
                    },
                    {
                        "id": "central",
                        "label": "Central",
                        "status": "Projeção fictícia — não demonstrada",
                        "water_saving_m3_per_year": 2400,
                        "water_tariff_eur_per_m3": 2.0,
                        "energy_saving_kwh_per_year": 40000,
                        "energy_tariff_eur_per_kwh": 0.22,
                        "direct_savings_eur_per_year": 13600,
                        "protected_revenue_eur_per_year": 4200,
                        "protected_revenue_basis": "Três incidentes evitados × 1 400 € de receita sob risco.",
                        "recurring_cost_eur_per_year": 2400,
                        "recurring_cost_basis": "Monitorização, calibração e manutenção anual.",
                        "net_benefit_eur_per_year": 15400,
                        "payback_months": 10,
                        "net_return_3y_eur": 33400,
                        "roi_3y_percent": 261,
                    },
                    {
                        "id": "favorable",
                        "label": "Favorável",
                        "status": "Projeção fictícia — não demonstrada",
                        "water_saving_m3_per_year": 3200,
                        "water_tariff_eur_per_m3": 2.0,
                        "energy_saving_kwh_per_year": 55000,
                        "energy_tariff_eur_per_kwh": 0.22,
                        "direct_savings_eur_per_year": 18500,
                        "protected_revenue_eur_per_year": 6200,
                        "protected_revenue_basis": "Quatro incidentes evitados × 1 550 € de receita sob risco.",
                        "recurring_cost_eur_per_year": 2800,
                        "recurring_cost_basis": "Monitorização reforçada, calibração e manutenção anual.",
                        "net_benefit_eur_per_year": 21900,
                        "payback_months": 7,
                        "net_return_3y_eur": 52900,
                        "roi_3y_percent": 413,
                    },
                ],
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
                    "Poupança direta = água evitada × tarifa da água + energia evitada × tarifa da energia.",
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
