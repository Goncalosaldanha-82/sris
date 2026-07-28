# SRIS Enterprise — Pilot Candidate v0.9

## Estado
Esta release está preparada para demonstração e piloto controlado. Não é apresentada como produção comercial sem validação em ambiente real, teste de restauro e revisão de segurança externa.

## Capacidade nova
`Provenance` é agora uma entidade independente. Toda nova evidência criada pela API exige proveniência existente ou criada atomicamente.

### Regras
- contributos humanos e não humanos seguem o mesmo método epistemológico;
- origem não humana exige `model_or_system` e `version`;
- proveniência usa `invalidated`, não `refuted`;
- evidência legada sem proveniência é detetada pela auditoria estrutural;
- proveniência fica ligada à evidência no grafo e é visível no Mission Map.

## Ontologia preservada
Observation → Evidence → Hypothesis → Assumption → Constraint → Alternative → Decision → Implementation → Outcome → Learning.

## Validação desta release
- 35 testes backend/API aprovados em três execuções isoladas;
- validação sintática Python concluída;
- validação sintática JavaScript concluída;
- RLS incluída na migração PostgreSQL `005_provenance.sql`;
- pacote limpo de caches, bytecode, base de testes e segredos locais.

## Antes de cliente pagante em produção
- executar instalação limpa numa segunda máquina;
- ensaiar backup e restauro;
- executar revisão de segurança externa;
- colocar num endereço HTTPS controlado;
- observar pelo menos três utilizadores externos no percurso login → missão → evidência → proveniência → decisão.
