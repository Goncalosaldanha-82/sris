@echo off
cd /d C:\Users\barba\Documents\GitHub\sris

python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail

python -m pip install -e ".[test]"
if errorlevel 1 goto :fail

python -c "import app; print('ATLAS package import OK')"
if errorlevel 1 goto :fail

python -m pytest backend/tests/test_alembic_migrations.py
if errorlevel 1 goto :fail

echo.
echo ATLAS package architecture verified successfully.
pause
exit /b 0

:fail
echo.
echo Verification failed. Review the error above.
pause
exit /b 1
