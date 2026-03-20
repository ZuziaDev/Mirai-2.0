@echo off
title MIRAI - Spotify Authorization
echo Starting Spotify authorization...
echo.

py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto :RUN
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :RUN
)

echo Python not found.
pause
exit /b

:RUN
%PY_CMD% scripts\spotify_auth.py
pause
