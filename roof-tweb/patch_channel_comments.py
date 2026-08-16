from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent

source = OVERLAY / "RoofChannelComments.ts"
target = ROOT / "src/lib/roof/RoofChannelComments.ts"
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, target)

# Keep the custom discussion UI on the exact same Telegram-style emoji renderer
# as normal TWeb messages/picker. The source intentionally stores Unicode; only
# rendering changes, so DB/search/copy remain normal text.
comments = target.read_text(encoding="utf-8")
emoji_import = "import wrapEmojiText from '@lib/richTextProcessor/wrapEmojiText';\n"
if emoji_import not in comments:
    comments = comments.replace(
        "import roofTransport from '@lib/roof/roofTransport';\n",
        "import roofTransport from '@lib/roof/roofTransport';\n" + emoji_import,
        1,
    )
comments = comments.replace(
    "const text = el('div');\n    text.textContent = state.post.message || 'Публикация';\n",
    "const text = el('div');\n    text.append(wrapEmojiText(state.post.message || 'Публикация'));\n",
)
comments = comments.replace(
    "const message = el('div', 'roof-discussion-text'); message.textContent = comment.message; body.append(message);\n",
    "const message = el('div', 'roof-discussion-text'); message.append(wrapEmojiText(comment.message)); body.append(message);\n",
)
comments = comments.replace(
    "chip.type = 'button'; chip.textContent = `${reaction.emoji} ${reaction.count}`;\n",
    "chip.type = 'button'; chip.append(wrapEmojiText(reaction.emoji), document.createTextNode(` ${reaction.count}`)); chip.disabled = !state?.joined;\n",
)
comments = comments.replace(
    "const plus = el('button', 'roof-discussion-reaction add'); plus.type = 'button'; plus.textContent = '＋';\n",
    "const plus = el('button', 'roof-discussion-reaction add'); plus.type = 'button'; plus.textContent = '＋'; plus.disabled = !state?.joined;\n",
)
comments = comments.replace(
    "replyButton.onclick = () => { replyTo = comment; renderComposer(); };\n",
    "replyButton.disabled = !state?.joined;\n      replyButton.onclick = () => { if(!state?.joined) return; replyTo = comment; renderComposer(); };\n",
)
comments = comments.replace(
    "const button = el('button'); button.type = 'button'; button.textContent = emoji;\n",
    "const button = el('button'); button.type = 'button'; button.append(wrapEmojiText(emoji));\n",
)
target.write_text(comments, encoding="utf-8")

path = ROOT / "src/components/chat/topbar.ts"
text = path.read_text(encoding="utf-8")

import_line = "import {installRoofChannelComments} from '@lib/roof/RoofChannelComments';\n"
if import_line not in text:
    marker = "import {openRoofChatSettings} from '@lib/roof/RoofChatSettings';\n"
    if marker not in text:
        marker = "import handleCommunityChatJoinError\nfrom '@components/communities/handleCommunityChatJoinError';\n"
    if marker not in text:
        raise SystemExit("[Roof comments patch] topbar import marker missing")
    text = text.replace(marker, marker + import_line, 1)

marker = """    this.container = document.createElement('div');\n    this.container.classList.add('sidebar-header', 'topbar', 'hide');\n    this.container.dataset.floating = '0';\n"""
replacement = marker + "\n    installRoofChannelComments(this.chat);\n"
if "installRoofChannelComments(this.chat);" not in text:
    if marker not in text:
        raise SystemExit("[Roof comments patch] construct marker missing")
    text = text.replace(marker, replacement, 1)

path.write_text(text, encoding="utf-8")
check = path.read_text(encoding="utf-8")
for needle in ("RoofChannelComments", "installRoofChannelComments(this.chat)"):
    if needle not in check:
        raise SystemExit(f"[Roof comments patch] verification failed: {needle}")
comment_check = target.read_text(encoding="utf-8")
for needle in ("wrapEmojiText", "chip.disabled = !state?.joined", "replyButton.disabled = !state?.joined"):
    if needle not in comment_check:
        raise SystemExit(f"[Roof comments patch] discussion verification failed: {needle}")
print("[Roof comments patch] channel post comments installed with Telegram-style emoji and join gating")
