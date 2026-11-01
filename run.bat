@echo off
rem Runs Benelli Aerialist from source. First run sets up a private Python environment.
cd /d "%~dp0"
where py >nul 2>nul || (echo Python is not installed. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this again. & pause & exit /b 1)
if not exist .venv (
    echo First run: setting up, this takes a minute...
    py -3 -m venv .venv || (pause & exit /b 1)
    .venv\Scripts\python -m pip install --quiet --upgrade pip
    .venv\Scripts\python -m pip install --quiet -r requirements.txt || (pause & exit /b 1)
)
start "" .venv\Scripts\pythonw run.py %*
