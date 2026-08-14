@echo off
cd /d "%~dp0"
title Roof Admin Setup

docker info >nul 2>&1
if errorlevel 1 (
  echo Start Docker Desktop first.
  pause
  exit /b 1
)

if not exist .env (
  echo Run START_ROOF.bat first.
  pause
  exit /b 1
)

echo [Roof] Starting backend if needed...
docker compose up -d backend
if errorlevel 1 (
  echo Failed to start backend.
  pause
  exit /b 1
)

echo.
echo Creating/updating the only Roof administrator:
echo nadone229@gmail.com
echo.
docker compose exec backend python /app/create_admin.py
if errorlevel 1 (
  echo Admin setup failed.
  pause
  exit /b 1
)

echo.
echo Done. Sign in at http://localhost:8080 with nadone229@gmail.com
pause
