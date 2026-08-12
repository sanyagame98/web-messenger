@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>nul || (
  echo Docker not found. Install/start Docker Desktop first.
  pause
  exit /b 1
)

docker info >nul 2>nul || (
  echo Docker Desktop is not running. Start it and run this file again.
  pause
  exit /b 1
)

if not exist "roof-teamgram-image.tar.gz" (
  echo Missing roof-teamgram-image.tar.gz
  echo Download the complete Roof-Ready artifact from GitHub Actions.
  pause
  exit /b 1
)

echo [1/3] Loading prebuilt Roof Teamgram server image...
docker image inspect roof-teamgram:ready >nul 2>nul
if errorlevel 1 (
  docker load -i roof-teamgram-image.tar.gz || goto :fail
) else (
  echo Image already loaded.
)

echo [2/3] Starting databases and infrastructure...
docker compose -f docker-compose.yml up -d || goto :fail

echo [3/3] Roof is starting...
echo.
echo Roof Web:   http://localhost:8080
echo Roof Store: http://localhost:8787/store/
echo.
start "" http://localhost:8080
pause
exit /b 0

:fail
echo.
echo Roof startup failed. Copy the error above into ChatGPT.
pause
exit /b 1
