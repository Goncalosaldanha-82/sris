# Guia de teste da SRIS Enterprise Pilot Release

## Objetivo do teste

O primeiro teste deve verificar se uma pessoa externa consegue reconstruir uma decisão, perceber a incerteza existente e identificar que informação falta recolher sem explicação prévia do autor.

## Preparação

1. Subir a aplicação com Docker Compose.
2. Criar o administrador e a organização piloto.
3. Executar `seed_demo`.
4. Entrar no navegador e abrir a missão M-001.

## Percurso recomendado

1. Abrir **Missões** e selecionar M-001.
2. Clicar nos nós do grafo e percorrer a proveniência.
3. Confirmar que as probabilidades das hipóteses concorrentes somam 1.
4. Ler **Para distinguir, falta recolher** e verificar a prioridade dos testes propostos.
5. Abrir o pressuposto refutado e observar a relação de refutação.
6. Consultar a auditoria do raciocínio.
7. Selecionar um resultado e executar a avaliação de atribuição.
8. Confirmar que o veredicto distingue sequência temporal de causalidade.
9. Criar uma nova aprendizagem e registar a sua reutilização noutra missão.
10. Tentar criar uma observação sem limitação declarada e confirmar que a API recusa com uma mensagem útil.

## Perguntas ao utilizador-teste

- O que aconteceu nesta missão?
- Que hipótese está atualmente mais sustentada e porquê?
- Que informação falta recolher para distinguir melhor as hipóteses?
- Que pressuposto foi refutado?
- O resultado pode ser atribuído à intervenção?
- O que foi aprendido e onde foi reutilizado?
- Em que ponto se sentiu perdido?
- Que ação esperava encontrar e não encontrou?

## Critérios mínimos de aprovação

- O utilizador completa o percurso sem ajuda técnica.
- Consegue explicar a diferença entre observação, evidência e hipótese.
- Percebe que os valores posteriores são relativos entre hipóteses concorrentes.
- Percebe por que razão a atribuição pode não estar sustentada.
- Não encontra erros 500, estados bloqueados ou formulários ambíguos.
- O trabalho persiste depois de terminar sessão e voltar a entrar.

## Registo de problemas

Para cada problema, registar:

- data e hora;
- utilizador e função;
- missão e objeto;
- ação executada;
- resultado esperado;
- resultado observado;
- captura de ecrã;
- `X-Request-ID` devolvido pela API;
- gravidade: bloqueante, alta, média ou baixa.
