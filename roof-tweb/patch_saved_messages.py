from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent

for name in ("RoofSavedMessages.ts", "RoofSavedMessagesHooks.ts"):
    target = ROOT / "src/lib/roof" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OVERLAY / name, target)

path = ROOT / "src/components/chat/topbar.ts"
text = path.read_text(encoding="utf-8")
import_line = "import {installRoofSavedMessagesHooks} from '@lib/roof/RoofSavedMessagesHooks';\n"
if import_line not in text:
    marker = "import {installRoofVoiceRecorder} from '@lib/roof/RoofVoiceRecorder';\n"
    if marker not in text:
        raise SystemExit("[Roof saved patch] voice import marker missing")
    text = text.replace(marker, marker + import_line, 1)
install_line = "    installRoofSavedMessagesHooks(this.chat);\n"
if install_line not in text:
    marker = "    installRoofVoiceRecorder(this.chat);\n"
    if marker not in text:
        raise SystemExit("[Roof saved patch] voice install marker missing")
    text = text.replace(marker, marker + install_line, 1)
path.write_text(text, encoding="utf-8")
print("[Roof saved patch] Saved Messages installed")
