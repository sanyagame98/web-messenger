from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()

# 1) Render regular emoji from the local Telegram-style atlas everywhere TWeb
# renders messageEntityEmoji (messages, picker, previews, etc.).
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

# 2) Merge the local k3a shortcode/name index into TWeb's native emoji search.
# This makes :smile:, heart, laughing, etc. work without Telegram API emoji
# keyword packs, while preserving TWeb recents, categories and custom emoji.
manager_path = ROOT / "src/lib/appManagers/appEmojiManager.ts"
manager = manager_path.read_text(encoding="utf-8")
search_import = "import {searchRoofTelegramEmoji} from '@lib/roof/telegramEmojiAtlas';\n"
if search_import not in manager:
    marker = "import {EmojiSkinTone, getEmojiSkinToneBase, getEmojiSkinToneVariants} from '@helpers/emojiSkinTone';\n"
    if marker not in manager:
        raise SystemExit("[Roof emoji patch] appEmojiManager import marker not found")
    manager = manager.replace(marker, marker + search_import, 1)

needle = """    if(q.trim()) {\n      const set = this.index.search(q, minChars);\n      emojis = filterUnique(flatten(Array.from(set)));\n      emojis.length = Math.min(40, emojis.length);\n    } else {\n"""
replacement_search = """    if(q.trim()) {\n      const roofEmojis = searchRoofTelegramEmoji(q, limit);\n      const set = this.index.search(q, minChars);\n      const twebEmojis = filterUnique(flatten(Array.from(set)));\n      emojis = filterUnique([...roofEmojis, ...twebEmojis]);\n      emojis.length = Math.min(limit, emojis.length);\n    } else {\n"""
if replacement_search not in manager:
    if needle not in manager:
        raise SystemExit("[Roof emoji patch] appEmojiManager search block not found")
    manager = manager.replace(needle, replacement_search, 1)

manager_path.write_text(manager, encoding="utf-8")

check = path.read_text(encoding="utf-8")
manager_check = manager_path.read_text(encoding="utf-8")
if "applyRoofTelegramEmoji(roofEmoji, entity.unicode, fullEntityText)" not in check:
    raise SystemExit("[Roof emoji patch] renderer hook was not installed")
if "searchRoofTelegramEmoji(q, limit)" not in manager_check:
    raise SystemExit("[Roof emoji patch] emoji search hook was not installed")

atlas = ROOT / "src/lib/roof/telegramEmojiAtlas.ts"
sprite = ROOT / "public/assets/roof-emoji/emj.png"
license_file = ROOT / "public/assets/roof-emoji/GPL-3.0.txt"
for required in (atlas, sprite, license_file):
    if not required.is_file() or required.stat().st_size == 0:
        raise SystemExit(f"[Roof emoji patch] required atlas asset missing: {required}")

print("[Roof emoji patch] local Telegram-style renderer + shortcode/name search enabled")
