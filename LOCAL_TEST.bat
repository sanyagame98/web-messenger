@echo off
setlocal
cd /d "%~dp0"
title Roof Local Test

echo ==============================================
echo           ROOF - LOCAL TEST BUILD
echo ==============================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
  echo Docker is not installed or not in PATH.
  echo Install Docker Desktop and start it first.
  pause
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running.
  echo Start Docker Desktop and run LOCAL_TEST.bat again.
  pause
  exit /b 1
)

echo [1/4] Building your own Roof backend...
docker build -f deploy/backend.Dockerfile -t roof-backend:ready .
if errorlevel 1 goto failed

echo.
echo [2/4] Building Roof frontend...
docker build -f deploy/frontend.Dockerfile -t roof-frontend:ready .
if errorlevel 1 goto failed

echo.
echo [3/4] Preparing local server...
if not exist roof-ready\.env (
  powershell -NoProfile -Command "$b=New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ('SECRET_KEY='+[Convert]::ToBase64String($b)) | Set-Content -Encoding ascii 'roof-ready\.env'"
  if errorlevel 1 goto failed
)

docker compose -f roof-ready/docker-compose.yml down >nul 2>&1
docker compose -f roof-ready/docker-compose.yml up -d
if errorlevel 1 goto failed

echo.
echo [4/4] Waiting for Roof...
for /L %%i in (1,1,60) do (
  curl.exe -fsS http://localhost:8080/health >nul 2>&1 && goto ready
  timeout /t 1 /nobreak >nul
)

echo Roof did not become ready.
docker compose -f roof-ready/docker-compose.yml ps
docker compose -f roof-ready/docker-compose.yml logs --tail=100
pause
exit /b 1

:ready
echo.
echo ==============================================
echo   ROOF LOCAL TEST: http://localhost:8080
echo ==============================================
echo.
echo Registration: email + password only.
echo Login: email + password only.
echo No Telegram codes or SMS.
echo.
echo To create/reset your owner account run:
echo   roof-ready\CREATE_ADMIN.bat
echo.
start "" http://localhost:8080
pause
exit /b 0

:failed
echo.
echo Roof local build failed. Copy the error above and send it to ChatGPT.
pause
exit /b 1
