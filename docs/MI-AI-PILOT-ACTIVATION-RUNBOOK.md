# SRIS — Runbook de ativação do piloto de IA

Estado inicial obrigatório: aplicação saudável, motor determinístico disponível e
`SRIS_AI_ENABLED=false`.

## 1. Criar a identidade institucional

Depois de implantar o gate do piloto, executar no PowerShell, a partir da raiz do
repositório:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\CREATE_MI_PILOT.ps1
```

O script pede email e palavra-passe localmente, cria ou reutiliza o utilizador,
cria a organização piloto quando necessário e grava a política inicial com
`enabled=false`. O UUID da organização é copiado para a área de transferência.

## 2. Criar um projeto OpenAI isolado

Na plataforma OpenAI:

1. criar o projeto `SRIS Production Pilot`;
2. definir um hard spend limit mensal de USD 5,00;
3. criar uma service account exclusiva para o Railway;
4. criar a chave dessa service account e copiá-la uma única vez.

Referências oficiais:

- https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform
- https://platform.openai.com/settings/organization/limits

## 3. Preparar o Railway sem ativar IA

Adicionar as variáveis seguintes e manter `SRIS_AI_ENABLED=false`:

```env
SRIS_AI_PILOT_ORGANIZATION_ID=<UUID copiado pelo script>
ATLAS_SELF_REGISTRATION_ENABLED=false
ATLAS_ORGANIZATION_CREATION_ENABLED=false
OPENAI_API_KEY=<chave da service account>
SRIS_AI_MODEL=gpt-5.6
SRIS_AI_ENABLED=false
```

Aplicar as alterações e confirmar:

- `/health` responde `200`;
- `ai_pilot_organization_configured=true`;
- `institutional_onboarding_closed=true`;
- `ai_configured=false`.

## 4. Abrir apenas o gate global

Alterar somente:

```env
SRIS_AI_ENABLED=true
```

Aplicar o deployment. A política da organização continua desativada, por isso
nenhuma chamada pode ainda atravessar o gate.

## 5. Executar uma única chamada controlada

Na raiz do repositório:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\RUN_MI_AI_PILOT.ps1
```

O script valida o fornecedor, o UUID e a política; ativa a política apenas para
uma execução da M-001 e volta a desativá-la no final, mesmo perante erro.

Critérios de aprovação:

- `ai_status=completed`;
- `execution_mode=hybrid`;
- `provider_response_id` e tokens presentes no ledger;
- custo estimado coerente com a utilização;
- todas as referências da saída pertencem a IDs canónicos existentes;
- revisão humana permanece `required`.

Se qualquer critério falhar, não reativar a política até o evento ser revisto.
