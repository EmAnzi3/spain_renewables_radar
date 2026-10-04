@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python assente. Eseguire prima la configurazione descritta nel README.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m app.catalunya_inventory
if errorlevel 1 (
    echo Acquisizione non completata. Consultare reports\catalunya_inventory\run_status.json.
    pause
    exit /b 1
)
start "" "reports\catalunya_inventory\index.html"
endlocal
