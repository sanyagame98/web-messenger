from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent

source = OVERLAY / "RoofNewChatSearch.ts"
target = ROOT / "src/lib/roof/RoofNewChatSearch.ts"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

path = ROOT / "src/components/sidebarLeft/index.ts"
text = path.read_text(encoding="utf-8")

import_line = "import {openRoofNewChatSearch} from '@lib/roof/RoofNewChatSearch';\n"
if import_line not in text:
    marker = "import {openEmojiStatusPicker} from '@components/sidebarLeft/emojiStatusPicker';\n"
    if marker not in text:
        raise SystemExit("[Roof sidebar patch] import marker missing")
    text = text.replace(marker, marker + import_line, 1)

# Replace only the New Private Chat action. Group and Channel continue to use
# TWeb's mature native creation screens, while direct chat is Roof username-only.
old_contacts = """    const onContactsClick = () => {\n      closeTabsBefore(() => {\n        this.createTab(AppContactsTab).open();\n      });\n    };\n"""
new_contacts = """    const onContactsClick = () => {\n      closeTabsBefore(() => {\n        openRoofNewChatSearch();\n      });\n    };\n"""
if new_contacts not in text:
    if old_contacts not in text:
        raise SystemExit("[Roof sidebar patch] private chat action marker missing")
    text = text.replace(old_contacts, new_contacts, 1)

# Make the three actions explicit Roof wording rather than inherited Telegram
# lang-pack strings. regularText is supported by ButtonMenu options.
old_return = """    return [{\n      icon: 'newchannel',\n      text: singular ? 'Channel' : 'NewChannel',\n      onClick: () => {\n        closeTabsBefore(() => {\n          this.createTab(AppNewChannelTab).open({});\n        });\n      }\n    }, {\n      icon: 'newgroup',\n      text: singular ? 'Group' : 'NewGroup',\n      onClick: onNewGroupClick\n    }, {\n      icon: 'newprivate',\n      text: singular ? 'PrivateChat' : 'NewPrivateChat',\n      onClick: onContactsClick\n    }];\n"""
new_return = """    return [{\n      icon: 'newprivate',\n      regularText: 'Новый чат',\n      onClick: onContactsClick\n    }, {\n      icon: 'newgroup',\n      regularText: 'Группа',\n      onClick: onNewGroupClick\n    }, {\n      icon: 'newchannel',\n      regularText: 'Канал',\n      onClick: () => {\n        closeTabsBefore(() => {\n          this.createTab(AppNewChannelTab).open({});\n        });\n      }\n    }];\n"""
if new_return not in text:
    if old_return not in text:
        raise SystemExit("[Roof sidebar patch] new-chat menu block missing")
    text = text.replace(old_return, new_return, 1)

# Search field should clearly communicate Roof's identity search rule.
old_placeholder = "    (this.inputSearch.input as HTMLInputElement).placeholder = ' ';\n"
new_placeholder = "    (this.inputSearch.input as HTMLInputElement).placeholder = 'Поиск @username или сообщений';\n"
if old_placeholder in text:
    text = text.replace(old_placeholder, new_placeholder, 1)

path.write_text(text, encoding="utf-8")

check = path.read_text(encoding="utf-8")
for needle in (
    "openRoofNewChatSearch",
    "regularText: 'Новый чат'",
    "regularText: 'Группа'",
    "regularText: 'Канал'",
    "Поиск @username или сообщений",
):
    if needle not in check:
        raise SystemExit(f"[Roof sidebar patch] verification failed: {needle}")

print("[Roof sidebar patch] username new-chat search and 3-action compose menu installed")
