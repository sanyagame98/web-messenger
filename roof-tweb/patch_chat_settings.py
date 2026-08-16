from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent

source = OVERLAY / "RoofChatSettings.ts"
target = ROOT / "src/lib/roof/RoofChatSettings.ts"
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, target)

path = ROOT / "src/components/chat/topbar.ts"
text = path.read_text(encoding="utf-8")

import_line = "import {openRoofChatSettings} from '@lib/roof/RoofChatSettings';\n"
if import_line not in text:
    marker = "import handleCommunityChatJoinError\nfrom '@components/communities/handleCommunityChatJoinError';\n"
    if marker not in text:
        raise SystemExit("[Roof chat settings patch] topbar import marker missing")
    text = text.replace(marker, marker + import_line, 1)

utils_marker = """    this.chatUtils = document.createElement('div');\n    this.chatUtils.classList.add('chat-utils');\n\n    this.plates = createTopbarPlates(this, this.chat, this.managers);\n"""
utils_replacement = """    this.chatUtils = document.createElement('div');\n    this.chatUtils.classList.add('chat-utils');\n\n    const roofSettingsButton = document.createElement('button');\n    roofSettingsButton.type = 'button';\n    roofSettingsButton.className = 'roof-chat-settings-topbar-button';\n    roofSettingsButton.title = 'Настройки Roof';\n    roofSettingsButton.innerHTML = '<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"3\"/><path d=\"M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.08A1.7 1.7 0 0 0 8.94 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.57 15a1.7 1.7 0 0 0-1.56-1.03H3v-4h.08A1.7 1.7 0 0 0 4.6 8.94a1.7 1.7 0 0 0-.34-1.88L4.2 7l2.83-2.83.06.06A1.7 1.7 0 0 0 8.97 4.6 1.7 1.7 0 0 0 10 3.08V3h4v.08a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06L19.8 7l-.06.06a1.7 1.7 0 0 0-.34 1.88A1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15z\"/></svg>';\n    attachClickEvent(roofSettingsButton, (event) => {\n      event.stopPropagation();\n      const peerId = this.peerId;\n      if(!peerId?.isAnyChat?.()) return;\n      void openRoofChatSettings(Number(peerId.toChatId()));\n    }, {listenerSetter: this.listenerSetter});\n\n    this.plates = createTopbarPlates(this, this.chat, this.managers);\n"""
if utils_replacement not in text:
    if utils_marker not in text:
        raise SystemExit("[Roof chat settings patch] chat utils marker missing")
    text = text.replace(utils_marker, utils_replacement, 1)

append_marker = """      this.btnGroupCallMenu,\n      this.btnSearch,\n      this.btnLogFilters,\n      this.btnMore\n"""
append_replacement = """      this.btnGroupCallMenu,\n      roofSettingsButton,\n      this.btnSearch,\n      this.btnLogFilters,\n      this.btnMore\n"""
if append_replacement not in text:
    if append_marker not in text:
        raise SystemExit("[Roof chat settings patch] topbar append marker missing")
    text = text.replace(append_marker, append_replacement, 1)

# Hide the Roof settings gear in private user chats. It remains available for
# groups and channels, where peerId is a chat/channel peer.
verify_marker = """    this.pushButtonToVerify(this.btnCall, this.verifyCallButton.bind(this, 'voice'));\n"""
verify_replacement = """    this.pushButtonToVerify(roofSettingsButton, () => this.peerId?.isAnyChat?.() || false);\n    this.pushButtonToVerify(this.btnCall, this.verifyCallButton.bind(this, 'voice'));\n"""
if verify_replacement not in text:
    if verify_marker not in text:
        raise SystemExit("[Roof chat settings patch] verify marker missing")
    text = text.replace(verify_marker, verify_replacement, 1)

path.write_text(text, encoding="utf-8")
for needle in ("openRoofChatSettings", "roof-chat-settings-topbar-button", "pushButtonToVerify(roofSettingsButton"):
    if needle not in text:
        raise SystemExit(f"[Roof chat settings patch] verification failed: {needle}")

print("[Roof chat settings patch] functional group/channel settings button installed")
