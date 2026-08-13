# SRIS — Portefólios e hierarquia de missões v3

## Resultado

O SRIS deixa de tratar uma missão como uma ficha isolada. Uma organização pode
agora criar um **programa de missões**, decompor esse programa em missões e
continuar a decomposição em sub-missões até seis níveis, mantendo em cada nó:

- identidade, objetivo, contexto e pergunta central;
- domínio, prioridade, horizonte e atores envolvidos;
- relação com a missão-mãe e caminho completo no portefólio;
- documento canónico MDL 1.3, revisão, hash e histórico imutável;
- registos epistemológicos, análises e diálogos governados.

Uma relação hierárquica organiza responsabilidade e dependência. Não transforma
automaticamente o objetivo de uma missão-mãe em evidência para as missões-filhas.

## Experiência de utilização

No ecrã **Missões**, perfis `owner`, `admin` e `contributor` podem:

1. selecionar **Nova missão**;
2. criar uma missão autónoma ou um programa;
3. escolher uma missão-mãe existente;
4. abrir uma missão e selecionar **Criar sub-missão**;
5. editar a missão, registando obrigatoriamente o motivo da revisão;
6. abrir a missão no estúdio e executar análise determinística ou diálogo
   governado, sem limitar a inteligência aos casos demonstrativos.

Os restantes perfis podem consultar a arquitetura, os caminhos e os estados de
forma consistente com as suas permissões. A árvore é apresentada com indentação,
tipo, domínio, prioridade, número de sub-missões e estado de revisão.

## Contrato institucional

| Operação | Endpoint | Perfis |
|---|---|---|
| Listar portefólio | `GET /api/organizations/{org}/mission-intelligence/missions` | todos os membros |
| Criar | `POST /api/organizations/{org}/mission-intelligence/missions` | owner, admin, contributor |
| Consultar | `GET /api/organizations/{org}/mission-intelligence/missions/{id}` | todos os membros |
| Rever / mover | `PATCH /api/organizations/{org}/mission-intelligence/missions/{id}` | owner, admin, contributor |
| Analisar | `POST /api/organizations/{org}/mission-intelligence/missions/{code}/analyze` | owner, admin, reviewer, contributor |
| Dialogar | `POST /api/organizations/{org}/mission-intelligence/missions/{code}/interact` | owner, admin, reviewer |

As missões criadas institucionalmente recebem códigos `PRG-###` ou `MIS-###`.
Esta namespace é deliberadamente distinta dos códigos `P-###` e `M-###` do
catálogo público, impedindo que uma criação local oculte um caso demonstrativo.

## Integridade e segurança

- isolamento por organização em todas as leituras e relações;
- rejeição de ciclos e de referências a missões de outra organização;
- profundidade máxima de seis níveis;
- concorrência otimista através de `expected_revision`;
- revisão imutável e evento de auditoria em cada criação ou alteração;
- validação estrita do documento MDL 1.3 e hash SHA-256 do conteúdo;
- texto narrativo inicial marcado como enquadramento, nunca como evidência;
- IA e investigação externa continuam dependentes de autenticação, política da
  organização, orçamento e revisão humana.

## Portefólio demonstrativo para UC/CFE

O catálogo público passa a mostrar uma arquitetura coerente, em vez de três
cartões sem relação:

| Nível | Código | Missão | Função demonstrativa |
|---|---|---|---|
| Programa | `P-001` | Penela Vivo 2035 | enquadrar um portefólio territorial multirriscos |
| Missão-farol | `M-002` | Nascente de Dragos | ligar água, património, ciência e legitimidade institucional |
| Missão | `M-001` | Paisagem Resiliente | reduzir risco de incêndio sem transferir risco para água, solo ou biodiversidade |
| Missão | `M-003` | Corredores Vivos | investigar infraestrutura ecológica e adaptação climática |
| Missão | `M-004` | Capacidade Humana | explorar participação, prontidão e bem-estar sem alegações clínicas |

Os casos `M-002`, `M-003` e `M-004` são **candidatos de investigação e decisão**,
não projetos autorizados nem resultados demonstrados. Essa fronteira é parte da
proposta de valor: o SRIS permite apresentar ambição sem fabricar certeza.

## Migração e operação

A revisão Alembic `20260813_0008` acrescenta à tabela `mi_missions` a relação
`parent_mission_id` e os campos `mission_kind`, `domain`, `priority` e
`sort_order`. O arranque em contentor já executa `alembic upgrade head`; a
migração tem downgrade simétrico para recuperação controlada.

Verificação recomendada antes de promover o build:

```bash
python -m pytest -q
node --test frontend/tests/*.test.js
alembic upgrade head
```
