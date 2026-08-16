from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent

source = OVERLAY / "RoofMediaUploader.ts"
target = ROOT / "src/lib/roof/RoofMediaUploader.ts"
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, target)

path = ROOT / "src/components/chat/topbar.ts"
text = path.read_text(encoding="utf-8")

import_line = "import {installRoofMediaUploader} from '@lib/roof/RoofMediaUploader';\n"
if import_line not in text:
    marker = "import {installRoofChannelComments} from '@lib/roof/RoofChannelComments';\n"
    if marker not in text:
        marker = "import {openRoofChatSettings} from '@lib/roof/RoofChatSettings';\n"
    if marker not in text:
        raise SystemExit("[Roof media patch] import marker missing")
    text = text.replace(marker, marker + import_line, 1)

if "installRoofMediaUploader(this.chat);" not in text:
    marker = "    installRoofChannelComments(this.chat);\n"
    if marker in text:
        text = text.replace(marker, marker + "    installRoofMediaUploader(this.chat);\n", 1)
    else:
        marker = "    this.container.dataset.floating = '0';\n"
        if marker not in text:
            raise SystemExit("[Roof media patch] construct marker missing")
        text = text.replace(marker, marker + "\n    installRoofMediaUploader(this.chat);\n", 1)

path.write_text(text, encoding="utf-8")
for needle in ("RoofMediaUploader", "installRoofMediaUploader(this.chat)"):
    if needle not in text:
        raise SystemExit(f"[Roof media patch] verification failed: {needle}")
print("[Roof media patch] drag-drop and preview uploader installed")
