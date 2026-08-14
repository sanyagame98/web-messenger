# Roof

Roof is a self-hosted messenger project using the open-source TWeb client as a UI/client-behavior base while replacing Telegram/MTProto networking with Roof's own API, WebSocket transport, authentication, database, messaging, entitlements, bots, groups/channels, and media services.

Current development branch: `roof-own-tweb`.

## Architecture rule

The Roof runtime must not connect to Telegram or Teamgram servers. Unsupported TWeb API methods fail with `ROOF_METHOD_NOT_IMPLEMENTED` until implemented on the Roof backend; there is no fallback to Telegram/Teamgram.

The TWeb-derived client is GPL-3.0 and must remain license-compliant when distributed. The Roof backend is maintained as a separate service.
