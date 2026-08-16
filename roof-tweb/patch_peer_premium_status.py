from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
path = ROOT / "src/components/generateTitleIcons.ts"
text = path.read_text(encoding="utf-8")

helper_import = (
    "import {invalidateRoofPeerProfileExtras, mountRoofPeerTitleStatus} "
    "from '@lib/roof/RoofPremiumEmojiPacks';\n"
)
transport_import = "import roofTransport from '@lib/roof/roofTransport';\n"
if helper_import not in text:
    marker = "import wrapEmojiStatus from '@components/wrappers/emojiStatus';\n"
    if marker not in text:
        raise SystemExit("[Roof peer status patch] import marker missing")
    text = text.replace(marker, marker + helper_import + transport_import, 1)

peer_guard = """  if(!peer) {\n    return {elements};\n  }\n\n"""
roof_block = """  if(!peer) {\n    return {elements};\n  }\n\n  // Roof user Premium/status icons are loaded from the local Roof backend, not\n  // from Telegram custom-emoji document ids. generateTitleIcons is shared by\n  // dialog rows, chat topbar and peer/profile titles, so this single hook keeps\n  // every title surface consistent.\n  if(peer._ === 'user' && !noPremiumIcon && wrapOptions?.middleware) {\n    const roofStatus = document.createElement('span');\n    roofStatus.classList.add('roof-peer-title-status', 'hide');\n\n    const refreshRoofStatus = async(force = false) => {\n      try {\n        const visible = await mountRoofPeerTitleStatus(roofStatus, Number(peerId), 20, force);\n        roofStatus.classList.toggle('hide', !visible);\n        return visible;\n      } catch(error) {\n        roofStatus.classList.add('hide');\n        console.warn('Roof peer premium status failed', error);\n        return false;\n      }\n    };\n\n    await refreshRoofStatus();\n    if(!wrapOptions.middleware()) return {elements};\n    // Always keep the element in the title. When the user changes status via\n    // WebSocket we can unhide/remount it immediately without requiring TWeb to\n    // reconstruct the dialog row/topbar/profile title first.\n    elements.push(roofStatus);\n\n    const detachRoofUpdate = roofTransport.onUpdate((update: any) => {\n      if(update?._ !== 'roofUpdateEmojiStatus' || Number(update.user_id) !== Number(peerId)) return;\n      invalidateRoofPeerProfileExtras(Number(peerId));\n      void refreshRoofStatus(true);\n    });\n    wrapOptions.middleware.onDestroy(detachRoofUpdate);\n  }\n\n"""
if roof_block not in text:
    if peer_guard not in text:
        raise SystemExit("[Roof peer status patch] peer guard missing")
    text = text.replace(peer_guard, roof_block, 1)

# Telegram user premium/custom emoji must not be rendered in parallel with Roof.
old_premium = "  if(!noPremiumIcon && wrapOptions?.middleware) {\n"
new_premium = "  if(!noPremiumIcon && wrapOptions?.middleware && peer._ !== 'user') {\n"
if new_premium not in text:
    if old_premium not in text:
        raise SystemExit("[Roof peer status patch] premium block missing")
    text = text.replace(old_premium, new_premium, 1)

path.write_text(text, encoding="utf-8")
check = path.read_text(encoding="utf-8")
for needle in (
    "mountRoofPeerTitleStatus",
    "roofTransport.onUpdate",
    "peer._ !== 'user'",
    "elements.push(roofStatus)",
    "roof-peer-title-status",
):
    if needle not in check:
        raise SystemExit(f"[Roof peer status patch] verification failed: {needle}")

print("[Roof peer status patch] animated Roof status installed for dialogs, topbar and peer profiles")
