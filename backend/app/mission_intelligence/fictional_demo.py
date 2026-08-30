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
            "title": "Água Municipal 360",
            "subtitle": "Reduzir perdas de água em equipamentos municipais sem degradar o serviço.",
            "organization": "Município de Vale Sereno (entidade fictícia)",
            "domain": "Eficiência hídrica e governação municipal",
            "status": "Piloto concluído — dados fictícios",
            "confidence": "Moderada",
            "decision": "DEC-DEMO-003 · Expandir de forma condicionada",
            "method_notice": (
                "Caso exclusivamente demonstrativo. Todos os nomes, valores, datas e "
                "resultados são fictícios e servem apenas para ilustrar o método SRIS."
            ),
            "situation": {
                "summary": (
                    "A autarquia fictícia gere 12 edifícios. Faturas e leituras manuais "
                    "sugeriam consumo anómalo, mas não permitiam localizar perdas nem separar "
                    "avarias, sazonalidade e alterações de utilização."
                ),
                "attention": [
                    {
                        "title": "A linha de base não distinguia causas.",
                        "description": "O consumo mensal agregado ocultava picos noturnos e diferenças entre edifícios.",
                        "level": "Lacuna inicial",
                    },
                    {
                        "title": "A expansão depende de capacidade operacional.",
                        "description": "Alertas sem responsável e prazo de resposta não produzem redução sustentada.",
                        "level": "Condição de escala",
                    },
                ],
                "chain": [
                    {"number": "01", "label": "Observação", "value": "Consumo anómalo", "note": "Faturas e leituras mensais em 12 edifícios fictícios.", "state": "completed"},
                    {"number": "02", "label": "Evidência", "value": "Linha de base de 8 semanas", "note": "Medição horária em 3 edifícios-piloto fictícios.", "state": "completed"},
                    {"number": "03", "label": "Hipótese", "value": "Perdas fora do horário", "note": "Picos noturnos poderiam indicar fugas ou equipamentos mal regulados.", "state": "completed"},
                    {"number": "04", "label": "Alternativas", "value": "3 comparadas", "note": "Monitorização, manutenção calendarizada e substituição integral.", "state": "completed"},
                    {"number": "05", "label": "Decisão", "value": "Piloto em 3 edifícios", "note": "Monitorização com protocolo de resposta em 48 horas.", "state": "completed"},
                    {"number": "06", "label": "Resultado", "value": "−14% no piloto", "note": "Valor fictício, corrigido por ocupação e comparado com a linha de base.", "state": "completed"},
                    {"number": "07", "label": "Aprendizagem", "value": "Tecnologia + responsabilidade", "note": "A redução ocorreu quando cada alerta teve dono, prazo e confirmação.", "state": "learning"},
                ],
            },
            "analysis": {
                "central_question": (
                    "Que intervenção reduz perdas com menor custo total e sem interromper "
                    "serviços municipais essenciais?"
                ),
                "available_evidence": (
                    "24 meses de faturas fictícias; leituras horárias durante 8 semanas; "
                    "registos de ocupação; ordens de manutenção e inspeções técnicas simuladas."
                ),
                "unknowns": (
                    "Sazonalidade anual, durabilidade da redução e custo de integração com "
                    "sistemas legados fora dos três edifícios-piloto."
                ),
                "alternatives": [
                    {"id": "ALT-DEMO-001", "title": "Monitorização e resposta em 48 horas", "state": "Selecionada para piloto", "rationale": "Baixo investimento inicial e aprendizagem rápida."},
                    {"id": "ALT-DEMO-002", "title": "Manutenção calendarizada reforçada", "state": "Comparada", "rationale": "Menor dependência tecnológica, mas deteção mais lenta."},
                    {"id": "ALT-DEMO-003", "title": "Substituição integral de equipamentos", "state": "Adiada", "rationale": "Custo elevado antes de localizar as causas dominantes."},
                ],
            },
            "evidence": [
                {"id": "EVD-DEMO-001", "type": "Série temporal", "title": "Linha de base de consumo", "description": "Oito semanas de leituras horárias em três edifícios fictícios.", "method": "Contadores simulados e validação semanal.", "limitation": "Não representa um ciclo anual completo.", "status": "Verificada no cenário", "confidence": "Elevada"},
                {"id": "EVD-DEMO-002", "type": "Observação", "title": "Picos fora do horário", "description": "Dois edifícios apresentaram consumo noturno persistente.", "method": "Comparação com horários e ocupação simulados.", "limitation": "O padrão indica anomalia, não identifica sozinho a causa.", "status": "Confirmada no cenário", "confidence": "Moderada"},
                {"id": "EVD-DEMO-003", "type": "Resultado", "title": "Redução corrigida no piloto", "description": "Redução fictícia de 14% após correções e protocolo de resposta.", "method": "Comparação com linha de base, corrigida por ocupação.", "limitation": "A persistência para além de 12 semanas não foi testada.", "status": "Resultado demonstrativo", "confidence": "Moderada"},
            ],
            "learning": [
                {"id": "LRN-DEMO-001", "title": "Um alerta precisa de responsável", "description": "A monitorização só alterou o resultado quando cada alerta passou a ter responsável, prazo e fecho verificável."},
                {"id": "LRN-DEMO-002", "title": "Medir antes de substituir", "description": "A linha de base evitou uma substituição integral prematura e concentrou o investimento nas causas observadas."},
            ],
        }
    },
}


def fictional_demo_catalog() -> dict:
    return deepcopy(_CATALOG)


def fictional_demo_mission(mission_code: str) -> dict | None:
    mission = _CATALOG["missions"].get(mission_code)
    return deepcopy(mission) if mission else None
