# SRIS Enterprise Experience Alpha v0.6

## Incremento principal

As conclusões do Guided Reasoning passam a atualizar imediatamente as três projeções centrais da experiência:

- Mission Entry;
- Mission Map;
- Timeline lógica.

O backend devolve um `experience_snapshot` coerente na resposta que conclui a sessão. O frontend aplica esse snapshot sem recarregar a página nem obrigar o utilizador a abandonar o fluxo.

## Novo contrato

`GET /api/v1/experience/missions/{mission_id}/snapshot`

O contrato devolve, no mesmo instante lógico:

- `entry`;
- `map`;
- `timeline`;
- `generated_at`.

## Comportamento da interface

Quando a intenção termina:

1. os objetos materializados aparecem no resumo;
2. a plataforma confirma que situação, mapa e percurso foram atualizados;
3. o utilizador pode abrir imediatamente o Mapa da Missão;
4. os novos objetos já estão navegáveis, sem atualização manual do navegador.

## Integridade

- As projeções são calculadas no servidor sobre o estado confirmado da base de dados.
- O frontend não inventa nós, relações ou momentos.
- Snapshots incompletos são rejeitados de forma segura.
- A atualização mantém a segregação por organização e missão.

## Validação

- 27 testes backend/API aprovados.
- 6 testes de contrato frontend aprovados.
- JavaScript validado por `node --check`.
- 0 falhas.
