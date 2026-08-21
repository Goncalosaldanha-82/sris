# SRIS — AI Governance v1

Estado: implementado e preparado para implantação com IA globalmente desativada

Migrações Alembic: até `20260815_0011`

## Objetivo

A presença de `OPENAI_API_KEY` nunca é autorização suficiente para gastar. Em
produção, apenas o UUID exato definido em `SRIS_AI_PILOT_ORGANIZATION_ID` pode
atravessar o gate do piloto. Essa organização tem ainda de possuir uma política
explícita, criada por `owner` ou `admin`, e cada chamada tem de caber
nos limites técnicos por pedido e de concorrência. Os valores mensais são, por
defeito, limiares auditáveis que não interrompem uma Missão. Uma organização
pode optar explicitamente por convertê-los em limites rígidos. Um bloqueio da IA
não elimina a análise determinística.

## Gate de execução

Uma execução assistida só chega ao fornecedor quando todas as condições são
verdadeiras:

1. `SRIS_AI_ENABLED=true` e `OPENAI_API_KEY` existe no servidor;
2. `SRIS_AI_PILOT_ORGANIZATION_ID` contém um UUID canónico;
3. o auto-registo e a criação livre de organizações estão explicitamente fechados;
4. o pedido pertence exatamente a essa organização piloto;
5. o utilizador está autenticado e tem papel `owner`, `admin` ou `reviewer`;
6. a organização tem uma política configurada com `enabled=true`;
7. o modelo possui uma tabela de preços governada;
8. o pedido cabe no limite de entrada e saída por execução;
9. existe capacidade no limite de chamadas concorrentes.

Pedidos, tokens e custo mensais continuam integralmente contabilizados. Quando
um limiar mensal é alcançado, o SRIS emite um aviso operacional e mantém a
Missão disponível. Só bloqueia por esse motivo quando
`enforce_monthly_limits=true` tiver sido escolhido pela organização.

A investigação contextual acrescenta um gate independente:
`SRIS_CONTEXT_RESEARCH_ENABLED=true`. Quando pedida, a execução reserva ainda o
pior caso de seis pesquisas web antes de contactar o fornecedor. A saída só é
aceite se as fontes citadas constarem das fontes efetivamente recuperadas nessa
execução e se o dossier permanecer `in_review` com revisão humana obrigatória.

Sem o UUID do piloto, a configuração de IA permanece falsa em Railway/produção.
Um utilizador que crie outra organização pode usar o motor determinístico, mas
recebe `organization_not_authorized` antes de qualquer contagem ou chamada à
OpenAI. O endpoint público de estado revela apenas se o gate está configurado;
nunca revela o UUID autorizado.

Depois de criar o utilizador e a organização piloto, a implantação deve fixar:

```env
ATLAS_SELF_REGISTRATION_ENABLED=false
ATLAS_ORGANIZATION_CREATION_ENABLED=false
```

Em produção, a IA permanece não configurada enquanto estes dois valores não
estiverem explicitamente fechados. O login dos utilizadores existentes continua
disponível.

O SRIS reserva primeiro o pior caso do pedido. Dentro dessa reserva, usa
`POST /v1/responses/input_tokens` para substituir a estimativa conservadora pela
contagem exata de entrada. Após a Responses API terminar, reconcilia a reserva
com `input_tokens`, `cached_input_tokens`, `output_tokens` e pesquisas web
observadas. O limite `max_output_tokens` enviado ao modelo é o menor entre o teto
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
  "enforce_monthly_limits": false,
  "monthly_request_limit": 20,
  "monthly_input_token_limit": 250000,
  "monthly_output_token_limit": 50000,
  "monthly_budget_usd": "5.00",
  "per_request_input_token_limit": 60000,
  "per_request_output_token_limit": 6000,
  "max_concurrent_requests": 1
}
```

Endpoint:

```text
PUT /api/organizations/{organization_id}/mission-intelligence/ai-governance/policy
```

Só depois do smoke test determinístico, da configuração do segredo e da leitura
do saldo deve a mesma política ser atualizada para `enabled=true`.

Com `enforce_monthly_limits=false`, os quatro valores mensais são limiares de
monitorização: geram avisos, permanecem no ledger e não terminam o diálogo. Os
limites por pedido e de concorrência continuam rígidos, porque protegem o
contrato técnico de cada chamada sem limitar o crescimento do arquivo da
Missão. Use `enforce_monthly_limits=true` apenas quando a organização pretender
uma interrupção mensal obrigatória.

O eventual limite de utilização ou de despesa configurado diretamente no
fornecedor é independente da aplicação e pode recusar pedidos quando for
atingido. Essa recusa externa é preservada e apresentada como falha repetível;
o SRIS não consegue eliminar limites impostos pelo fornecedor.

## Contabilidade e preços

O custo é guardado em inteiros (`micro-USD`) para evitar erros de ponto flutuante.
O ledger preserva as tarifas de entrada, entrada em cache, saída e pesquisa web,
o multiplicador, a fonte e a data efetiva utilizadas naquela execução. As tarifas
predefinidas correspondem ao modo Standard e contexto curto verificado em
2026-08-10 para `gpt-5.6`, `gpt-5.6-sol`, `gpt-5.6-terra` e `gpt-5.6-luna`. A
pesquisa web é reservada a USD 0,01 por chamada, configurável por
`SRIS_WEB_SEARCH_RATE_MICROUSD_PER_CALL`.

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
| `mi_ai_usage_periods` | consumo e reservas do mês UTC, incluindo pesquisas web |
| `mi_ai_usage_events` | ledger de cada tentativa e snapshot dos preços de tokens e pesquisa |

Reservas sem finalização expiram por defeito ao fim de dez minutos e libertam
tokens/custo reservados, mantendo o pedido contado. O prazo pode ser alterado por
`SRIS_AI_RESERVATION_TTL_MINUTES`.

## Superfície operacional

| Método | Endpoint | Perfis |
|---|---|---|
| `GET` | `/api/organizations/{org}/mission-intelligence/ai-governance` | owner, admin, reviewer |
| `PUT` | `/api/organizations/{org}/mission-intelligence/ai-governance/policy` | owner, admin |
| `GET` | `/api/organizations/{org}/mission-intelligence/ai-governance/events` | owner, admin, reviewer |

O resumo apresenta consumo, reservas ativas, saldo de pedidos/tokens/orçamento,
avisos dos limiares mensais e o aviso de que o custo é estimado. O ledger não
guarda a chave OpenAI, prompts nem o conteúdo canónico; esses dados permanecem
separados nos objetos próprios.

## Gate para ativação real

- implantação concluída com `SRIS_AI_ENABLED=false`;
- migração `20260815_0011` no head;
- `/health` e análise pública determinística aprovados;
- organização e utilizador piloto criados;
- auto-registo e criação de organizações fechados no Railway;
- projeto OpenAI dedicado, chave de serviço e hard spend limit de USD 5,00;
- política criada e verificada ainda desativada;
- `SRIS_AI_PILOT_ORGANIZATION_ID` definido com o UUID exato da organização;
- `OPENAI_API_KEY` adicionada como segredo;
- ativação global e organizacional limitada ao piloto;
- uma única chamada M-001 executada;
- tokens, custo, response ID, IDs canónicos e revisão humana verificados;
- política novamente desativada se qualquer invariant falhar.
