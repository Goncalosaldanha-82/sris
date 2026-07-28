## SRIS Enterprise Experience Alpha v0.8

O raciocínio guiado permite agora rever e corrigir todas as respostas antes de criar objetos definitivos na missão.

# SRIS Enterprise Experience Alpha v0.3

Esta edição acrescenta a primeira fatia vertical do SEES à superfície de raciocínio do SRIS com a fundação enterprise: autenticação, organizações segregadas, permissões, PostgreSQL, RLS, encriptação, auditoria, integrações, backups e deployment.

## O que está implementado

- Observações, evidências, hipóteses concorrentes, pressupostos, restrições, alternativas, decisões, implementações, ações, resultados e aprendizagens como objetos próprios.
- Distribuição posterior normalizada entre hipóteses concorrentes da mesma investigação. A soma é sempre 1.
- Valor esperado da informação por divergência KL para priorizar novos testes ou observações.
- Refutação formal de pressupostos por evidência e preservação temporal do estado.
- Avaliação de sustentação da atribuição executada no servidor, versionada e reconstruível.
- Auditoria estrutural do raciocínio.
- Reutilização explícita de aprendizagens entre missões ou decisões.
- Grafo de proveniência ligado ao backend.
- Multi-tenancy na aplicação e por Row-Level Security no PostgreSQL.
- Mensagens de validação legíveis na API e no frontend.
- O fluxo `Opportunity` foi retirado da API pública desta edição. Valor económico só deve reaparecer depois de baseline, intervenção, resultado e avaliação de atribuição.


## Launcher Windows v0.3

Esta edição inclui uma experiência de arranque sem comandos:

- `PRIMEIRA_CONFIGURACAO_SRIS.cmd` cria o `.env` com segredos aleatórios, inicia os serviços, cria o administrador e carrega a demonstração;
- `ABRIR_SRIS_LAUNCHER.cmd` abre a consola gráfica Windows;
- o Launcher inicia, para, abre, verifica e mostra os logs do SRIS.

Consulte `docs/WINDOWS_LAUNCHER.md`.

## Arranque local

```bash
cp .env.example .env
# Substitua todos os valores CHANGE... e GENERATE...
docker compose up --build
```

Criar o primeiro administrador:

```bash
docker compose exec app python -m app.scripts.bootstrap_admin \
  --email admin@exemplo.pt \
  --password 'UMA_PALAVRA_PASSE_FORTE' \
  --organization 'Organização Piloto'
```

Carregar uma missão demonstrativa completa:

```bash
docker compose exec app python -m app.scripts.seed_demo \
  --organization-slug organizacao-piloto
```

Abrir `http://localhost:8000`.

## Fluxo nuclear

```text
Observação → Evidência → Hipóteses concorrentes → Decisão → Implementação
→ Resultado → Avaliação de atribuição → Aprendizagem → Reutilização
```

Pressupostos, restrições e alternativas permanecem independentes e podem sobreviver à decisão que os originou.

## Testes

```bash
pytest
```

A suite cobre autenticação, segregação entre organizações, encriptação, posteriores normalizadas, valor da informação, validações obrigatórias, refutação, atribuição, auditoria, grafo, contrato da API, frontend e retirada pública de `Opportunity`.

## Limite desta edição

Esta é uma **Pilot Release pronta para teste controlado**, não uma certificação de produção. Antes de tratar dados críticos ou confidenciais de clientes, complete `docs/PRODUCTION_GATE.md`: teste de intrusão independente, MFA/SSO, DPIA/RGPD, monitorização, gestão de segredos, testes de restauro, resposta a incidentes e revisão operacional das permissões.


## Experience Alpha v0.2

Consulte `docs/EXPERIENCE_ALPHA.md` para a Mission Entry Surface, Advisor, Impact Chain, Mission Map, Timeline e Guided Reasoning Alpha.


## Experience API v0.2

A camada `/api/v1/experience` fornece projeções orientadas à missão para Mission Entry, mapa, impacto, foco, Timeline e Guided Reasoning. Consulte `docs/EXPERIENCE_ALPHA_V0_2.md`.


## Correção v0.2.1

O arranque do frontend normaliza o contrato de `/auth/me`, possui fallback seguro de identidade e inclui testes Node para variantes de resposta. Consulte `docs/EXPERIENCE_ALPHA_V0_2_1.md`.

## Experience Alpha v0.5

O Guided Reasoning é agora persistente. Cada sessão, pergunta e resposta é guardada no backend e auditada. Consulte `docs/EXPERIENCE_ALPHA_V0_4.md`.


## Alpha v0.5 — Guided Reasoning materializado

As sessões concluídas criam objetos reais do domínio e mostram ao utilizador o que foi estruturado. Ver `docs/EXPERIENCE_ALPHA_V0_5.md`.

## Experience Alpha v0.6 — projeções vivas

Ao concluir uma intenção guiada, o SRIS atualiza imediatamente a Situação, o Mapa e o Percurso da missão. Os objetos acabados de criar ficam visíveis sem atualização manual do navegador.

Novo endpoint agregado:

```text
GET /api/v1/experience/missions/{mission_id}/snapshot
```

Consulte `docs/EXPERIENCE_ALPHA_V0_6.md`.


## Proveniência examinável (v0.9)
Toda nova evidência criada pela API exige um registo de proveniência independente. Contributos humanos e não humanos seguem as mesmas regras epistemológicas, mas origens não humanas têm de declarar o modelo ou sistema e a respetiva versão. Estados de proveniência usam `invalidated`, não `refuted`, reservando refutação para pressupostos.
