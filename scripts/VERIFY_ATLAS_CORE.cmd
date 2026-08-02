@echo off
cd /d C:\Users\barba\Documents\GitHub\sris
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto fail
python -m pip install -e ".[test]"
if errorlevel 1 goto fail
python -c "import app; import app.main; print('ATLAS Core import OK')"
if errorlevel 1 goto fail
python -m pytest backend/tests/test_alembic_migrations.py
if errorlevel 1 goto fail
python -m pytest backend/tests/test_atlas_repository_engine.py
if errorlevel 1 goto fail
python -m pytest backend/tests/test_atlas_platform_workflow.py
if errorlevel 1 goto fail
echo ATLAS CORE v1.0 VERIFIED SUCCESSFULLY.
pause
exit /b 0
:fail
echo ATLAS CORE VERIFICATION FAILED.
pause
exit /b 1
