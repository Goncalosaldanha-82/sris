# MISSION-000 — Determinar a Unidade Atómica do SRIS

**Tipo:** Missão de investigação ontológica
**Estado:** Ativa
**Versão:** 0.1
**Data:** 2026-08-01
**Programa:** Project ATLAS
**Quadro teórico:** TICC
**Implementação experimental:** SRIS

---

## 1. Advertência epistemológica

Esta missão investiga uma questão ontológica ainda não resolvida.

Não existe, nesta fase, evidência suficiente para afirmar que `Meaning
Asset`, `Claim`, `Observation`, `Event` ou qualquer outro candidato
constitui a unidade fundamental do SRIS.

> **Hipótese não validada. Nenhuma evidência empírica produzida.**

---

## 2. Problema

A arquitetura atual do SRIS utiliza conceitos como:

- Observation;
- Source Claim;
- Evidence;
- Hypothesis;
- Investigation;
- Decision;
- Outcome;
- Learning;
- Knowledge;
- Doctrine;
- Meaning Asset.

Contudo, ainda não foi demonstrado qual é a menor unidade conceptual
necessária para preservar conhecimento institucional de forma:

- contextualizada;
- atribuída;
- proveniente;
- auditável;
- revisável;
- temporal;
- relacionada com missões;
- independente da implementação técnica.

Escolher prematuramente uma unidade atómica poderá contaminar:

- a ontologia;
- a base de dados;
- o grafo;
- os contratos;
- as APIs;
- a interface;
- o Reasoning Engine;
- a Inteligência Externa;
- a representação de autoridade e proveniência.

---

## 3. Questão principal

> **Qual é a menor entidade capaz de manter identidade própria,
> proveniência, contexto, estado epistémico, relações de
> suporte/contradição e relevância missionária?**

---

## 4. Hipótese de trabalho

A unidade mínima poderá não ser um documento, dado ou ativo agregado.

Uma hipótese inicial é:

> **A unidade atómica poderá ser uma asserção contextualizada e
> atribuída: algo que um ator, fonte, sensor ou sistema afirmou,
> observou, inferiu, decidiu ou registou, num determinado contexto,
> momento e âmbito de autoridade.**

Esta formulação é provisória e deve ser refutada.

---

## 5. Candidatos

### 5.1. Dado

**Forças**

- simples;
- computável;
- facilmente armazenável;
- adequado para medições brutas.

**Limitações**

- não contém significado institucional;
- pode não possuir interpretação;
- não contém necessariamente autoria, finalidade ou justificação;
- não participa sozinho num raciocínio.

---

### 5.2. Documento

**Forças**

- preserva contexto parcial;
- pode manter estrutura, autoria e data;
- corresponde a objetos institucionais reconhecíveis.

**Limitações**

- demasiado agregado;
- pode conter afirmações incompatíveis;
- pode combinar factos, opiniões, previsões e citações;
- não constitui unidade mínima de raciocínio.

---

### 5.3. Evento

**Forças**

- preserva temporalidade;
- adequado a event sourcing;
- representa ocorrência ou alteração.

**Limitações**

- um evento não representa necessariamente significado;
- não distingue observação, interpretação e justificação;
- pode não possuir conteúdo proposicional.

---

### 5.4. Observação

**Forças**

- liga o sistema ao mundo observado;
- preserva tempo, contexto e observador;
- pode iniciar uma investigação.

**Limitações**

- não abrange decisões, normas ou inferências;
- pode já conter interpretação;
- não é necessariamente unidade universal.

---

### 5.5. Claim / Asserção

**Forças**

- pode ser atribuída;
- pode ser contestada;
- pode ser corroborada;
- possui conteúdo proposicional;
- pode participar em raciocínio.

**Limitações**

- pode perder contexto operacional;
- nem todos os objetos institucionais são proposições;
- uma decisão não é apenas uma afirmação;
- pode ser insuficiente para representar eventos ou ações.

---

### 5.6. Evidence

**Forças**

- possui relevância justificativa;
- liga-se diretamente a hipóteses e decisões;
- exige âmbito e avaliação.

**Limitações**

- já pressupõe uma relação com algo que pretende sustentar;
- não existe como estatuto absoluto;
- não representa informação ainda não aceite.

---

### 5.7. Meaning Asset

**Forças**

- pretende unificar objetos que transportam significado;
- permite identidade, contexto, proveniência e lifecycle;
- suporta múltiplos tipos epistemológicos.

**Limitações**

- ainda não possui definição não circular;
- pode tornar-se excessivamente abrangente;
- pode misturar objetos epistemológicos, decisórios e administrativos;
- ainda não foi demonstrado que seja indivisível.

---

### 5.8. Decisão

**Forças**

- central à memória institucional;
- possui autoridade, contexto e consequência;
- liga raciocínio a execução.

**Limitações**

- é resultado de um percurso;
- não é unidade geral de conhecimento;
- depende de objetos anteriores.

---

## 6. Critérios de avaliação

Um candidato só poderá ser aceite como unidade atómica se conseguir:

1. existir com identidade persistente;
2. possuir origem identificável ou explicitamente desconhecida;
3. preservar contexto temporal, espacial, organizacional e missionário;
4. ser atribuído a ator, fonte, sensor ou sistema;
5. possuir estado epistémico;
6. ser confirmado, contestado, limitado, revogado ou arquivado;
7. participar numa cadeia de raciocínio;
8. relacionar-se com outros objetos sem perder identidade;
9. existir independentemente da sua representação técnica;
10. respeitar autoridade, privacidade, classificação e acesso;
11. manter histórico e versão;
12. distinguir conteúdo, interpretação e utilização;
13. suportar relações de apoio, contradição, dependência e derivação;
14. permitir reconstrução futura;
15. ser aplicável em múltiplos domínios institucionais.

---

## 7. Testes de refutação

### Universalidade

O candidato consegue representar adequadamente:

- uma medição de sensor;
- um testemunho;
- uma afirmação científica;
- uma decisão administrativa;
- uma regra;
- uma aprendizagem;
- uma ordem operacional;
- uma contradição?

Se não, pode não ser unidade fundamental.

### Indivisibilidade

O candidato pode ser dividido em objetos menores que conservam
identidade, proveniência e participação no raciocínio?

Se sim, poderá não ser atómico.

### Independência técnica

A definição continua válida fora de:

- SQL;
- grafos;
- Python;
- APIs;
- documentos;
- modelos de linguagem?

Se não, é uma unidade de implementação e não uma unidade ontológica.

### Não circularidade

O candidato consegue ser definido sem utilizar o próprio conceito ou
sinónimos vagos?

### Distinção entre existência e estatuto

O objeto continua a existir quando muda de:

- observado;
- candidato;
- aceite;
- contestado;
- revogado?

### Adequação institucional

O candidato permite preservar:

- autoria;
- responsabilidade;
- autoridade;
- delegação;
- contexto;
- finalidade;
- limitações;
- revisão?

---

## 8. Hipótese alternativa de três níveis

A investigação poderá concluir que não existe um único átomo universal.

Uma estrutura alternativa é:

```text
Sinal / ocorrência
↓
Asserção contextualizada e atribuída
↓
Interpretação ou ativo de significado
