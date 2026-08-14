@echo off
setlocal
cd /d "%~dp0"
title Roof Messenger

echo [Roof] Checking Docker...
where docker >nul 2>&1
if errorlevel 1 (
  echo Docker is not installed or is not in PATH.
  echo Install Docker Desktop, start it, then run this file again.
  pause
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running.
  echo Start Docker Desktop and try again.
  pause
  exit /b 1
)

if not exist .env (
  echo [Roof] Creating local server secret...
  powershell -NoProfile -Command "$b=New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ('SECRET_KEY='+[Convert]::ToBase64String($b)) | Set-Content -Encoding ascii '.env'"
  if errorlevel 1 (
    echo Failed to create .env
    pause
    exit /b 1
  )
)

set NEED_LOAD=0
docker image inspect roof-backend:ready >nul 2>&1 || set NEED_LOAD=1
docker image inspect roof-frontend:ready >nul 2>&1 || set NEED_LOAD=1

if "%NEED_LOAD%"=="1" (
  if not exist roof-images.tar.gz (
    echo roof-images.tar.gz was not found.
    pause
    exit /b 1
  )
  echo [Roof] Loading prebuilt Roof images. This can take a minute...
  docker load -i roof-images.tar.gz
  if errorlevel 1 (
    echo Failed to load Roof images.
    pause
    exit /b 1
  )
)

echo [Roof] Starting your own Roof server...
docker compose up -d
if errorlevel 1 (
  echo Failed to start Roof.
  docker compose ps
  pause
  exit /b 1
)

echo [Roof] Waiting for server...
for /L %%i in (1,1,40) do (
  curl.exe -fsS http://localhost:8080/health >nul 2>&1 && goto ready
  timeout /t 1 /nobreak >nul
)

echo Roof did not become ready in time.
docker compose ps
pause
exit /b 1

:ready
echo.
echo ==============================================
echo   ROOF IS RUNNING: http://localhost:8080
echo ==============================================
echo.
echo First launch? Run CREATE_ADMIN.bat once to create
 echo the owner account nadone229@gmail.com.
echo.
start "" http://localhost:8080
pause
