# SRIS Enterprise Experience Alpha v0.7

## Revisão antes da materialização

O Guided Reasoning passa a ter três estados explícitos:

1. `active` — recolha das respostas;
2. `awaiting_confirmation` — revisão e correção;
3. `completed` — materialização confirmada.

Nenhuma Observação, Investigação, Hipótese, Decisão, Alternativa ou Aprendizagem é criada antes da confirmação final do utilizador.

### Novos contratos

- `PATCH /api/v1/experience/guided-sessions/{session_id}/answers/{question_id}`
- `POST /api/v1/experience/guided-sessions/{session_id}/confirm`

A pré-visualização é determinística, não usa inferência generativa e não escreve na base de dados. A confirmação é idempotente e devolve um snapshot atualizado da experiência.

## Validação

- 29 testes backend/API;
- 6 testes frontend;
- validação sintática de JavaScript;
- zero falhas.
