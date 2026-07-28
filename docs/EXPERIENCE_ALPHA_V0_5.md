# SRIS Enterprise Experience Alpha v0.5

## Incremento entregue

O Guided Reasoning deixou de guardar apenas respostas. Quando uma sessão é concluída, o backend transforma as respostas confirmadas em objetos reais e auditáveis do domínio SRIS.

### Mapeamentos implementados

- **Compreender** → `Observation`
- **Investigar** → `Investigation`, hipóteses concorrentes e `EvidenceProposal`
- **Decidir** → `Decision` e `Alternative`
- **Rever** → observação de revisão, sem alterar automaticamente decisões anteriores
- **Aprender** → `Learning` com não-conclusões e condições de reutilização preservadas

Cada objeto criado:

- pertence à organização e missão corretas;
- mantém ligação à sessão guiada através de relações tipadas;
- gera registo de auditoria;
- inclui limitações explícitas;
- é criado por regras determinísticas, sem inferência generativa.

## Integridade

- A materialização ocorre apenas após a última resposta.
- A leitura posterior da sessão não duplica objetos.
- Hipóteses concorrentes recebem priors normalizados.
- Uma possível evidência contrária é registada como proposta de recolha, não como evidência já confirmada.
- Uma revisão humana não reescreve automaticamente a decisão histórica.

## Testes

A suite inclui testes específicos para:

- criação de observação;
- criação de investigação, hipóteses e proposta de evidência;
- criação de decisão e alternativas;
- idempotência da materialização.
