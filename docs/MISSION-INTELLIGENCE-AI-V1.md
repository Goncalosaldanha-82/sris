# SRIS — Mission Intelligence & AI v1

Estado: implementação preparada para revisão e implantação

Versão da linguagem de missão: MDL 1.3

Versão do motor: `mission-intelligence-deterministic-1.0`

## Decisão de arquitetura

Mission Intelligence não é um texto produzido por um modelo. É uma capacidade
institucional construída sobre um documento canónico, regras determinísticas,
proveniência, versionamento e revisão humana. A IA é uma camada assistiva
opcional e nunca altera a missão canónica.

Princípios invariantes:

- a cadeia é preservada como
  Realidade → Observação → Representação → Informação → Evidência →
  Conhecimento → Compreensão → Decisão → Ação → Resultado → Aprendizagem;
- `Mission Status`, `Mission Trend` e `Decision Confidence` são calculados e
  apresentados separadamente;
- ausência de dados não é convertida em certeza;
- texto livre é contexto declarado e não se torna evidência canónica sem um
  registo com proveniência;
- evidência mantém origem, método e limitações; confiança é um atributo distinto;
- uma saída de IA é provisória, cita IDs canónicos e não constitui evidência,
  decisão nem atribuição causal;
- toda a execução institucional requer revisão humana documentada.

## Fluxo implementado

1. O catálogo governado é convertido para o contrato canónico `sris.mission/1.3`.
2. O snapshot é validado e recebe um hash SHA-256 reproduzível.
3. O motor determinístico calcula estado, tendência, confiança, lacunas,
   pressupostos, alternativas e não-inferências explícitas.
4. Numa sessão institucional, e apenas por opção expressa, a camada OpenAI pode
   acrescentar uma análise estruturada sobre o snapshot e o relatório.
5. O SRIS valida todas as referências da IA contra os IDs canónicos.
6. Snapshot, versão, relatório, proveniência técnica e estado de revisão ficam
   registados; o resultado continua pendente até aprovação ou rejeição humana.
7. Uma chamada de IA institucional só atravessa o gate se existir uma política
   explícita da organização, quota disponível e reserva prévia de custo.

## Superfície API

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/mission-intelligence/status` | Capacidade, versões e disponibilidade da IA |
| `GET` | `/api/mission-intelligence/demo/missions` | Catálogo demonstrativo MDL 1.3 |
| `POST` | `/api/mission-intelligence/demo/missions/{code}/analyze` | Análise determinística pública; nunca consome IA |
| `GET` | `/api/organizations/{org}/mission-intelligence/missions` | Missões canónicas da organização |
| `POST` | `/api/organizations/{org}/mission-intelligence/demo/{code}/analyze` | Execução persistida, com IA opcional |
| `GET` | `/api/organizations/{org}/mission-intelligence/runs/{id}` | Reconstrução auditável da execução |
| `POST` | `/api/organizations/{org}/mission-intelligence/runs/{id}/review` | Aprovação ou rejeição por perfil autorizado |
| `GET` | `/api/organizations/{org}/mission-intelligence/ai-governance` | Política, consumo e saldo mensal |
| `PUT` | `/api/organizations/{org}/mission-intelligence/ai-governance/policy` | Configuração por owner/admin |
| `GET` | `/api/organizations/{org}/mission-intelligence/ai-governance/events` | Ledger auditável das chamadas |

Persistência adicionada por Alembic:

- `mi_missions`: versão corrente de cada missão por organização;
- `mi_mission_revisions`: histórico append-only dos snapshots aceites;
- `mi_intelligence_runs`: inputs, hashes, resultado determinístico, eventual
  advisory de IA, proveniência e revisão humana.
- `mi_ai_organization_policies`: autorização explícita e limites por organização;
- `mi_ai_usage_periods`: consumo e reservas concorrentes por mês UTC;
- `mi_ai_usage_events`: tokens, custo estimado, tarifa e estado de cada chamada.

## Controlo da IA

A camada de IA está desativada por defeito. Só fica disponível quando existem
simultaneamente:

```env
SRIS_AI_ENABLED=true
SRIS_AI_MODEL=gpt-5.6
OPENAI_API_KEY=<segredo no ambiente de implantação>
```

Controlos presentes:

| Risco | Controlo implementado |
|---|---|
| Alucinação ou afirmação sem base | Structured Output validado e referências obrigatórias a IDs canónicos |
| Injeção de instruções no conteúdo | Snapshot tratado explicitamente como dados não confiáveis |
| Contaminação da evidência | Advisory guardado separadamente, com `verification_status=in_review` |
| Decisão automática | A IA não seleciona alternativas; revisão humana é obrigatória |
| Consumo anónimo | IA bloqueada na demonstração pública e sujeita a autenticação/RBAC |
| Custo sem autorização | Política explícita, teto mensal, limites por pedido e reserva anterior à chamada |
| Corrida entre pedidos | Contadores e reservas protegidos por bloqueio transacional da política da organização |
| Falha do fornecedor | Relatório determinístico permanece disponível e a falha fica registada |
| Reprodutibilidade | Hash do snapshot, motor, modelo, prompt e response ID preservados |
| Retenção no fornecedor | Pedido enviado com `store=false` |

## Implantação segura

1. Implantar o código com `SRIS_AI_ENABLED=false`.
2. Definir `ATLAS_ENV=production` e um `ATLAS_JWT_SECRET` aleatório com pelo
   menos 32 bytes. A aplicação recusa arrancar num ambiente Railway sem este
   controlo.
3. Confirmar que a migração `20260808_0003` terminou sem erro.
4. Verificar `/health`: deve responder `status=ok` e `database=ok`.
5. Executar M-001 no modo público e confirmar:
   `requires_attention`, `not_evaluable`, `moderate` e as três lacunas
   principais (pressupostos, restrições e baseline).
6. Criar uma sessão e organização de teste; confirmar versionamento e revisão.
7. Criar uma política organizacional piloto com `enabled=false` e limites baixos.
8. Configurar o segredo OpenAI e ativar globalmente `SRIS_AI_ENABLED=true`.
9. Ativar apenas a política da organização piloto.
10. Executar um smoke test de IA e verificar que as citações correspondem a IDs
   presentes no snapshot antes de abrir a capacidade a utilizadores piloto.

## Resultado da auditoria e dívida explícita

A interface de produção foi verificada nas sete áreas e apresenta uma base visual
coerente. Antes deste trabalho, “Processar análise” apenas mostrava um resultado
pré-escrito no JavaScript e as importações existiam apenas em `localStorage`.
O backend de produção expunha autenticação, organizações, conhecimento e workflow,
mas não tinha Mission Intelligence, persistência de missões nem análise real.

Esta versão corrige o percurso demonstrativo e institucional das três missões do
catálogo. Permanecem deliberadamente fora deste incremento:

- transformar pacotes importados localmente em missões institucionais canónicas;
- edição completa de relações entre objetos da cadeia;
- comparação temporal necessária para calcular `Mission Trend`;
- painel visual para gestão de quotas (a API e o ledger já estão implementados);
- remoção de `unsafe-inline` da CSP, dependente de extrair o JavaScript/CSS do
  ficheiro HTML único;
- teste real ao fornecedor OpenAI, que exige chave e ambiente autorizados.

Os testes `test_enterprise.py` são mantidos, mas marcados como especificação
legada: exercitam a antiga API `/api/v1`, desligada da aplicação de produção na
consolidação ATLAS Core. Não devem ser interpretados como cobertura do runtime
atual até existir uma decisão explícita de convergência ou retirada.
