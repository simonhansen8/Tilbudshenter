@echo off
rem Dobbeltklik paa denne fil for at starte Tilbudshenter i din browser.
cd /d "%~dp0"
title Tilbudshenter
where py >nul 2>nul
if errorlevel 1 (
  echo Python blev ikke fundet. Installer Python fra https://www.python.org/downloads/
  pause
  exit /b 1
)
py -c "import tilbudshenter" >nul 2>nul
if errorlevel 1 (
  echo Installerer Tilbudshenter. Det sker kun foerste gang...
  py -m pip install -e .
)
py -m tilbudshenter app
if errorlevel 1 pause
