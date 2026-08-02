# Sprint 2 — Bloco 3: Alembic e Migrações Oficiais

Este bloco substitui a criação automática de tabelas em produção por migrações versionadas.

## Inclui

- `alembic.ini`;
- ambiente Alembic ligado ao metadata SQLAlchemy;
- leitura de `ATLAS_DATABASE_URL`;
- migração inicial integral;
- upgrade e downgrade;
- scripts Windows;
- teste automático de migração;
- workflow GitHub.

## Comandos

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic history
python -m alembic downgrade -1
```

## Regra de produção

Remover de `backend/app/atlas_platform/api.py`:

```python
Base.metadata.create_all(bind=engine)
```

A API não deve alterar o esquema ao arrancar. O deploy executa primeiro:

```bash
python -m alembic upgrade head
```

e só depois inicia a aplicação.

## Nova alteração de modelos

Depois de alterar modelos SQLAlchemy:

```bash
python -m alembic revision --autogenerate -m "describe change"
```

A migração gerada deve ser revista manualmente antes do commit.
