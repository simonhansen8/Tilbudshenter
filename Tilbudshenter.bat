@echo off
rem Dobbeltklik paa denne fil for at starte Tilbudshenter i din browser.
rem Programmet koeres direkte fra mappen her, saa en aeldre installeret
rem udgave af tilbudshenter ikke kan komme i vejen.
cd /d "%~dp0"
title Tilbudshenter
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
set "PYTHONPATH=%~dp0src"
py -m tilbudshenter app
if errorlevel 1 pause
