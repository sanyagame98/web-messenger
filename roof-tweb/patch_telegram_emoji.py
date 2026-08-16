from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
path = ROOT / "src/lib/richTextProcessor/wrapRichText.ts"
text = path.read_text(encoding="utf-8")

import_line = "import {applyRoofTelegramEmoji} from '@lib/roof/telegramEmojiAtlas';\n"
if import_line not in text:
    marker = "import formatRelativeTime from '@helpers/date/formatRelativeTime';\n"
    if marker not in text:
        raise SystemExit("[Roof emoji patch] wrapRichText import marker not found")
    text = text.replace(marker, marker + import_line, 1)

case_marker = """      case 'messageEntityEmoji': {\n        let isSupported = IS_EMOJI_SUPPORTED;\n"""
replacement = """      case 'messageEntityEmoji': {\n        // Roof renders regular emoji from the local Telegram-style atlas. Keep\n        // the original Unicode as text inside the span so copy/paste, search,\n        // message storage and accessibility remain standard Unicode. Draft\n        // content stays native because contenteditable needs browser text.\n        if(!options.wrappingDraft) {\n          const roofEmoji = document.createElement('span');\n          if(applyRoofTelegramEmoji(roofEmoji, entity.unicode, fullEntityText)) {\n            element = roofEmoji;\n            break;\n          }\n        }\n\n        let isSupported = IS_EMOJI_SUPPORTED;\n"""
if replacement not in text:
    if case_marker not in text:
        raise SystemExit("[Roof emoji patch] messageEntityEmoji block not found")
    text = text.replace(case_marker, replacement, 1)

path.write_text(text, encoding="utf-8")

check = path.read_text(encoding="utf-8")
if "applyRoofTelegramEmoji(roofEmoji, entity.unicode, fullEntityText)" not in check:
    raise SystemExit("[Roof emoji patch] renderer hook was not installed")

atlas = ROOT / "src/lib/roof/telegramEmojiAtlas.ts"
sprite = ROOT / "public/assets/roof-emoji/emj.png"
license_file = ROOT / "public/assets/roof-emoji/GPL-3.0.txt"
for required in (atlas, sprite, license_file):
    if not required.is_file() or required.stat().st_size == 0:
        raise SystemExit(f"[Roof emoji patch] required atlas asset missing: {required}")

print("[Roof emoji patch] regular emoji renderer uses local Telegram-style atlas")
