@echo off
cd /d C:\Users\barba\Documents\GitHub\sris

set ATLAS_DATABASE_URL=sqlite+pysqlite:///./.atlas/test/atlas-tests.db
set ATLAS_REPOSITORY_ROOT=.\.atlas\test\repository
set ATLAS_JWT_SECRET=atlas-local-test-secret-change-before-production
set ATLAS_ENV=test

if not exist ".atlas\test" mkdir ".atlas\test"
if not exist ".atlas\test\repository" mkdir ".atlas\test\repository"

python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail

python -m pip install -e ".[test]"
if errorlevel 1 goto :fail

python -c "import app; import app.main; print('ATLAS Core import OK')"
if errorlevel 1 goto :fail

python -m pytest backend/tests/test_alembic_migrations.py
if errorlevel 1 goto :fail

python -m pytest backend/tests/test_atlas_repository_engine.py
if errorlevel 1 goto :fail

python -m pytest backend/tests/test_atlas_platform_workflow.py
if errorlevel 1 goto :fail

python -m alembic heads
if errorlevel 1 goto :fail

echo.
echo ATLAS CORE v1.1 VERIFIED.
pause
exit /b 0

:fail
echo.
echo ATLAS CORE v1.1 VERIFICATION FAILED.
pause
exit /b 1
