@echo off
cd /d "%~dp0"
title Stop Roof

echo [Roof] Stopping containers...
docker compose down
if errorlevel 1 (
  echo Failed to stop Roof.
  pause
  exit /b 1
)

echo Roof stopped. Your users, messages and uploads were kept.
pause
