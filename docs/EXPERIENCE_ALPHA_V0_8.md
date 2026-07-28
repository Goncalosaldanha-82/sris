# SRIS Enterprise Experience Alpha v0.8

## Decision Workspace

Esta release acrescenta uma superfície única para reconstruir uma decisão: fundamento, alternativas, pressupostos, restrições, riscos, relações e gatilhos de revisão.

O indicador de sustentação é explicável e versionado (`decision-support-0.8`). Não representa probabilidade de a decisão estar correta; mede apenas a completude e integridade da estrutura documentada.

## Contrato

`GET /api/v1/experience/missions/{mission_id}/decisions/{decision_id}/workspace`

## Limites

- A independência das fontes é aproximada a partir da origem declarada.
- A condição de revisão ainda não possui campo próprio no modelo legado.
- O workspace não recomenda nem aprova decisões.
