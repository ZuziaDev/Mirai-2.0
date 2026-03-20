@echo off
title MIRAI — Neural Link
echo 💠 MIRAI NEURAL ENGINE IGNITING...
echo --------------------------------------------------

:: Try 'py' launcher first
py --version >nul 2>&1
if %errorlevel% equ 0 ( set PY_CMD=py & goto :RUN )
python --version >nul 2>&1
if %errorlevel% equ 0 ( set PY_CMD=python & goto :RUN )

echo ❌ ERROR: Python not found.
exit /b

:RUN
%PY_CMD% igniter.py
if %errorlevel% neq 0 (
    echo ❌ ENGINE CRASH.
)
