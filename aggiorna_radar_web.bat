@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python non configurato. Seguire il README.
  exit /b 1
)
.venv\Scripts\python.exe -m app.operational --days 7
set "RESULT=%ERRORLEVEL%"
if not exist "reports\operational\latest.json" exit /b %RESULT%
.venv\Scripts\python.exe -m app.bocyl_storage --db data/spain_renewables.sqlite
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m app.web_portal --db data/spain_renewables.sqlite --status reports/operational/latest.json --output site
if errorlevel 1 exit /b 1
start "" "%cd%\site\index.html"
if not "%RESULT%"=="0" echo Aggiornamento fallito: la pagina mostra i dati precedenti e la causa registrata.
exit /b %RESULT%
