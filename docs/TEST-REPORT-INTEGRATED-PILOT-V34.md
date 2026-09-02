# Test Report — SRIS Integrated Pilot v34

## Âmbito

Validação do build `20260901-integrated-pilot-platform-v34` no ramo `pilot-v1-september-2026`.

A validação não usa nem promove dados demonstrativos para o staging público. Bases locais descartáveis são criadas do zero para cada percurso.

## Verificações automatizadas

- importação integral da aplicação;
- compilação Python;
- migração limpa desde a primeira revisão até `20260901_0024`;
- um único head Alembic;
- sintaxe dos módulos JavaScript;
- contratos do frontend;
- criação e revisão de piloto;
- perfis e modelos setoriais;
- Data Readiness;
- métricas, baseline, objetivo e resultado;
- controlo de concorrência por revisão;
- Value Case e prova obrigatória para valor realizado;
- papéis formais do piloto;
- report suite;
- identidade, convite e recuperação;
- contrato Pilot V1;
- Mission Intelligence;
- Business Case vivo;
- aprendizagem e herança;
- memória de longo prazo.

## Percurso browser end-to-end

Executado num browser Chromium sobre servidor e base de dados descartáveis:

1. abrir página pública;
2. criar workspace piloto;
3. entrar na aplicação;
4. confirmar estado vazio;
5. criar piloto Hospitality com origem Tourism Advance;
6. preencher problema, decisão, objetivo, critério de sucesso, suspensão, intervenção, recursos, riscos, reversibilidade e privacidade;
7. registar baseline, objetivo e resultado;
8. criar missão diretamente dentro do piloto;
9. confirmar pré-preenchimento;
10. guardar missão;
11. confirmar ligação automática ao piloto;
12. registar valor realizado com período, baseline, fonte, cálculo e atribuição;
13. formalizar mentor de programa sem autoridade de decisão;
14. exportar dossier completo;
15. registar recomendação de adaptação antes de escala.

## Smoke público

Verificações sem criação de dados no staging:

- `/health`;
- `/api/pilot/build`;
- `/api/pilot/capabilities`;
- build v34;
- cinco momentos;
- oito registos canónicos;
- Pilot Charter;
- Value Case;
- report suite;
- criação direta de missão.

## Isolamento

Foram verificados separadamente:

- `www.sris.io`;
- site Railway institucional;
- `sris-production`;
- `sris-pilot-v1-staging`.

O identificador do build integrado é exclusivo do serviço piloto.

## Limites desta aceitação

A validação automatizada e browser não substitui:

- iPhone físico;
- Android físico;
- entrega real de email;
- fornecedor de IA real;
- backup e restauro do PostgreSQL do Railway;
- teste externo de segurança;
- missão executada por um parceiro independente.

Esses pontos permanecem gates operacionais e não são apresentados como concluídos.
