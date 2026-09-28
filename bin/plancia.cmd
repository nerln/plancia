@echo off
setlocal
set "PLANCIA_PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PLANCIA_PY=py -3"
)
if defined PLANCIA_PY goto :avvia
where python >nul 2>nul
if errorlevel 1 goto :senzapython
python -c "import sys" >nul 2>nul
if errorlevel 1 goto :senzapython
set "PLANCIA_PY=python"
:avvia
%PLANCIA_PY% -X utf8 "%~dp0plancia" %*
exit /b %errorlevel%
:senzapython
echo plancia: non trovo un Python 3 che funzioni (ne "py -3" ne "python", l alias del Microsoft Store non conta). Installalo da python.org o con: winget install Python.Python.3.12 1>&2
exit /b 9009
