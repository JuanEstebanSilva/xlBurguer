@echo off
title Carniceria San Diego POS
cd /d "%~dp0"

if exist "dist\CarniceriaSanDiego\CarniceriaSanDiego.exe" (
    start "" "dist\CarniceriaSanDiego\CarniceriaSanDiego.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        python main.py
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" main.py
    ) else (
        py main.py
    )
)
