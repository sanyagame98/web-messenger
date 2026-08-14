@echo off
setlocal
cd /d "%~dp0"

echo [Roof] Starting own backend and full TWeb client...
docker version >nul 2>&1
if errorlevel 1 (
  echo [Roof] Docker Desktop is not running.
  pause
  exit /b 1
)

docker compose up --build -d
if errorlevel 1 (
  echo [Roof] Build/start failed. Run: docker compose logs
  pause
  exit /b 1
)

echo.
echo [Roof] Ready: http://localhost:8080
start "" http://localhost:8080
endlocal
