@echo off
cd /d C:\Users\barba\Documents\GitHub\sris
start "ATLAS OS API" cmd /k uvicorn app.atlas_os.api:app --host 127.0.0.1 --port 8792
timeout /t 3 >nul
start "" "frontend\atlas-os\index.html"
