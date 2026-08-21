# SRIS Pilot V1 — Railway

Este ramo foi preparado para um serviço Railway isolado da produção.

## Branch

`pilot-v1-september-2026`

## Serviço recomendado

Criar um serviço separado, por exemplo `sris-pilot-v1`, ligado exclusivamente ao ramo acima. Não alterar o serviço de produção existente.

## Variáveis mínimas

```text
SRIS_PILOT_MODE=true
SRIS_PUBLIC_SIGNUP_ENABLED=true
SRIS_PILOT_SHOW_RESET_LINK=true
SRIS_BILLING_TEST_MODE=true
SRIS_TRIAL_CREDIT_EUR=5.00
SRIS_AI_ENABLED=true
SRIS_OPENAI_MODEL=gpt-5.6-terra
OPENAI_API_KEY=<secret Railway — nunca colocar no GitHub>
```

Manter também as variáveis canónicas já exigidas pelo backend, incluindo `DATABASE_URL`, segredos JWT e qualquer configuração de storage já utilizada pela instalação SRIS.

## Preços e controlo de margem

A carteira do piloto usa micro-euros e regista movimentos num ledger dedicado. O custo do fornecedor e o preço ao cliente ficam separados. Defaults atuais para Terra podem ser alterados sem deploy:

```text
SRIS_OPENAI_INPUT_USD_PER_M=1.25
SRIS_OPENAI_OUTPUT_USD_PER_M=7.50
SRIS_BILLING_EUR_PER_USD=0.92
SRIS_AI_PRICE_MULTIPLIER=1.50
SRIS_PLAN_PROFESSIONAL_EUR=49
SRIS_PLAN_ORGANIZATION_EUR=149
```

Antes de lançamento comercial, rever câmbio, preços oficiais do fornecedor, IVA, margem, limites de utilização e política de reembolso.

## Recuperação de palavra-passe

No Pilot V1, `SRIS_PILOT_SHOW_RESET_LINK=true` devolve o token de recuperação ao browser apenas para permitir teste end-to-end sem fornecedor de email. Em produção esta opção deve ser `false` e deve ser ligado um serviço transacional de email.

## Pagamentos

Os carregamentos de 10 €, 25 € e 50 € são simulados enquanto `SRIS_BILLING_TEST_MODE=true`. Não representam cobrança financeira real. Antes de produção deve ser ligado um PSP (por exemplo Stripe ou equivalente), com webhook assinado e reconciliação de ledger.

## Smoke test após deploy

1. `GET /health` deve devolver base de dados OK.
2. A página `/` deve apresentar o nascer do sol, login, criação de conta e recuperação.
3. Criar uma conta nova; verificar crédito inicial.
4. Terminar sessão e voltar a entrar.
5. Testar recuperação de palavra-passe e confirmar que a palavra-passe antiga deixa de funcionar.
6. Em `/app`, abrir Copiloto IA e executar uma pergunta curta.
7. Confirmar débito de créditos e movimento no ledger.
8. Testar um carregamento simulado.
9. Criar uma nova Mission Intelligence e pedir a primeira leitura analítica.
10. Repetir em desktop e mobile.

## Segurança para produção

Antes de promover este piloto: desligar reset-link no browser e topups simulados; ativar email transacional, rate limiting, proteção anti-abuso, pagamentos reais, termos/privacidade, observabilidade e backups testados. A chave OpenAI deve existir exclusivamente como secret do Railway.