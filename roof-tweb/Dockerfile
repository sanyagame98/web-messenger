FROM node:24.11-bookworm-slim AS build

RUN corepack enable && corepack prepare pnpm@11.16.0 --activate \
    && apt-get update \
    && apt-get install -y --no-install-recommends git python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
ARG TWEB_COMMIT=e3730e10073c3fc02e1360e3513b70b176d6afec
RUN git clone --filter=blob:none https://github.com/morethanwords/tweb.git /src/tweb \
    && cd /src/tweb \
    && git checkout "$TWEB_COMMIT"

COPY roof-tweb/patch_tweb.py /src/roof/patch_tweb.py
COPY roof-tweb/patch_tweb_safe.py /src/roof/patch_tweb_safe.py
COPY roof-tweb/roofTransport.ts /src/roof/roofTransport.ts
COPY roof-tweb/SignInCard.tsx /src/roof/SignInCard.tsx
COPY roof-tweb/SettingsRoof.tsx /src/roof/SettingsRoof.tsx
COPY roof-tweb/roof-ui.css /src/roof/roof-ui.css
COPY roof-tweb/roof-profile-editor.css /src/roof/roof-profile-editor.css
RUN cat /src/roof/roof-profile-editor.css >> /src/roof/roof-ui.css \
    && python3 /src/roof/patch_tweb_safe.py /src/tweb \
    && cp /src/roof/roof-ui.css /src/tweb/public/roof-ui.css \
    && python3 - <<'PY'
from pathlib import Path
path = Path('/src/tweb/index.html')
text = path.read_text(encoding='utf-8')
if '/roof-ui.css' not in text:
    text = text.replace('</head>', '  <link rel="stylesheet" href="/roof-ui.css?v=roof-ui-v5">\n</head>')
path.write_text(text, encoding='utf-8')
PY

WORKDIR /src/tweb
RUN pnpm install --frozen-lockfile && pnpm run build

FROM nginx:1.29-alpine
COPY roof-tweb/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/tweb/dist/ /usr/share/nginx/html/
COPY roof-tweb/roof-ui.css /usr/share/nginx/html/roof-ui.css
COPY roof-tweb/roof-profile-editor.css /tmp/roof-profile-editor.css
RUN cat /tmp/roof-profile-editor.css >> /usr/share/nginx/html/roof-ui.css \
    && rm /tmp/roof-profile-editor.css \
    && test -s /usr/share/nginx/html/roof-ui.css \
    && grep -q 'tgico-search' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-premium-card' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-profile-editor' /usr/share/nginx/html/roof-ui.css \
    && grep -q '/roof-ui.css' /usr/share/nginx/html/index.html
EXPOSE 80
