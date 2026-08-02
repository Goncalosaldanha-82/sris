# Sprint 2 — Bloco 2: Workflow Integration

Este bloco elimina a persistência separada do Orchestrator e integra o fluxo operacional na base comum da plataforma.

## Inclui

- workflows ligados a organizações e utilizadores;
- candidatos de conhecimento persistidos;
- histórico de estados;
- revisão humana por RBAC;
- materialização em `KnowledgeObject`;
- geração de ficheiros Markdown;
- proposta de branch, commit, paths e diff;
- auditoria;
- Review Center autenticado.

## Alteração necessária em `api.py`

Aplicar o conteúdo indicado em:

```text
backend/app/atlas_platform/api_patch.py
```

O próximo bloco deve acrescentar Alembic e migrações oficiais, removendo `Base.metadata.create_all` como mecanismo de produção.
