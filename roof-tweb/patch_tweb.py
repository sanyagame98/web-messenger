from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/tweb").resolve()
OVERLAY = Path(__file__).resolve().parent


def fail(message: str) -> None:
    raise SystemExit(f"[Roof TWeb patch] {message}")


def copy_overlay(source_name: str, relative_target: str) -> None:
    source = OVERLAY / source_name
    target = ROOT / relative_target
    if not source.exists():
        fail(f"missing overlay file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def replace_method(text: str, signature: str, replacement: str) -> str:
    start = text.find(signature)
    if start < 0:
        fail(f"method not found: {signature.strip()}")

    brace = text.find(" {\n", start)
    if brace < 0:
        brace = text.find(" {\r\n", start)
    if brace < 0:
        fail("opening method brace not found")
    brace += 1

    depth = 0
    end = None
    quote: str | None = None
    escaped = False
    for index in range(brace, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        fail("closing method brace not found")
    return text[:start] + replacement + text[end:]


def replace_invoke_api() -> None:
    path = ROOT / "src/lib/appManagers/apiManager.ts"
    text = path.read_text(encoding="utf-8")
    import_line = "import roofTransport from '@lib/roof/roofTransport';\n"
    if import_line not in text:
        first_import = text.find("import ")
        if first_import < 0:
            fail("apiManager.ts has no imports")
        text = text[:first_import] + import_line + text[first_import:]

    old_updates = """  public setUpdatesProcessor(callback: (obj: any) => void) {\n    this.networkerFactory.setUpdatesProcessor(callback);\n  }"""
    new_updates = """  public setUpdatesProcessor(callback: (obj: any) => void) {\n    roofTransport.onUpdate(callback);\n    roofTransport.connectUpdates();\n  }"""
    if old_updates not in text:
        fail("setUpdatesProcessor block not found")
    text = text.replace(old_updates, new_updates, 1)

    signature = "  public invokeApi<T extends keyof MethodDeclMap>("
    start = text.find(signature)
    if start < 0:
        fail("invokeApi method not found")
    class_end = text.rfind("\n}")
    if class_end < start:
        fail("ApiManager class closing brace not found")
    replacement = """  public invokeApi<T extends keyof MethodDeclMap>(method: T, params: MethodDeclMap[T]['req'] = {}, options: InvokeApiOptions = {}): CancellablePromise<MethodDeclMap[T]['res']> {\n    // Roof-only transport. There is intentionally no MTProto fallback.\n    return roofTransport.invoke(method as string, params as any, options as any) as CancellablePromise<MethodDeclMap[T]['res']>;\n  }"""
    text = text[:start] + replacement + text[class_end:]
    path.write_text(text, encoding="utf-8")


def disable_mtproto_network() -> None:
    path = ROOT / "src/lib/mtproto/dcConfigurator.ts"
    text = path.read_text(encoding="utf-8")

    pattern = re.compile(
        r"export function constructTelegramWebSocketUrl\([^)]*\) \{.*?\n\}",
        re.DOTALL,
    )
    replacement = """export function constructTelegramWebSocketUrl(_dcId: DcId, _connectionType: ConnectionType, _premium?: boolean): string {\n  throw new Error('ROOF_MTPROTO_DISABLED');\n}"""
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        fail("could not disable WebSocket endpoint constructor")

    socket_start = text.find("  private transportSocket =")
    http_start = text.find("  private transportHTTP =")
    if min(socket_start, http_start) < 0:
        fail("transport methods not found")
    text = text[:socket_start] + """  private transportSocket = (_dcId: DcId, _connectionType: ConnectionType, _premium?: boolean): MTTransport => {\n    throw new Error('ROOF_MTPROTO_DISABLED');\n  };\n\n""" + text[http_start:]

    http_start = text.find("  private transportHTTP =")
    choose_start = text.find("  public chooseServer(")
    if min(http_start, choose_start) < 0:
        fail("HTTP/chooseServer methods not found")
    text = text[:http_start] + """  private transportHTTP = (_dcId: DcId, _connectionType: ConnectionType, _premium?: boolean): MTTransport => {\n    throw new Error('ROOF_MTPROTO_DISABLED');\n  };\n\n""" + text[choose_start:]

    choose_replacement = """  public chooseServer(\n    _dcId: DcId,\n    _connectionType: ConnectionType = 'client',\n    _transportType: TransportType = Modes.transport,\n    _reuse = true,\n    _premium?: boolean\n  ): MTTransport {\n    throw new Error('ROOF_MTPROTO_DISABLED');\n  }"""
    text = replace_method(text, "  public chooseServer(", choose_replacement)

    text = re.sub(
        r"  private sslSubdomains = \[[^\n]+\];\n\n  private dcOptions = Modes\.test \?.*?\n    \];\n\n",
        "",
        text,
        count=1,
        flags=re.DOTALL,
    )
    text = text.replace("web.telegram.org", "roof-network-disabled.invalid")
    text = re.sub(r"149\.154\.(?:167|171|175)\.\d+", "0.0.0.0", text)
    path.write_text(text, encoding="utf-8")


def strip_entry_branding() -> None:
    # Production metadata is injected from this handlebars context.
    vite_path = ROOT / "vite.config.ts"
    vite = vite_path.read_text(encoding="utf-8")
    vite = vite.replace("title: 'Telegram Web'", "title: 'Roof'")
    vite = vite.replace(
        "description: 'Telegram is a cloud-based mobile and desktop messaging app with a focus on security and speed.'",
        "description: 'Roof is a private messaging app powered entirely by Roof infrastructure.'",
    )
    # Keep absolute URLs so Vite does not interpret '/' as a directory asset.
    vite = vite.replace("url: 'https://web.telegram.org/k/'", "url: 'https://roof.local/'")
    vite = vite.replace("origin: 'https://web.telegram.org/'", "origin: 'https://roof.local/'")
    vite_path.write_text(vite, encoding="utf-8")

    for relative in (
        "index.html",
        "public/index.html",
        "public/manifest.json",
        "public/site.webmanifest",
    ):
        path = ROOT / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace("Telegram Web K", "Roof")
        text = text.replace("Telegram Web", "Roof")
        text = text.replace("Telegram", "Roof")
        path.write_text(text, encoding="utf-8")


def verify() -> None:
    api = (ROOT / "src/lib/appManagers/apiManager.ts").read_text(encoding="utf-8")
    dc = (ROOT / "src/lib/mtproto/dcConfigurator.ts").read_text(encoding="utf-8")
    vite = (ROOT / "vite.config.ts").read_text(encoding="utf-8")
    if "cachedNetworker.wrapApiCall(method, params, options)" in api:
        fail("MTProto invoke fallback remains")
    if "roofTransport.invoke" not in api:
        fail("Roof transport is not active")
    if "web.telegram.org" in dc:
        fail("Telegram Web endpoint remains")
    if "title: 'Roof'" not in vite:
        fail("Roof build title is not configured")
    for prefix in ("149.154.175.", "149.154.167.", "149.154.171."):
        if prefix in dc:
            fail(f"Telegram DC address remains: {prefix}")


copy_overlay("roofTransport.ts", "src/lib/roof/roofTransport.ts")
copy_overlay("SignInCard.tsx", "src/pages/cards/SignInCard.tsx")
replace_invoke_api()
disable_mtproto_network()
strip_entry_branding()
verify()
print("[Roof TWeb patch] Roof-only API installed; Telegram/Teamgram network disabled")
