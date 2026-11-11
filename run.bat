@echo off
rem ReadySet Control Tower in one command on Windows. Needs Python 3.9+ and nothing else.
rem   run.bat          the web page at http://localhost:8010
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul && (set PY=py) || (set PY=python)
if "%~1"=="" (%PY% -m control_tower serve) else (%PY% -m control_tower %*)
