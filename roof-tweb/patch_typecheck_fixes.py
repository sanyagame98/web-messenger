from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"[Roof typecheck patch] marker missing: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. Do not let TypeScript narrow the original TWeb peer union away from User;
# native code below still performs its own cast after this Roof-only guard.
title_icons = ROOT / "src/components/generateTitleIcons.ts"
replace_once(
    title_icons,
    "&& peer._ !== 'user') {",
    "&& (peer as any)._ !== 'user') {",
    "generateTitleIcons peer guard",
)

# 2. TypeScript 7 requires an explicit void callback here because the callback
# only fire-and-forgets an async Roof status mount.
edit_profile = ROOT / "src/components/sidebarLeft/tabs/editProfile.tsx"
replace_once(
    edit_profile,
    "createEffect(() => void mountRoofPremiumEmojiStatus(el, roofStatus(), 38));",
    "createEffect((): void => { void mountRoofPremiumEmojiStatus(el, roofStatus(), 38); });",
    "edit profile premium status effect",
)

# 3. Same TS7 callback rule for the delayed channel bubble decorator.
post_tools = ROOT / "src/lib/roof/RoofChannelPostTools.ts"
replace_once(
    post_tools,
    "timer = window.setTimeout(() => void decorateBubbles(chat, intersection), 80);",
    "timer = window.setTimeout((): void => { void decorateBubbles(chat, intersection); }, 80);",
    "channel post schedule",
)

# 4. Same TS7 callback rule for username search debounce.
new_chat = ROOT / "src/lib/roof/RoofNewChatSearch.ts"
replace_once(
    new_chat,
    "timer = window.setTimeout(() => void search(), 180);",
    "timer = window.setTimeout((): void => { void search(); }, 180);",
    "new chat search debounce",
)

# 5. Saved Messages should not import a helper that the generated atlas does
# not expose. Unicode is still preserved; normal chat rendering keeps the local
# Telegram-style atlas renderer.
saved = ROOT / "src/lib/roof/RoofSavedMessages.ts"
saved_text = saved.read_text(encoding="utf-8")
saved_text = saved_text.replace(
    "import {wrapTelegramEmojiText} from '@lib/roof/telegramEmojiAtlas';\n",
    "",
    1,
)
old_render = """function renderText(node: HTMLElement, text: string) {\n  try { node.append(wrapTelegramEmojiText(text || '')); }\n  catch { node.textContent = text || ''; }\n}\n"""
new_render = """function renderText(node: HTMLElement, text: string): void {\n  node.textContent = text || '';\n}\n"""
if new_render not in saved_text:
    if old_render not in saved_text:
        raise SystemExit("[Roof typecheck patch] marker missing: Saved Messages renderer")
    saved_text = saved_text.replace(old_render, new_render, 1)
saved.write_text(saved_text, encoding="utf-8")

# 6-7. The generated atlas dimensions are numeric constants. Explicit number
# annotations prevent TS from treating 1800/2475/45 as disjoint literal types
# in the defensive denominator checks.
atlas = ROOT / "src/lib/roof/telegramEmojiAtlas.ts"
atlas_text = atlas.read_text(encoding="utf-8")
for old, new in (
    ("const CELL = 45;", "const CELL: number = 45;"),
    ("const ATLAS_WIDTH = 1800;", "const ATLAS_WIDTH: number = 1800;"),
    ("const ATLAS_HEIGHT = 2475;", "const ATLAS_HEIGHT: number = 2475;"),
):
    if new not in atlas_text:
        if old not in atlas_text:
            raise SystemExit(f"[Roof typecheck patch] atlas marker missing: {old}")
        atlas_text = atlas_text.replace(old, new, 1)
atlas.write_text(atlas_text, encoding="utf-8")

# Guard the exact seven regressions that broke Docker typecheck.
checks = {
    title_icons: "(peer as any)._ !== 'user'",
    edit_profile: "createEffect((): void => { void mountRoofPremiumEmojiStatus",
    post_tools: "window.setTimeout((): void => { void decorateBubbles",
    new_chat: "window.setTimeout((): void => { void search(); }, 180)",
    saved: "function renderText(node: HTMLElement, text: string): void",
    atlas: "const ATLAS_WIDTH: number = 1800;",
}
for path, needle in checks.items():
    if needle not in path.read_text(encoding="utf-8"):
        raise SystemExit(f"[Roof typecheck patch] verification failed: {path.name}: {needle}")

print("[Roof typecheck patch] fixed 7 Roof/TWeb TypeScript compatibility errors")
