"""
Apply these two changes to backend/app/atlas_platform/api.py:

1. Import workflow models before Base.metadata.create_all:
   from . import workflow_models  # noqa: F401

2. Import and include the router:
   from .workflow_api import router as workflow_router
   app.include_router(workflow_router)
"""
