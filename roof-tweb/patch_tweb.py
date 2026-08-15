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
    replacement = """  public invokeApi<T extends keyof MethodDeclMap>(method: T, params: MethodDeclMap[T]['req'] = {}, options: InvokeApiOptions = {}): CancellablePromise<MethodDeclMap[T]['res']> {\n    return roofTransport.invoke(method as string, params as any, options as any) as CancellablePromise<MethodDeclMap[T]['res']>;\n  }"""
    text = text[:start] + replacement + text[class_end:]
    path.write_text(text, encoding="utf-8")


def disable_mtproto_network() -> None:
    path = ROOT / "src/lib/mtproto/dcConfigurator.ts"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"export function constructTelegramWebSocketUrl\([^)]*\) \{.*?\n\}", re.DOTALL)
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
    text = replace_method(text, "  public chooseServer(", """  public chooseServer(\n    _dcId: DcId,\n    _connectionType: ConnectionType = 'client',\n    _transportType: TransportType = Modes.transport,\n    _reuse = true,\n    _premium?: boolean\n  ): MTTransport {\n    throw new Error('ROOF_MTPROTO_DISABLED');\n  }""")
    text = text.replace("web.telegram.org", "roof-network-disabled.invalid")
    text = re.sub(r"149\.154\.(?:167|171|175)\.\d+", "0.0.0.0", text)
    path.write_text(text, encoding="utf-8")


def fix_roof_connection_status() -> None:
    path = ROOT / "src/components/connectionStatus.ts"
    text = path.read_text(encoding="utf-8")
    if "const NO_STATUS = false;" not in text:
        fail("connectionStatus NO_STATUS flag not found")
    path.write_text(text.replace("const NO_STATUS = false;", "const NO_STATUS = true;", 1), encoding="utf-8")


def fix_roof_auth_bootstrap() -> None:
    path = ROOT / "src/index.ts"
    text = path.read_text(encoding="utf-8")
    needle = "  let authState = stateResult.state.authState;\n"
    replacement = """  let authState = stateResult.state.authState;\n\n  let roofAccessToken: string | null = null;\n  try {\n    roofAccessToken = localStorage.getItem('roof_access_token');\n  } catch {}\n  if(!roofAccessToken) {\n    authState = {_: 'authStateSignIn'};\n  }\n"""
    if needle not in text:
        fail("index authState bootstrap not found")
    path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")


def expire_invalid_roof_token() -> None:
    path = ROOT / "src/lib/roof/roofTransport.ts"
    text = path.read_text(encoding="utf-8")
    needle = """    if(!response.ok) {\n      let detail = response.statusText;"""
    replacement = """    if(!response.ok) {\n      if(response.status === 401 && token && !path.startsWith('/auth/')) {\n        this.setToken(null);\n        globalThis.setTimeout(() => globalThis.location?.reload(), 0);\n      }\n      let detail = response.statusText;"""
    if needle not in text:
        fail("roofTransport HTTP error block not found")
    path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")


def patch_edit_profile() -> None:
    path = ROOT / "src/components/sidebarLeft/tabs/editProfile.tsx"
    text = path.read_text(encoding="utf-8")

    text = text.replace("import {purchaseUsernameCaption} from '@components/sidebarLeft/tabs/purchaseUsernameCaption';\n", "")
    text = text.replace("import UsernamesSection from '@components/usernamesSection';\n", "")

    marker = "type FocusKey = typeof FOCUS_KEYS[number];\n"
    insert = """type FocusKey = typeof FOCUS_KEYS[number];\n\nconst ROOF_PREMIUM_STATUSES = ['😂', '❤️', '🔥', '👍', '💯', '😁', '😎', '👑', '⚡', '💜', '🖤', '🚀'];\n"""
    if marker not in text:
        fail("editProfile status marker not found")
    text = text.replace(marker, insert, 1)

    purchase = """  const {setUsername: setPurchaseUsername, element: purchaseEl} = purchaseUsernameCaption();\n"""
    replacement = """  const setPurchaseUsername = (_username: string) => {};\n  const purchaseEl = document.createElement('div');\n  purchaseEl.classList.add('hide');\n\n  const [roofStatus, setRoofStatus] = createSignal('');\n  const [roofPremium, setRoofPremium] = createSignal(false);\n  const [roofStars, setRoofStars] = createSignal(0);\n\n  const refreshRoofExtras = () => (tab.managers.apiManager as any).invokeApi('roof.getProfileExtras', {})\n  .then((extras: any) => {\n    setRoofStatus(String(extras?.emoji_status || ''));\n    setRoofPremium(!!extras?.premium);\n    setRoofStars(Number(extras?.stars || 0));\n  })\n  .catch(() => {});\n\n  const chooseRoofStatus = (emoji: string) => {\n    (tab.managers.apiManager as any).invokeApi('roof.updateEmojiStatus', {emoji})\n    .then((extras: any) => {\n      setRoofStatus(String(extras?.emoji_status || ''));\n      setRoofPremium(!!extras?.premium);\n      setRoofStars(Number(extras?.stars || 0));\n    })\n    .catch((err: any) => console.error('Roof emoji status error:', err));\n  };\n\n  refreshRoofExtras();\n"""
    if purchase not in text:
        fail("editProfile purchase caption block not found")
    text = text.replace(purchase, replacement, 1)

    # Extra Telegram username-management section is not part of Roof accounts.
    text = re.sub(
        r"\n\s*\{\(\(\) => \{\n\s*const section = new UsernamesSection\(\{.*?\n\s*\}\)\(\)\}\n",
        "\n",
        text,
        count=1,
        flags=re.DOTALL,
    )

    anchor = """      <UsernameSection\n        user={user}\n        editPeer={editPeer}\n        purchaseEl={purchaseEl}\n        onPurchaseUsernameChange={setPurchaseUsername}\n        usernameInputFieldRef={(ref) => {\n          usernameInputField = ref;\n          trackInputField(ref);\n        }}\n      />\n"""
    status_ui = anchor + """\n      <Section>\n        <div class=\"roof-profile-premium-head\">\n          <div>\n            <div class=\"roof-profile-premium-title\">Roof Premium статус</div>\n            <div class=\"roof-profile-premium-caption\">\n              {roofPremium() ? `Premium активен · ${roofStars()} Roof Stars` : `${roofStars()} Roof Stars`}\n            </div>\n          </div>\n          <span class=\"roof-premium-badge\">★</span>\n        </div>\n        <div class=\"roof-status-grid\">\n          {ROOF_PREMIUM_STATUSES.map((emoji) => (\n            <button\n              type=\"button\"\n              class={`roof-status-button${roofStatus() === emoji ? ' is-selected' : ''}`}\n              onClick={() => chooseRoofStatus(emoji)}\n              title={`Roof Premium статус ${emoji}`}\n            >\n              {emoji}\n            </button>\n          ))}\n          <button\n            type=\"button\"\n            class={`roof-status-button roof-status-clear${!roofStatus() ? ' is-selected' : ''}`}\n            onClick={() => chooseRoofStatus('')}\n            title=\"Убрать статус\"\n          >\n            ×\n          </button>\n        </div>\n      </Section>\n"""
    if anchor not in text:
        fail("editProfile username section anchor not found")
    text = text.replace(anchor, status_ui, 1)
    path.write_text(text, encoding="utf-8")


def strip_entry_branding() -> None:
    vite_path = ROOT / "vite.config.ts"
    vite = vite_path.read_text(encoding="utf-8")
    vite = vite.replace("title: 'Telegram Web'", "title: 'Roof'")
    vite = vite.replace("description: 'Telegram is a cloud-based mobile and desktop messaging app with a focus on security and speed.'", "description: 'Roof is a private messaging app powered entirely by Roof infrastructure.'")
    vite = vite.replace("url: 'https://web.telegram.org/k/'", "url: 'https://roof.local/'")
    vite = vite.replace("origin: 'https://web.telegram.org/'", "origin: 'https://roof.local/'")
    vite_path.write_text(vite, encoding="utf-8")

    lang_path = ROOT / "src/lang.ts"
    if lang_path.exists():
        lang = lang_path.read_text(encoding="utf-8")
        lang = lang.replace("Telegram Premium", "Roof Premium")
        lang = lang.replace("Telegram Stars", "Roof Stars")
        lang = lang.replace("Telegram", "Roof")
        lang = lang.replace("https://t.me/", "https://roof.local/")
        lang = lang.replace("https://telegram.org/", "https://roof.local/")
        lang_path.write_text(lang, encoding="utf-8")

    for relative in ("index.html", "public/index.html", "public/manifest.json", "public/site.webmanifest"):
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
    status = (ROOT / "src/components/connectionStatus.ts").read_text(encoding="utf-8")
    index = (ROOT / "src/index.ts").read_text(encoding="utf-8")
    transport = (ROOT / "src/lib/roof/roofTransport.ts").read_text(encoding="utf-8")
    settings = (ROOT / "src/components/sidebarLeft/tabs/settings.tsx").read_text(encoding="utf-8")
    profile = (ROOT / "src/components/sidebarLeft/tabs/editProfile.tsx").read_text(encoding="utf-8")
    if "cachedNetworker.wrapApiCall(method, params, options)" in api:
        fail("MTProto invoke fallback remains")
    if "roofTransport.invoke" not in api:
        fail("Roof transport is not active")
    if "web.telegram.org" in dc:
        fail("Telegram Web endpoint remains")
    if "title: 'Roof'" not in vite:
        fail("Roof build title is not configured")
    if "const NO_STATUS = true;" not in status:
        fail("legacy MTProto connection status is still enabled")
    if "localStorage.getItem('roof_access_token')" not in index:
        fail("Roof auth bootstrap guard is missing")
    if "response.status === 401" not in transport:
        fail("Roof stale-token recovery is missing")
    if "Roof Premium" not in settings or "Roof Stars" not in settings:
        fail("Roof Premium settings UI is missing")
    if "roof.updateEmojiStatus" not in profile or "ROOF_PREMIUM_STATUSES" not in profile:
        fail("Roof Premium emoji status UI is missing")
    for prefix in ("149.154.175.", "149.154.167.", "149.154.171."):
        if prefix in dc:
            fail(f"Telegram DC address remains: {prefix}")


copy_overlay("roofTransport.ts", "src/lib/roof/roofTransport.ts")
copy_overlay("SignInCard.tsx", "src/pages/cards/SignInCard.tsx")
copy_overlay("SettingsRoof.tsx", "src/components/sidebarLeft/tabs/settings.tsx")
replace_invoke_api()
disable_mtproto_network()
fix_roof_connection_status()
fix_roof_auth_bootstrap()
expire_invalid_roof_token()
patch_edit_profile()
strip_entry_branding()
verify()
print("[Roof TWeb patch] Roof transport, Roof Premium, Stars and emoji statuses installed")
