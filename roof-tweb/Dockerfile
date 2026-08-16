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
RUN git clone --depth=1 https://github.com/k3a/telegram-emoji-list.git /src/telegram-emoji-list

COPY roof-tweb/ /src/roof/
RUN mkdir -p /src/tweb/public/assets/roof-emoji /src/tweb/src/lib/roof \
    && cp /src/telegram-emoji-list/emj.png /src/tweb/public/assets/roof-emoji/emj.png \
    && cp /src/telegram-emoji-list/LICENSE /src/tweb/public/assets/roof-emoji/GPL-3.0.txt \
    && python3 /src/roof/generate_telegram_emoji_atlas.py /src/telegram-emoji-list/atlas.htm /src/telegram-emoji-list/emoji_autocomplete.json /src/telegram-emoji-list/emj.png /src/tweb/src/lib/roof/telegramEmojiAtlas.ts \
    && for f in /src/roof/roof-*.css; do if [ "$f" != "/src/roof/roof-ui.css" ]; then cat "$f" >> /src/roof/roof-ui.css; fi; done \
    && python3 /src/roof/patch_tweb_safe.py /src/tweb \
    && python3 /src/roof/patch_telegram_emoji.py /src/tweb \
    && python3 /src/roof/patch_premium_emoji.py /src/tweb \
    && python3 /src/roof/patch_peer_premium_status.py /src/tweb \
    && python3 /src/roof/patch_sidebar_new_chat.py /src/tweb \
    && python3 /src/roof/patch_chat_settings.py /src/tweb \
    && python3 /src/roof/patch_channel_comments.py /src/tweb \
    && python3 /src/roof/patch_channel_post_tools.py /src/tweb \
    && python3 /src/roof/patch_media_uploader.py /src/tweb \
    && python3 /src/roof/patch_voice_recorder.py /src/tweb \
    && python3 /src/roof/patch_saved_messages.py /src/tweb \
    && cp /src/roof/roof-ui.css /src/tweb/public/roof-ui.css \
    && python3 - <<'PY'
from pathlib import Path
path = Path('/src/tweb/index.html')
text = path.read_text(encoding='utf-8')
if '/roof-ui.css' not in text:
    text = text.replace('</head>', '  <link rel="stylesheet" href="/roof-ui.css?v=roof-ui-v15">\n</head>')
path.write_text(text, encoding='utf-8')
PY

WORKDIR /src/tweb
RUN pnpm install --frozen-lockfile && pnpm run build

FROM nginx:1.29-alpine
COPY roof-tweb/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/tweb/dist/ /usr/share/nginx/html/
COPY --from=build /src/roof/roof-ui.css /usr/share/nginx/html/roof-ui.css
RUN test -s /usr/share/nginx/html/roof-ui.css \
    && test -s /usr/share/nginx/html/assets/roof-emoji/emj.png \
    && grep -q 'roof-saved-panel' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-voice-recording' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-media-preview-panel' /usr/share/nginx/html/roof-ui.css \
    && grep -q '/roof-ui.css' /usr/share/nginx/html/index.html
EXPOSE 80
