# Alteração obrigatória em `backend/app/atlas_platform/api.py`

Eliminar:

```python
Base.metadata.create_all(bind=engine)
```

Também deixa de ser necessário importar `engine` apenas para executar `create_all`.

A criação e atualização do esquema passa exclusivamente por Alembic.
