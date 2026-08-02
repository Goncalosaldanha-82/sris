@echo off
cd /d C:\Users\barba\Documents\GitHub\sris
set /p QUERY=Search AMOS:
python -m app.amos.cli --repo . search "%QUERY%"
pause
