from pathlib import Path
import sys

root = Path(sys.argv[1])
chat = root / 'src/components/chat/chat.ts'
text = chat.read_text(encoding='utf-8')
needle = "import {installRoofVoiceRecorder} from '@lib/roof/RoofVoiceRecorder';"
if needle in text and "saveRoofMessage" not in text:
    text = text.replace(needle, needle + "\nimport {saveRoofMessage} from '@lib/roof/RoofSavedMessages';")
chat.write_text(text, encoding='utf-8')

# Add a Saved Messages shortcut to the sidebar menu using a small independent
# DOM hook. This avoids coupling Roof storage to Telegram cloud Saved Messages.
sidebar = root / 'src/components/sidebarLeft/index.ts'
if sidebar.exists():
    value = sidebar.read_text(encoding='utf-8')
    marker = "import {openRoofNewChatSearch} from '@lib/roof/RoofNewChatSearch';"
    if marker in value and 'openRoofSavedMessages' not in value:
        value = value.replace(marker, marker + "\nimport {openRoofSavedMessages} from '@lib/roof/RoofSavedMessages';")
    sidebar.write_text(value, encoding='utf-8')
