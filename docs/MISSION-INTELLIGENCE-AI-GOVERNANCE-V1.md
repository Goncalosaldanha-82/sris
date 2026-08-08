# SRIS — AI Governance v1

Estado: implementado e preparado para implantação com IA globalmente desativada

Migração Alembic: `20260808_0003`

## Objetivo

A presença de `OPENAI_API_KEY` nunca é autorização suficiente para gastar. Cada
organização tem de possuir uma política explícita, criada por `owner` ou `admin`,
e cada chamada tem de caber simultaneamente nos limites mensal, por pedido e de
concorrência. Um bloqueio da IA não elimina a análise determinística.

## Gate de execução

Uma execução assistida só chega ao fornecedor quando todas as condições são
verdadeiras:

1. `SRIS_AI_ENABLED=true` e `OPENAI_API_KEY` existe no servidor;
2. o utilizador está autenticado e tem papel `owner`, `admin` ou `reviewer`;
3. a organização tem uma política configurada com `enabled=true`;
4. o modelo possui uma tabela de preços governada;
5. o pedido cabe no limite de entrada e saída por execução;
6. a quota mensal de pedidos, tokens e custo ainda tem saldo;
7. existe capacidade no limite de chamadas concorrentes.

O SRIS reserva primeiro o pior caso do pedido. Dentro dessa reserva, usa
`POST /v1/responses/input_tokens` para substituir a estimativa conservadora pela
contagem exata de entrada. Após a Responses API terminar, reconcilia a reserva
com `input_tokens`, `cached_input_tokens` e `output_tokens` reportados pelo
fornecedor. O limite `max_output_tokens` enviado ao modelo é o menor entre o teto
da aplicação e o teto da política.

Se o fornecedor falhar sem devolver `usage`, o ledger cobra provisoriamente toda
a reserva. É uma escolha deliberadamente conservadora: um timeout pode acontecer
depois de o fornecedor processar a resposta. A classificação
`conservative_failure_reservation` torna essa incerteza visível.

## Política inicial recomendada para o piloto

Criar primeiro com `enabled=false`:

```json
{
  "enabled": false,
  "monthly_request_limit": 20,
  "monthly_input_token_limit": 250000,
  "monthly_output_token_limit": 50000,
  "monthly_budget_usd": "5.00",
  "per_request_input_token_limit": 60000,
  "per_request_output_token_limit": 3000,
  "max_concurrent_requests": 1
}
```

Endpoint:

```text
PUT /api/organizations/{organization_id}/mission-intelligence/ai-governance/policy
```

Só depois do smoke test determinístico, da configuração do segredo e da leitura
do saldo deve a mesma política ser atualizada para `enabled=true`.

## Contabilidade e preços

O custo é guardado em inteiros (`micro-USD`) para evitar erros de ponto flutuante.
O ledger preserva as tarifas de entrada, entrada em cache e saída, o multiplicador,
a fonte e a data efetiva utilizadas naquela execução. As tarifas predefinidas
correspondem ao modo Standard e contexto curto publicado pela OpenAI em
2026-07-30 para `gpt-5.6`, `gpt-5.6-sol`, `gpt-5.6-terra` e `gpt-5.6-luna`.

O valor é uma estimativa operacional, não uma fatura. A fatura do fornecedor é a
fonte financeira definitiva. Para outro modelo ou modalidade de preço, a chamada
falha de forma segura até serem configuradas conjuntamente:

```env
SRIS_AI_INPUT_USD_PER_MTOK=
SRIS_AI_CACHED_INPUT_USD_PER_MTOK=
SRIS_AI_OUTPUT_USD_PER_MTOK=
SRIS_AI_PRICING_SOURCE=
SRIS_AI_PRICING_EFFECTIVE_DATE=
```

Processamento regional ou outro acréscimo deve ser representado em pontos base:

```env
SRIS_AI_PRICE_MULTIPLIER_BPS=11000
```

`10000` equivale a 1,00×; `11000`, a 1,10×.

## Persistência

| Tabela | Função |
|---|---|
| `mi_ai_organization_policies` | autorização e limites vigentes por organização |
| `mi_ai_usage_periods` | consumo e reservas do mês UTC |
| `mi_ai_usage_events` | ledger de cada tentativa e snapshot do preço |

Reservas sem finalização expiram por defeito ao fim de dez minutos e libertam
tokens/custo reservados, mantendo o pedido contado. O prazo pode ser alterado por
`SRIS_AI_RESERVATION_TTL_MINUTES`.

## Superfície operacional

| Método | Endpoint | Perfis |
|---|---|---|
| `GET` | `/api/organizations/{org}/mission-intelligence/ai-governance` | owner, admin, reviewer |
| `PUT` | `/api/organizations/{org}/mission-intelligence/ai-governance/policy` | owner, admin |
| `GET` | `/api/organizations/{org}/mission-intelligence/ai-governance/events` | owner, admin, reviewer |

O resumo apresenta consumo, reservas ativas, saldo de pedidos/tokens/orçamento e
o aviso de que o custo é estimado. O ledger não guarda a chave OpenAI, prompts nem
o conteúdo canónico; esses dados permanecem separados nos objetos próprios.

## Gate para ativação real

- implantação concluída com `SRIS_AI_ENABLED=false`;
- migração `20260808_0003` no head;
- `/health` e análise pública determinística aprovados;
- organização e utilizador piloto criados;
- política criada e verificada ainda desativada;
- `OPENAI_API_KEY` adicionada como segredo;
- ativação global e organizacional limitada ao piloto;
- uma única chamada M-001 executada;
- tokens, custo, response ID, IDs canónicos e revisão humana verificados;
- política novamente desativada se qualquer invariant falhar.
