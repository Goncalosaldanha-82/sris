# SRIS Enterprise Experience Alpha v0.9 — Provenance Object

Esta release introduz `Provenance` como entidade independente e transversal.

## Princípio
O valor de um contributo não é determinado automaticamente pela sua origem. É avaliado pela qualidade da proveniência, clareza das limitações e robustez da verificação.

## Modelo
- origem: humano, modelo de IA, agente de IA, sistema, organização ou desconhecida;
- aquisição: observação direta, entrevista, documento, sensor, drone, satélite, API, importação ou geração;
- método/modalidade;
- ator/emissor;
- modelo ou sistema e versão;
- contexto de input e política;
- limitações e incerteza;
- estado de verificação: declarado, em revisão, confirmado, contestado, invalidado ou indisponível;
- referência de integridade.

## Integridade
- nova evidência exige exatamente um registo de proveniência existente ou aninhado;
- origem não humana exige modelo/sistema e versão;
- a auditoria estrutural assinala evidência legada sem proveniência;
- `refutado` permanece reservado ao estado de pressupostos.

## Ontologia preservada
Observation → Evidence → Hypothesis → Assumption → Constraint → Alternative → Decision → Implementation → Outcome → Learning.
