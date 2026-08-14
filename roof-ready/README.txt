ROOF READY — CUSTOM SERVER EDITION
==================================

This package is NOT Teamgram and does not connect to Telegram.
It contains the custom Roof frontend and custom FastAPI backend.

QUICK START (Windows)
1. Install and start Docker Desktop.
2. Run START_ROOF.bat.
3. Roof opens at http://localhost:8080
4. On the first launch, run CREATE_ADMIN.bat and choose a password.
5. Sign in with: nadone229@gmail.com

ACCOUNT SYSTEM
- Registration: email + password only.
- Login: email + password only.
- No SMS, Telegram codes, or external auth messages.
- Username is created automatically and can be changed in the Roof profile.

OWNER / ADMIN BOT
Only nadone229@gmail.com is treated as the Roof administrator.
The owner profile contains Roof Admin Bot, where the owner can:
- view/search users;
- grant Roof Stars;
- gift Roof Premium without spending stars;
- revoke Premium;
- grant/remove the official verification badge.

DATA
Users, messages and uploads are stored in Docker volumes and survive STOP_ROOF.bat.
STOP_ROOF.bat does not delete data.

SERVER ACCESS
The web service is exposed on port 8080. The backend stays inside Docker and is reached
through the Roof nginx reverse proxy (/api, /ws and /uploads), so the browser does not
need a separate backend port.

FILES
- START_ROOF.bat      Start Roof
- STOP_ROOF.bat       Stop Roof without deleting data
- CREATE_ADMIN.bat    Create/reset the owner password
- roof-images.tar.gz  Prebuilt Roof Docker images
- docker-compose.yml  Roof services

For an internet-facing deployment, put your HTTPS reverse proxy/domain in front of port 8080.
