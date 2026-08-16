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
print("[Roof comments patch] channel post comments installed")
