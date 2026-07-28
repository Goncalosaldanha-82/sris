# SRIS Enterprise Experience Alpha v0.2

## Incremento entregue

A v0.2 deixa de reconstruir toda a experiência apenas no browser e introduz uma camada de API orientada ao SEES.

### Endpoints de experiência

- `GET /api/v1/experience/missions/{mission_id}/entry`
- `GET /api/v1/experience/missions/{mission_id}/map`
- `GET /api/v1/experience/missions/{mission_id}/impact/{object_id}`
- `GET /api/v1/experience/missions/{mission_id}/focus/{object_type}/{object_id}`
- `GET /api/v1/experience/missions/{mission_id}/timeline`
- `GET /api/v1/experience/missions/{mission_id}/guidance/{intention}`

### Capacidades

- Mission Entry calculada no servidor;
- pontos de atenção e lacunas agregados;
- Mission Map tenant-scoped;
- Impact Chain calculada no backend por BFS e profundidade controlada;
- Focus Surface com validação de pertença à missão;
- Timeline lógica inicial construída a partir de objetos e eventos de auditoria;
- catálogo versionado de perguntas para as cinco intenções;
- frontend ligado aos novos contratos de experiência;
- contadores de missão e Guided Reasoning com perguntas servidas pelo backend.

## Limites declarados

- As respostas do Guided Reasoning ainda não são persistidas como sessões próprias. O frontend preserva o fluxo e apresenta o contrato que será materializado na próxima versão.
- A Timeline lógica é real, mas ainda não constitui projeção bitemporal integral.
- O mapa continua a usar SVG próprio e não Cytoscape.
- A revisão de decisões continua dependente dos endpoints de domínio existentes.

## Validação

- 18 testes automatizados aprovados;
- `node --check` aprovado para o frontend;
- base de dados de testes e caches excluídas do pacote final.
