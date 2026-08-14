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
COPY roof-tweb/roofTransport.ts /src/roof/roofTransport.ts
COPY roof-tweb/SignInCard.tsx /src/roof/SignInCard.tsx
RUN python3 /src/roof/patch_tweb.py /src/tweb

WORKDIR /src/tweb
RUN pnpm install --frozen-lockfile && pnpm run build

FROM nginx:1.29-alpine
COPY roof-tweb/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/tweb/dist/ /usr/share/nginx/html/
EXPOSE 80
