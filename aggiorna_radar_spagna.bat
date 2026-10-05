@echo off
setlocal
cd /d "%~dp0"
set "PY=.\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERRORE: ambiente .venv non trovato.
  echo Esegui: py -m venv .venv
  echo         .\.venv\Scripts\pip.exe install -r requirements.txt
  pause
  exit /b 1
)
if not exist "data" mkdir data
if not exist "reports\change_reports" mkdir reports\change_reports
if not exist "docs" mkdir docs

echo ==========================================================
echo Spain Renewables Radar - fonti ufficiali - ultimi 7 giorni
echo ==========================================================
"%PY%" -m app.run_pipeline --days 7
if errorlevel 1 (
  echo ERRORE pipeline.
  pause
  exit /b 1
)
echo.
echo OK. Apri reports\change_reports\changes_latest.html
pause
