from __future__ import annotations

import html
import json
import re
import struct
import sys
from pathlib import Path


if len(sys.argv) != 5:
    raise SystemExit(
        "usage: generate_telegram_emoji_atlas.py <atlas.htm> <emoji_autocomplete.json> <emj.png> <output.ts>"
    )

atlas_path = Path(sys.argv[1])
autocomplete_path = Path(sys.argv[2])
png_path = Path(sys.argv[3])
out_path = Path(sys.argv[4])

atlas_text = atlas_path.read_text(encoding="utf-8", errors="replace")
autocomplete = json.loads(autocomplete_path.read_text(encoding="utf-8"))

row_re = re.compile(
    r"background-position:\s*(-?\d+)px\s+(-?\d+)px.*?<strong>(.*?)</strong>",
    re.IGNORECASE | re.DOTALL,
)
code_re = re.compile(r":[a-zA-Z0-9_+\-]+:")
alpha_to_position: dict[str, tuple[int, int]] = {}
for match in row_re.finditer(atlas_text):
    x = abs(int(match.group(1)))
    y = abs(int(match.group(2)))
    codes = code_re.findall(html.unescape(match.group(3)))
    for code in codes:
        alpha_to_position.setdefault(code, (x, y))

if len(alpha_to_position) < 500:
    raise SystemExit(f"telegram emoji atlas parse looks incomplete: {len(alpha_to_position)} codes")

png = png_path.read_bytes()
if png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
    raise SystemExit("emj.png is not a valid PNG")
width, height = struct.unpack(">II", png[16:24])
cell = 45

unicode_to_position: dict[str, tuple[int, int]] = {}
for input_code, data in autocomplete.items():
    if not isinstance(data, dict):
        continue

    alpha_codes: list[str] = []
    for raw in (data.get("alpha_code"), data.get("aliases")):
        if raw:
            alpha_codes.extend(code_re.findall(str(raw)))
    position = next((alpha_to_position[code] for code in alpha_codes if code in alpha_to_position), None)
    if position is None:
        continue

    output_code = str(data.get("output") or input_code).lower()
    for key in {str(input_code).lower(), output_code}:
        unicode_to_position.setdefault(key, position)
        unicode_to_position.setdefault(key.replace("-fe0f", ""), position)

if len(unicode_to_position) < 500:
    raise SystemExit(f"telegram emoji unicode mapping looks incomplete: {len(unicode_to_position)} entries")

mapping_json = json.dumps(
    {key: [value[0], value[1]] for key, value in sorted(unicode_to_position.items())},
    ensure_ascii=False,
    separators=(",", ":"),
)

bg_width = (width / cell) * 100
bg_height = (height / cell) * 100

source = f"""// Generated from k3a/telegram-emoji-list (GPL-3.0).
// Do not edit by hand. The source sprite is copied to /assets/roof-emoji/emj.png.
const CELL = {cell};
const ATLAS_WIDTH = {width};
const ATLAS_HEIGHT = {height};
const BG_WIDTH = '{bg_width:.8f}%';
const BG_HEIGHT = '{bg_height:.8f}%';
const MAP: Record<string, [number, number]> = {mapping_json};

function normalizeUnicodeKey(value: string): string {{
  return String(value || '').toLowerCase().replace(/_/g, '-');
}}

export function applyRoofTelegramEmoji(element: HTMLElement, unicode: string, text: string): boolean {{
  const key = normalizeUnicodeKey(unicode);
  const position = MAP[key] || MAP[key.replace(/-fe0f/g, '')];
  if(!position) return false;

  const [x, y] = position;
  element.classList.add('emoji', 'roof-telegram-emoji');
  element.dataset.roofEmojiUnicode = key;
  element.setAttribute('aria-label', text);
  element.setAttribute('role', 'img');
  element.style.setProperty('--roof-emoji-bg-width', BG_WIDTH);
  element.style.setProperty('--roof-emoji-bg-height', BG_HEIGHT);
  element.style.setProperty('--roof-emoji-x-percent', String(ATLAS_WIDTH === CELL ? 0 : (x / (ATLAS_WIDTH - CELL)) * 100) + '%');
  element.style.setProperty('--roof-emoji-y-percent', String(ATLAS_HEIGHT === CELL ? 0 : (y / (ATLAS_HEIGHT - CELL)) * 100) + '%');
  return true;
}}
"""

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(source, encoding="utf-8")
print(
    f"[Roof emoji atlas] generated {len(unicode_to_position)} mappings from {len(alpha_to_position)} atlas codes ({width}x{height})"
)
