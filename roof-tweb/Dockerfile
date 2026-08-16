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

# Roof regular emoji source. The runtime stays fully local: the sprite, mapping
# and GPL-3.0 license are copied into the final web bundle during this build.
RUN git clone --depth=1 https://github.com/k3a/telegram-emoji-list.git /src/telegram-emoji-list

COPY roof-tweb/patch_tweb.py /src/roof/patch_tweb.py
COPY roof-tweb/patch_tweb_safe.py /src/roof/patch_tweb_safe.py
COPY roof-tweb/patch_telegram_emoji.py /src/roof/patch_telegram_emoji.py
COPY roof-tweb/patch_premium_emoji.py /src/roof/patch_premium_emoji.py
COPY roof-tweb/patch_peer_premium_status.py /src/roof/patch_peer_premium_status.py
COPY roof-tweb/patch_sidebar_new_chat.py /src/roof/patch_sidebar_new_chat.py
COPY roof-tweb/generate_telegram_emoji_atlas.py /src/roof/generate_telegram_emoji_atlas.py
COPY roof-tweb/roofTransport.ts /src/roof/roofTransport.ts
COPY roof-tweb/SignInCard.tsx /src/roof/SignInCard.tsx
COPY roof-tweb/SettingsRoof.tsx /src/roof/SettingsRoof.tsx
COPY roof-tweb/RoofPremiumEmojiPacks.ts /src/roof/RoofPremiumEmojiPacks.ts
COPY roof-tweb/RoofNewChatSearch.ts /src/roof/RoofNewChatSearch.ts
COPY roof-tweb/roof-ui.css /src/roof/roof-ui.css
COPY roof-tweb/roof-profile-editor.css /src/roof/roof-profile-editor.css
COPY roof-tweb/roof-telegram-emoji.css /src/roof/roof-telegram-emoji.css
COPY roof-tweb/roof-premium-emoji.css /src/roof/roof-premium-emoji.css
COPY roof-tweb/roof-new-chat.css /src/roof/roof-new-chat.css

RUN mkdir -p /src/tweb/public/assets/roof-emoji /src/tweb/src/lib/roof \
    && cp /src/telegram-emoji-list/emj.png /src/tweb/public/assets/roof-emoji/emj.png \
    && cp /src/telegram-emoji-list/LICENSE /src/tweb/public/assets/roof-emoji/GPL-3.0.txt \
    && python3 /src/roof/generate_telegram_emoji_atlas.py \
        /src/telegram-emoji-list/atlas.htm \
        /src/telegram-emoji-list/emoji_autocomplete.json \
        /src/telegram-emoji-list/emj.png \
        /src/tweb/src/lib/roof/telegramEmojiAtlas.ts \
    && cat /src/roof/roof-profile-editor.css >> /src/roof/roof-ui.css \
    && cat /src/roof/roof-telegram-emoji.css >> /src/roof/roof-ui.css \
    && cat /src/roof/roof-premium-emoji.css >> /src/roof/roof-ui.css \
    && cat /src/roof/roof-new-chat.css >> /src/roof/roof-ui.css \
    && python3 /src/roof/patch_tweb_safe.py /src/tweb \
    && python3 /src/roof/patch_telegram_emoji.py /src/tweb \
    && python3 /src/roof/patch_premium_emoji.py /src/tweb \
    && python3 /src/roof/patch_peer_premium_status.py /src/tweb \
    && python3 /src/roof/patch_sidebar_new_chat.py /src/tweb \
    && cp /src/roof/roof-ui.css /src/tweb/public/roof-ui.css \
    && python3 - <<'PY'
from pathlib import Path
path = Path('/src/tweb/index.html')
text = path.read_text(encoding='utf-8')
if '/roof-ui.css' not in text:
    text = text.replace('</head>', '  <link rel="stylesheet" href="/roof-ui.css?v=roof-ui-v9">\n</head>')
path.write_text(text, encoding='utf-8')
PY

WORKDIR /src/tweb
RUN pnpm install --frozen-lockfile && pnpm run build

FROM nginx:1.29-alpine
COPY roof-tweb/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/tweb/dist/ /usr/share/nginx/html/
COPY roof-tweb/roof-ui.css /usr/share/nginx/html/roof-ui.css
COPY roof-tweb/roof-profile-editor.css /tmp/roof-profile-editor.css
COPY roof-tweb/roof-telegram-emoji.css /tmp/roof-telegram-emoji.css
COPY roof-tweb/roof-premium-emoji.css /tmp/roof-premium-emoji.css
COPY roof-tweb/roof-new-chat.css /tmp/roof-new-chat.css
RUN cat /tmp/roof-profile-editor.css >> /usr/share/nginx/html/roof-ui.css \
    && cat /tmp/roof-telegram-emoji.css >> /usr/share/nginx/html/roof-ui.css \
    && cat /tmp/roof-premium-emoji.css >> /usr/share/nginx/html/roof-ui.css \
    && cat /tmp/roof-new-chat.css >> /usr/share/nginx/html/roof-ui.css \
    && rm /tmp/roof-profile-editor.css /tmp/roof-telegram-emoji.css /tmp/roof-premium-emoji.css /tmp/roof-new-chat.css \
    && test -s /usr/share/nginx/html/roof-ui.css \
    && test -s /usr/share/nginx/html/assets/roof-emoji/emj.png \
    && test -s /usr/share/nginx/html/assets/roof-emoji/GPL-3.0.txt \
    && grep -q 'tgico-search' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-premium-card' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-profile-editor' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-telegram-emoji' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-premium-emoji-panel' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-peer-title-status' /usr/share/nginx/html/roof-ui.css \
    && grep -q 'roof-new-chat-panel' /usr/share/nginx/html/roof-ui.css \
    && grep -q '/roof-ui.css' /usr/share/nginx/html/index.html
EXPOSE 80
