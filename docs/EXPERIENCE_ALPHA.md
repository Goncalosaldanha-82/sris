# SRIS Enterprise Experience Alpha

Primeira fatia vertical do SEES implementada sobre o backend Enterprise Pilot.

## Incluído

- Mission Entry Surface, sem dashboard de KPI.
- Navegação por cinco intenções: Compreender, Investigar, Decidir, Rever e Aprender.
- SRIS Advisor baseado nas regras devolvidas por `/api/v1/reasoning-audit`.
- Focus Surface para qualquer objeto do grafo.
- Impact Chain navegável através das relações existentes.
- Mission Map relacional com alternativa textual.
- Timeline Lógica inicial.
- Guided Reasoning Alpha para validar linguagem e fluxo.
- Experiência móvel sequencial.

## Limites declarados

- O Guided Reasoning Alpha ainda preserva respostas apenas na sessão da interface; a persistência versionada exige os endpoints de sessão previstos no SEES.
- A Timeline atual é uma projeção lógica do estado existente; o modo bitemporal completo ainda não foi implementado.
- O mapa utiliza as relações atuais do backend e não infere causalidade.

## Fluxo de demonstração

1. Entrar.
2. Selecionar M-001.
3. Ler a situação da missão.
4. Abrir um ponto de atenção.
5. Seguir a cadeia de impacto.
6. Abrir o Mapa da Missão.
7. Ver o Percurso.
8. Iniciar uma das cinco intenções.
