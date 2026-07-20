@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "Minerguard_TEcho_Generador_V6_GPS_AUTO_PLATFORMIO.py"
) else (
    python "Minerguard_TEcho_Generador_V6_GPS_AUTO_PLATFORMIO.py"
)
if errorlevel 1 pause
