@echo off
setlocal
cd /d "%~dp0"

echo [Roof] Checking Docker Desktop...
docker version >nul 2>&1
if errorlevel 1 (
  echo [Roof] Start Docker Desktop and run this file again.
  pause
  exit /b 1
)

if not exist "roof-images.tar" (
  echo [Roof] roof-images.tar is missing.
  pause
  exit /b 1
)

echo [Roof] Loading Roof images. First launch can take a few minutes...
docker load -i roof-images.tar
if errorlevel 1 (
  echo [Roof] Failed to load Docker images.
  pause
  exit /b 1
)

echo [Roof] Starting local messenger...
docker compose up -d
if errorlevel 1 (
  echo [Roof] Start failed. Run: docker compose logs
  pause
  exit /b 1
)

echo.
echo [Roof] Ready: http://localhost:8080
start "" http://localhost:8080
endlocal
