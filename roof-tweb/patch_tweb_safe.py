from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent
LANG = ROOT / "src/lang.ts"


def split_key(line: str) -> tuple[str, str, str]:
    head, sep, tail = line.partition(":")
    return head, sep, tail


original_lines = LANG.read_text(encoding="utf-8").splitlines(keepends=True)
subprocess.check_call([sys.executable, str(OVERLAY / "patch_tweb.py"), str(ROOT)])
patched_lines = LANG.read_text(encoding="utf-8").splitlines(keepends=True)

if len(original_lines) != len(patched_lines):
    raise SystemExit("[Roof safe patch] lang.ts line count changed unexpectedly")

fixed: list[str] = []
for original, patched in zip(original_lines, patched_lines, strict=True):
    original_head, original_sep, _ = split_key(original)
    patched_head, patched_sep, patched_tail = split_key(patched)

    # Keep every TWeb LangPack identifier byte-for-byte from upstream. Only the
    # human-visible value to the right of ':' is allowed to carry Roof branding.
    if original_sep and patched_sep:
        fixed.append(original_head + original_sep + patched_tail)
    else:
        fixed.append(patched)

LANG.write_text("".join(fixed), encoding="utf-8")

# Guard against the exact regression that broke the previous build.
source = LANG.read_text(encoding="utf-8")
for key in (
    "'Telegram.LanguageViewController'",
    "'Telegram.GeneralSettingsViewController'",
    "'MenuTelegramStars'",
    "'MenuTelegramStarsTon'",
):
    if key not in source:
        raise SystemExit(f"[Roof safe patch] upstream LangPack key was renamed: {key}")

print("[Roof safe patch] visible branding changed; upstream LangPack keys preserved")
