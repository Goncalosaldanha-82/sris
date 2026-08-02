# ATLAS OS Sprint 2 — Foundation

Este pacote acrescenta:

- autenticação com JWT;
- hashing Argon2;
- utilizadores;
- organizações;
- memberships;
- RBAC;
- modelo unificado de Knowledge Objects;
- auditoria;
- PostgreSQL para produção;
- SQLite para testes e desenvolvimento local;
- API FastAPI única.

## Arranque local

```bash
uvicorn app.atlas_platform.api:app --host 127.0.0.1 --port 8000
```

## Arranque com PostgreSQL

```bash
docker compose -f docker-compose.atlas-foundation.yml up
```

## Limites ainda em aberto

- migrações Alembic;
- refresh tokens;
- convites de utilizadores;
- gestão visual de membros;
- object storage;
- workers;
- GitHub App;
- integração do Orchestrator com esta persistência.
