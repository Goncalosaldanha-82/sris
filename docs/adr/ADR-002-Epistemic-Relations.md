# ADR-002 — Epistemic Relations

**Status:** Proposed
**Version:** 0.1
**Date:** 2026-07-31
**Architecture:** SRIS Epistemic Engine (SEE)
**Depends on:** ADR-001 — Meaning Asset

---

## 1. Contexto

O significado institucional não reside apenas nos objetos registados.

Reside sobretudo nas relações entre esses objetos.

Uma observação isolada não explica:

- que hipótese influenciou;
- que evidência a corroborou;
- que decisão ajudou a fundamentar;
- que resultado produziu;
- que aprendizagem permitiu;
- que doutrina veio a limitar ou substituir.

Consequentemente, o SEE não pode tratar relações como simples chaves
estrangeiras, campos auxiliares ou ligações técnicas invisíveis.

As relações epistemológicas têm significado próprio.

Podem ser:

- propostas;
- aceites;
- contestadas;
- limitadas;
- revistas;
- substituídas;
- revogadas;
- temporalmente válidas;
- dependentes de contexto;
- sustentadas por determinada autoridade;
- enfraquecidas por nova evidência.

Por isso, as relações devem ser tratadas como objetos institucionais
de primeira classe.

---

## 2. Decisão

O SEE representa cada relação epistemológica através de um objeto
persistente denominado **Epistemic Relation**.

Uma Epistemic Relation liga dois objetos institucionais:

- um objeto de origem;
- um objeto de destino;

e declara:

- o tipo de relação;
- a direção;
- a explicação;
- a proveniência;
- o contexto;
- a autoridade;
- a validade temporal;
- as limitações;
- o estado de revisão;
- o estatuto epistemológico;
- a versão.

A relação não prova, por si só, que o vínculo declarado é verdadeiro.

Representa que uma determinada ligação foi proposta, aceite, contestada
ou preservada pelo sistema sob condições identificáveis.

---

## 3. Princípio fundamental

> No SEE, uma ligação entre dois objetos não é um detalhe técnico.
> É uma afirmação institucional sobre a relação entre esses objetos.

Exemplo:

```text
EVD-021 SUPPORTS HYP-003

