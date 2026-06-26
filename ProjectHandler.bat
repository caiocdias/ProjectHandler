@echo off
setlocal

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Ambiente virtual nao encontrado. Execute setup.bat primeiro.
    exit /b 1
)

call "venv\Scripts\activate.bat"
if errorlevel 1 exit /b %errorlevel%

python run.py

