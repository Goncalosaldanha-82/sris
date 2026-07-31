# ADR-001 — Meaning Asset

**Status:** Proposed
**Version:** 0.1
**Date:** 2026-07-31
**Architecture:** SRIS Epistemic Engine (SEE)

---

## 1. Contexto

A maioria dos sistemas de informação utiliza documentos, ficheiros,
registos ou tabelas como unidades fundamentais.

Essa abordagem é insuficiente para o SRIS.

Um único documento pode conter:

- afirmações factuais;
- opiniões;
- interpretações;
- previsões;
- contradições;
- evidência;
- pressupostos;
- referências a terceiros.

Cada elemento pode possuir proveniência, autoridade, validade temporal,
limitações e estatuto epistemológico diferentes.

Consequentemente, o documento não pode ser a unidade fundamental do
SRIS Epistemic Engine.

---

## 2. Decisão

A unidade fundamental de significado do SEE é o **Meaning Asset**.

Um Meaning Asset é um objeto institucional que participa num processo
de observação, investigação, fundamentação, decisão, avaliação,
aprendizagem ou doutrina.

O Meaning Asset não representa verdade absoluta.

Representa o significado institucional atribuído a determinada
informação:

- num contexto definido;
- num momento definido;
- por uma autoridade identificada;
- com proveniência conhecida;
- com limitações explícitas;
- sob um determinado estatuto epistemológico.

---

## 3. Tipos iniciais

O SEE reconhece inicialmente os seguintes tipos de Meaning Asset:

- Source Claim;
- Observation;
- Evidence Candidate;
- Evidence;
- Hypothesis;
- Investigation;
- Assumption;
- Alternative;
- Decision;
- Implementation;
- Outcome;
- Learning;
- Knowledge;
- Doctrine Proposal;
- Doctrine.

Os tipos representam funções epistemológicas diferentes.

Uma Observation não se transforma automaticamente em Evidence.

Quando necessário, são criados objetos distintos e ligados através de
relações explícitas, auditáveis e contextualizadas.

---

## 4. Propriedades mínimas

Todo o Meaning Asset deve possuir:

- identidade persistente;
- organização;
- missão;
- tipo;
- título;
- afirmação ou conteúdo significativo;
- data de criação;
- autor ou origem;
- proveniência;
- contexto;
- estatuto epistemológico;
- limitações;
- âmbito de utilização;
- validade temporal;
- autoridade;
- estado de revisão;
- versão.

---

## 5. Identidade e preservação histórica

A identidade de um Meaning Asset permanece estável durante o seu ciclo
de vida.

Uma alteração de estatuto não cria retroativamente uma nova realidade
nem apaga o estado anterior.

Um Meaning Asset pode tornar-se:

- aceite;
- contestado;
- limitado;
- substituído;
- revogado;
- arquivado.

O histórico das transições deve permanecer preservado.

---

## 6. Relações

Os Meaning Assets adquirem significado através das relações que mantêm
com outros objetos institucionais.

Exemplos de relações:

- supports;
- contradicts;
- qualifies;
- derives_from;
- depends_on;
- triggers;
- implemented_by;
- produces;
- supersedes;
- limits;
- invalidates;
- requires_review.

As relações são objetos de primeira classe.

Cada relação deve poder conservar:

- origem;
- destino;
- tipo;
- explicação;
- proveniência;
- contexto;
- limitações;
- validade temporal;
- autor ou autoridade;
- estado de revisão.

---

## 7. Invariantes

A implementação deve respeitar, pelo menos, os seguintes invariantes:

1. Nenhum Meaning Asset representa verdade absoluta.
2. Todo o Meaning Asset possui proveniência registada ou explicitamente
declarada como ainda desconhecida.
3. A força de uma conclusão não pode exceder a força da evidência que a
sustenta.
4. Uma alteração de estatuto não altera silenciosamente o histórico.
5. Uma revogação não elimina o objeto revogado.
6. Uma relação epistemológica deve possuir explicação.
7. A aceitação institucional exige autoridade identificável.
8. A IA pode propor ou avaliar, mas não constitui autoridade
institucional por si própria.
9. Alterações metodológicas devem ser versionadas.
10. As limitações conhecidas devem permanecer associadas ao ativo.

---

## 8. Consequências

### Consequências positivas

- unidade ontológica coerente;
- rastreabilidade transversal;
- preservação histórica;
- representação explícita da incerteza;
- relações auditáveis;
- extensibilidade para diferentes domínios;
- separação entre informação, evidência e decisão;
- compatibilidade com agentes de inteligência artificial governados.

### Custos e restrições

- maior complexidade de modelação;
- necessidade de governação de estados;
- necessidade de proveniência estruturada;
- necessidade de auditoria append-only;
- maior disciplina na criação de objetos e relações;
- impossibilidade de tratar documentos externos como verdade automática.

---

## 9. Princípio fundamental

> O SEE não transforma informação em verdade.
> Governa o percurso pelo qual uma organização atribui significado,
> validade, autoridade, âmbito e limitações à informação que utiliza.

---

## 10. Estado da decisão

Este ADR encontra-se em estado **Proposed**.

A passagem para **Accepted** depende de:

- revisão dos contratos Python existentes;
- validação dos testes do lifecycle;
- definição do modelo de proveniência;
- definição dos invariantes iniciais;
- confirmação de compatibilidade com o modelo de dados atual.
