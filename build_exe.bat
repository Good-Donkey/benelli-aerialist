@echo off
rem Builds a standalone app: dist\BenelliAerialist\BenelliAerialist.exe (no Python needed to run it).
cd /d "%~dp0"
where py >nul 2>nul || (echo Python is not installed. Install it from https://www.python.org/downloads/ and run this again. & pause & exit /b 1)
if not exist .venv py -3 -m venv .venv || (pause & exit /b 1)
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements.txt pyinstaller || (pause & exit /b 1)
.venv\Scripts\pyinstaller --noconfirm --windowed --name "BenelliAerialist" --icon installer\aerialist.ico --add-data "aerialist/assets;aerialist/assets" --add-data "LICENSE;." --add-data "THIRD-PARTY-NOTICES.md;." --exclude-module pymupdf.layout --exclude-module pymupdf4llm --exclude-module onnxruntime --exclude-module networkx run.py || (pause & exit /b 1)
echo.
echo Done. Your app is in: %~dp0dist\BenelliAerialist\BenelliAerialist.exe
explorer "dist\BenelliAerialist"
pause
