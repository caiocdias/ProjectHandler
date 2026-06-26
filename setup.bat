@echo off
setlocal

cd /d "%~dp0"

python -m venv venv
if errorlevel 1 exit /b %errorlevel%

call "venv\Scripts\activate.bat"
if errorlevel 1 exit /b %errorlevel%

python -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%

python -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

echo.
echo Ambiente configurado com sucesso.
echo Para iniciar o programa, execute ProjectHandler.bat.

