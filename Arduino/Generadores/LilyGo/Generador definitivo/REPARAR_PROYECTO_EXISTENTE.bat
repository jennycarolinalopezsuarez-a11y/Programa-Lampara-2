@echo off
set /p PROJECT_PATH=Pegue la ruta completa del proyecto a reparar: 
if "%PROJECT_PATH%"=="" exit /b 1
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0REPARAR_PROYECTO_SDFAT.py" "%PROJECT_PATH%"
) else (
    python "%~dp0REPARAR_PROYECTO_SDFAT.py" "%PROJECT_PATH%"
)
pause
