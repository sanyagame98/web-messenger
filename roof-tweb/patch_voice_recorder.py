from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent

source = OVERLAY / "RoofVoiceRecorder.ts"
target = ROOT / "src/lib/roof/RoofVoiceRecorder.ts"
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, target)

path = ROOT / "src/components/chat/topbar.ts"
text = path.read_text(encoding="utf-8")

import_line = "import {installRoofVoiceRecorder} from '@lib/roof/RoofVoiceRecorder';\n"
if import_line not in text:
    marker = "import {installRoofMediaUploader} from '@lib/roof/RoofMediaUploader';\n"
    if marker not in text:
        marker = "import {installRoofChannelComments} from '@lib/roof/RoofChannelComments';\n"
    if marker not in text:
        raise SystemExit("[Roof voice patch] import marker missing")
    text = text.replace(marker, marker + import_line, 1)

install_line = "    installRoofVoiceRecorder(this.chat);\n"
if install_line not in text:
    marker = "    installRoofMediaUploader(this.chat);\n"
    if marker not in text:
        marker = "    installRoofChannelComments(this.chat);\n"
    if marker not in text:
        raise SystemExit("[Roof voice patch] install marker missing")
    text = text.replace(marker, marker + install_line, 1)

path.write_text(text, encoding="utf-8")
for needle in ("RoofVoiceRecorder", "installRoofVoiceRecorder(this.chat)"):
    if needle not in text:
        raise SystemExit(f"[Roof voice patch] verification failed: {needle}")
print("[Roof voice patch] recorder installed")
