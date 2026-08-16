from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent

source = OVERLAY / "RoofChannelPostTools.ts"
target = ROOT / "src/lib/roof/RoofChannelPostTools.ts"
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, target)

path = ROOT / "src/components/chat/topbar.ts"
text = path.read_text(encoding="utf-8")

import_line = "import {installRoofChannelPostTools} from '@lib/roof/RoofChannelPostTools';\n"
if import_line not in text:
    marker = "import {installRoofChannelComments} from '@lib/roof/RoofChannelComments';\n"
    if marker not in text:
        marker = "import {openRoofChatSettings} from '@lib/roof/RoofChatSettings';\n"
    if marker not in text:
        raise SystemExit("[Roof channel post tools patch] import marker missing")
    text = text.replace(marker, marker + import_line, 1)

call = "    installRoofChannelPostTools(this.chat);\n"
if call not in text:
    marker = "    installRoofChannelComments(this.chat);\n"
    if marker not in text:
        marker = "    this.container.dataset.floating = '0';\n"
    if marker not in text:
        raise SystemExit("[Roof channel post tools patch] construct marker missing")
    text = text.replace(marker, marker + "\n" + call, 1)

path.write_text(text, encoding="utf-8")
check = path.read_text(encoding="utf-8")
for needle in ("RoofChannelPostTools", "installRoofChannelPostTools(this.chat)"):
    if needle not in check:
        raise SystemExit(f"[Roof channel post tools patch] verification failed: {needle}")

print("[Roof channel post tools patch] views, authors and post menu installed")
