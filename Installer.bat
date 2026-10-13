@echo off
rem Dobbeltklik paa denne fil EN gang for at installere Tilbudshenter.
rem Bagefter starter du programmet fra genvejen paa skrivebordet eller i
rem Start-menuen, og det henter selv nye udgaver fra GitHub.
cd /d "%~dp0"
title Installer Tilbudshenter
where py >nul 2>nul
if errorlevel 1 (
  echo Python blev ikke fundet. Installer Python fra https://www.python.org/downloads/
  pause
  exit /b 1
)
py -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if errorlevel 1 (
  echo Tilbudshenter kraever Python 3.11 eller nyere. Installer det fra https://www.python.org/downloads/
  pause
  exit /b 1
)
py "%~dp0src\tilbudshenter\updater.py" installer "%~dp0."
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Tryk paa en tast for at starte Tilbudshenter.
pause >nul
start "" "%LOCALAPPDATA%\Tilbudshenter\Tilbudshenter.bat"
