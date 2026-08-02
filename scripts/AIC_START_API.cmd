@echo off
cd /d C:\Users\barba\Documents\GitHub\sris
uvicorn app.atlas_intelligence_core.api:app --host 127.0.0.1 --port 8791
pause
