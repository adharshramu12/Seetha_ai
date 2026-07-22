@echo off
title Seetha AI - Build Distributable
echo ============================================
echo    SEETHA AI - Building customer .exe
echo ============================================
echo.

cd /d "%~dp0"

REM Use the same Python that has the app dependencies installed.
REM Change this path if you build on another machine.
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python

"%PY%" -m pip install --quiet pyinstaller

"%PY%" -m PyInstaller --noconfirm --clean --windowed --name Seetha ^
  --add-data "seetha\assets;seetha\assets" ^
  --add-data "seetha\config.json;seetha" ^
  --hidden-import pyttsx3.drivers ^
  --hidden-import pyttsx3.drivers.sapi5 ^
  --hidden-import comtypes.stream ^
  --hidden-import pystray._win32 ^
  --hidden-import keyboard ^
  --hidden-import winsound ^
  run_seetha.py

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build complete:  dist\Seetha\Seetha.exe
echo.
echo  Ship the WHOLE dist\Seetha folder (zip it,
echo  or wrap it with an installer like Inno
echo  Setup). No .env, no source code included.
echo ============================================
pause
