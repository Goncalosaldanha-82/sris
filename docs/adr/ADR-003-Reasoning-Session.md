# ADR-003 — Reasoning Session

**Status:** Proposed
**Version:** 0.1
**Date:** 2026-07-31
**Architecture:** SRIS Epistemic Engine (SEE)
**Depends on:** ADR-001 — Meaning Asset
**Depends on:** ADR-002 — Epistemic Relations

---

# 1. Contexto

As decisões institucionais não surgem de forma instantânea.

Resultam de um processo contínuo de observação, recolha de evidência,
formulação de hipóteses, investigação, revisão, decisão e aprendizagem.

Nos sistemas tradicionais estes elementos encontram-se dispersos por
tabelas, documentos, emails, processos administrativos e aplicações
independentes.

O raciocínio deixa de ser reconstruível.

O SEE pretende preservar não apenas os objetos produzidos, mas todo o
processo intelectual que lhes deu origem.

---

# 2. Decisão

O SEE introduz uma entidade institucional denominada:

**Reasoning Session**

Uma Reasoning Session representa um processo completo de raciocínio
institucional.

É o recipiente onde todo o processo epistemológico decorre.

Todos os objetos produzidos durante uma decisão pertencem a uma sessão.

---

# 3. Princípio Fundamental

> Uma decisão nunca existe isoladamente.

Toda a decisão pertence a uma sessão de raciocínio claramente
identificável.

---

# 4. Objetivos

Uma Reasoning Session deve permitir:

- preservar contexto;
- preservar sequência lógica;
- preservar revisão;
- preservar autoridade;
- preservar conflitos;
- preservar alternativas rejeitadas;
- preservar aprendizagem;
- preservar doutrina aplicada;
- permitir reconstrução integral do raciocínio.

---

# 5. Estrutura Geral

Cada sessão possui identidade própria.

Exemplo:

RS-2026-000184

A sessão agrega:

- missão;
- organização;
- objetivo;
- âmbito;
- participantes;
- contexto;
- restrições;
- observações;
- evidências;
- hipóteses;
- investigações;
- decisões;
- resultados;
- aprendizagens;
- doutrina;
- revisões.

---

# 6. Questão Inicial

Toda a sessão inicia-se com uma questão explícita.

Exemplos:

- Devemos aprovar este investimento?
- Existe risco operacional?
- Qual a melhor intervenção?
- Esta hipótese é plausível?

O SEE nunca inicia uma sessão sem uma questão identificável.

---

# 7. Evolução

Durante a sessão podem surgir:

novas observações;

novas evidências;

novas hipóteses;

novas investigações;

novas revisões;

novos participantes;

novas decisões.

Nada substitui automaticamente o histórico.

---

# 8. Estados

Uma sessão poderá assumir estados como:

Draft

Active

Waiting Evidence

Waiting Investigation

Waiting Review

Decision Ready

Completed

Suspended

Appealed

Archived

Cada alteração gera evento auditável.

---

# 9. Contexto

O contexto da sessão inclui:

tempo;

espaço;

missão;

organização;

domínio;

restrições;

objetivos;

atores;

fontes;

versão metodológica.

---

# 10. Participantes

Uma sessão pode possuir:

autor;

investigadores;

revisores;

especialistas;

decisores;

IA;

sensores;

fontes externas.

Todos permanecem identificados.

---

# 11. Objetos

A sessão não duplica objetos.

Apenas referencia:

Observations

Evidence

Hypotheses

Investigations

Decisions

Outcomes

Learnings

Doctrine

Relations

Todos permanecem independentes.

---

# 12. Linha Temporal

Toda a sessão preserva cronologia completa.

Exemplo:

Observação

↓

Evidência

↓

Hipótese

↓

Investigação

↓

Revisão

↓

Decisão

↓

Resultado

↓

Aprendizagem

↓

Doutrina

---

# 13. Revisão

Qualquer elemento pode ser revisto.

A revisão nunca elimina:

hipóteses rejeitadas;

decisões antigas;

evidências ultrapassadas;

investigações encerradas.

Tudo permanece reconstruível.

---

# 14. Sessões Longas

Uma sessão pode durar:

minutos;

dias;

meses;

anos.

A identidade permanece constante.

---

# 15. Sessões Encadeadas

Uma sessão pode originar novas sessões.

Exemplo:

Sessão de auditoria

↓

gera

↓

Sessão disciplinar

↓

gera

↓

Sessão jurídica

A relação entre sessões permanece explícita.

---

# 16. IA

Uma IA pode participar.

Nunca pode substituir automaticamente:

autoridade;

aprovação;

responsabilidade.

As suas contribuições permanecem identificadas.

---

# 17. Reconstrução

O SEE deve conseguir responder:

Porque foi tomada esta decisão?

Que alternativas existiam?

Quem participou?

Que evidências existiam?

Quem discordou?

Que regra metodológica foi utilizada?

Que doutrina estava em vigor?

---

# 18. Invariantes

1. Toda a sessão possui identidade persistente.

2. Toda a sessão possui questão inicial.

3. Toda a decisão pertence a uma sessão.

4. Nenhum objeto perde ligação à sessão.

5. A cronologia é preservada.

6. Revisões nunca apagam histórico.

7. Participantes permanecem identificados.

8. IA permanece identificada.

9. Autoridade permanece identificável.

10. Toda a sessão possui estado.

11. Toda a sessão possui contexto.

12. A sessão nunca altera diretamente objetos históricos.

13. Sessões podem originar sessões.

14. A sessão preserva cadeia de raciocínio completa.

15. A sessão pode ser auditada integralmente.

---

# 19. Benefícios

- reconstrução completa;

- auditabilidade;

- transparência;

- aprendizagem organizacional;

- memória institucional;

- explicabilidade;

- rastreabilidade;

- reutilização de conhecimento;

- suporte ao Mission Intelligence.

---

# 20. Consequência Arquitetural

O Reasoning Engine não opera diretamente sobre objetos isolados.

Opera sempre dentro de uma Reasoning Session.

A sessão torna-se a unidade fundamental de raciocínio do SEE.

---

# 21. Estado

Proposed

A implementação apenas começará após validação da arquitetura do
Reasoning Engine.
