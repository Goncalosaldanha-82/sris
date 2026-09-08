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
ATLAS_DATABASE_URL=${{Postgres.DATABASE_URL}}
ATLAS_JWT_SECRET=<segredo aleatório exclusivo, mínimo 32 bytes>
ATLAS_ENV=production
SRIS_PILOT_SHOW_RESET_LINK=false
SRIS_AI_ENABLED=false
```

O PostgreSQL tem de pertencer exclusivamente ao serviço `sris-pilot-v1`. Nunca reutilizar a base de dados de `sris-production` ou de `SRIS-Mission-Intelligence`. O backend também aceita a referência Railway com o nome `DATABASE_URL`, mas `ATLAS_DATABASE_URL` torna a ligação explícita e tem precedência.

O arranque é interrompido se um deploy Railway tentar usar SQLite. Isto evita contas e missões aparentemente funcionais que desaparecem no redeploy.

Só ativar assistência depois de configurar a chave como secret do Railway e validar o endpoint:

```text
SRIS_AI_ENABLED=true
OPENAI_API_KEY=<secret Railway — nunca colocar no GitHub>
```

## Recuperação de palavra-passe

`SRIS_PILOT_SHOW_RESET_LINK=true` só é aceitável numa validação técnica controlada: devolve o token ao browser. No staging partilhado deve ser `false` e deve ser ligado email transacional antes de validar a entrega real.

## Smoke test após deploy

1. `GET /health` deve devolver base de dados OK.
2. A página `/` deve apresentar o nascer do sol, login, criação de conta e recuperação.
3. Criar uma conta nova; confirmar que o workspace abre.
4. Terminar sessão e voltar a entrar.
5. Testar recuperação de palavra-passe e confirmar que a palavra-passe antiga deixa de funcionar.
6. Criar uma missão, sair, voltar a entrar e confirmar persistência.
7. Carregar vários documentos e confirmar a listagem e proveniência.
8. Exportar a secção e o relatório da missão.
9. Se a assistência estiver configurada, executar uma pergunta curta e confirmar que o estado apresentado é verdadeiro.
10. Repetir em desktop e num iPhone real, incluindo teclado aberto no login.

## Segurança para produção

Antes de promover este piloto: desligar reset-link no browser e topups simulados; ativar email transacional, rate limiting, proteção anti-abuso, pagamentos reais, termos/privacidade, observabilidade e backups testados. A chave OpenAI deve existir exclusivamente como secret do Railway.
