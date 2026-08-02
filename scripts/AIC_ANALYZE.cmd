@echo off
cd /d C:\Users\barba\Documents\GitHub\sris
python -m app.amos.cli --repo . bootstrap
python -m app.atlas_intelligence_core.cli --repo . analyze --no-refresh
pause
