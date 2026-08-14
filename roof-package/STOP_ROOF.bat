@echo off
setlocal
cd /d "%~dp0"
docker compose down
echo [Roof] Stopped.
pause
endlocal
