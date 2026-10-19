@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Zainstaluj Python 3.12 lub nowszy i dodaj go do PATH.
  pause
  exit /b 1
)
if not exist .env (
  copy .env.example .env >nul
  echo Uzupelnij plik .env wedlug README.md, a potem uruchom ponownie.
  notepad .env
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 (
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m botspoti
set "BOTSPOTI_EXIT=%errorlevel%"
pause
exit /b %BOTSPOTI_EXIT%
