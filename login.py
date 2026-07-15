#!/usr/bin/env python3
"""
TokenGO Login + Get API Key
Input: email|password (args or email.txt)
Output: email|password|apikey → accounts.txt
"""

import time, sys, re
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
EMAIL_FILE = BASE_DIR / "email.txt"
RESULT_FILE = BASE_DIR / "accounts.txt"
USED_FILE = BASE_DIR / "used.txt"
FAILED_FILE = BASE_DIR / "failed.txt"
PROXY_FILE = BASE_DIR / "proxies.txt"
LOGIN_URL = "https://dashboard.tokengo.com/sign-in"

G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
C = "\033[96m"
B = "\033[1m"
D = "\033[0m"

def ss(page, name):
    (BASE_DIR / "photo").mkdir(exist_ok=True)
    page.screenshot(path=str(BASE_DIR / "photo" / f"{name}.png"), full_page=True)

def log(tag, msg, color=D):
    print(f"{color}{tag}{D} {msg}")

def load_accounts():
    accounts = []
    for line in EMAIL_FILE.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts

def load_done():
    done = set()
    if RESULT_FILE.exists():
        for line in RESULT_FILE.read_text().strip().splitlines():
            parts = line.split("|")
            if len(parts) >= 3:
                status = parts[2].strip()
                if not any(status.startswith(x) for x in ("ERROR", "LOGIN_FAILED", "EXTRACT_FAILED")):
                    done.add(parts[0].strip())
    return done

def load_proxies():
    proxies = []
    if not PROXY_FILE.exists():
        return proxies
    for line in PROXY_FILE.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) >= 4:
            proxies.append({
                "server": f"http://{parts[0]}:{parts[1]}",
                "username": parts[2],
                "password": parts[3],
            })
        elif len(parts) == 2:
            proxies.append({"server": f"http://{parts[0]}:{parts[1]}"})
    return proxies

def move_to_used(email):
    lines = EMAIL_FILE.read_text().strip().splitlines()
    kept, moved = [], None
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and s.split("|")[0].strip() == email:
            moved = s
        else:
            kept.append(line)
    if moved:
        EMAIL_FILE.write_text("\n".join(kept) + "\n")
        with open(USED_FILE, "a") as f:
            f.write(moved + "\n")

def login_and_get_key(ctx, email, password, idx, total):
    t = f"[{idx}/{total}]"
    log(t, f"{B}{email}{D}", C)
    page = ctx.new_page()

    try:
        # Login
        log(t, "  Login...", Y)
        page.goto(LOGIN_URL, wait_until="networkidle")
        time.sleep(2)

        # Click Google — could open popup or navigate same tab
        popup = None
        try:
            with page.expect_popup(timeout=5000) as popup_info:
                page.click("button:has-text('Google')")
            popup = popup_info.value
            popup.wait_for_load_state("networkidle")
        except:
            # No popup — maybe same tab navigated to Google
            time.sleep(2)
            if "accounts.google.com" in page.url:
                popup = page

        if not popup:
            log(t, "  Google button failed", R)
            ss(page, f"l{idx:02d}_fail")
            return email, password, "LOGIN_FAILED"

        target = popup

        target.wait_for_selector("#identifierId", state="visible", timeout=20000)
        target.fill("#identifierId", email)
        target.click("#identifierNext")
        target.wait_for_load_state("networkidle")
        time.sleep(3)

        sel = 'input[name="Passwd"]:not([aria-hidden="true"])'
        target.wait_for_selector(sel, state="visible", timeout=20000)
        target.fill(sel, password)
        target.click("#passwordNext")
        target.wait_for_load_state("networkidle")
        time.sleep(3)

        # GSuite speedbump
        try:
            b = target.locator("button:has-text('I understand')")
            b.wait_for(state="visible", timeout=5000)
            b.click()
            target.wait_for_load_state("networkidle")
            time.sleep(2)
        except:
            pass

        # OAuth consent
        if "signin/oauth/id" in target.url or "oauth/consent" in target.url:
            log(t, "  OAuth consent...", Y)
            try:
                time.sleep(2)
                cont = target.locator("button:has-text('Continue')")
                cont.wait_for(state="visible", timeout=15000)
                cont.click()
                target.wait_for_load_state("networkidle")
                time.sleep(5)
            except:
                try:
                    target.reload(wait_until="networkidle")
                    time.sleep(3)
                    cont = target.locator("button:has-text('Continue')")
                    cont.wait_for(state="visible", timeout=10000)
                    cont.click()
                    target.wait_for_load_state("networkidle")
                    time.sleep(5)
                except:
                    pass

        # Wait for popup to close
        if popup != page:
            try:
                popup.wait_for_event("close", timeout=15000)
            except:
                pass
            time.sleep(2)

        # Verify
        if "tokengo" not in page.url:
            log(t, f"  LOGIN FAILED", R)
            ss(page, f"l{idx:02d}_fail")
            return email, password, "LOGIN_FAILED"

        log(t, "  Logged in OK", G)

        # API Keys
        log(t, "  /api-keys...", Y)
        page.goto("https://dashboard.tokengo.com/api-keys", wait_until="networkidle")
        time.sleep(2)

        body = page.inner_text("body")
        if "auto-key" not in body:
            log(t, "  Create key...", Y)
            page.locator("button:has-text('New API Key')").click()
            time.sleep(2)
            page.locator("input").first.fill("auto-key")
            try:
                page.locator("button:has-text('Create')").click()
            except:
                page.locator("button[type='submit']").click()
            time.sleep(3)
            page.reload(wait_until="networkidle")
            time.sleep(3)

        # Reveal key via eye icon, then read from page text
        log(t, "  Reveal + extract...", Y)
        apikey = None
        try:
            row = page.locator("tr:has-text('auto-key')")
            eye = row.locator("button").first
            eye.click()
            time.sleep(2)
        except Exception as e:
            log(t, f"  Reveal error: {e}", Y)

        # Extract revealed key from page text
        body = page.inner_text("body")
        for pat in [r'(tk-[\w-]+)', r'(sk-[\w-]+)', r'(tgk-[\w-]+)', r'(0[\w]{40,})', r'([\w]{40,})']:
            m = re.findall(pat, body)
            if m:
                for k in m:
                    if len(k) > 20 and "auto" not in k.lower() and "tokengo" not in k.lower():
                        apikey = k
                        break
                if apikey:
                    break

        ss(page, f"l{idx:02d}_done")

        if not apikey:
            log(t, "  EXTRACT FAILED", R)
            return email, password, "EXTRACT_FAILED"

        log(t, f"  API Key: {G}{apikey}{D}", G)
        return email, password, apikey

    except Exception as e:
        log(t, f"  ERROR: {e}", R)
        try:
            ss(page, f"l{idx:02d}_err")
        except:
            pass
        return email, password, f"ERROR:{str(e)[:80]}"
    finally:
        page.close()


def main():
    # Single account from args
    if len(sys.argv) >= 3:
        email, password = sys.argv[1], sys.argv[2]
        accounts = [(email, password)]
    else:
        accounts = load_accounts()

    if not accounts:
        log("!", "email.txt kosong atau ga ada args!", R)
        print(f"  Usage: python3 login.py email@domain.com password")
        print(f"  Atau isi email.txt lalu: python3 login.py")
        return

    done = load_done()
    todo = [(e, p) for e, p in accounts if e not in done]
    if not todo:
        log("!", "Semua akun sudah diproses!", G)
        return

    proxies = load_proxies()

    print(f"\n{B}{'='*55}{D}")
    print(f"  {C}TKNG Login + Get API Key{D}")
    print(f"  Accounts : {B}{len(todo)}{D} baru ({len(done)} selesai)")
    print(f"  Proxies  : {B}{len(proxies)}{D} tersedia")
    print(f"{B}{'='*55}{D}\n")

    use_proxy = False
    if proxies:
        ans = input(f"  {Y}Gunakan proxy? (y/n) [n]:{D} ").strip().lower()
        use_proxy = ans in ("y", "yes")
        if use_proxy:
            # Check proxy IP via curl
            log("", "  Checking proxy...", Y)
            import urllib.request, json as _json
            px = proxies[0]
            proxy_url = px["server"].replace("http://", "")
            if "username" in px:
                proxy_url = f"http://{px['username']}:{px['password']}@{proxy_url}"
            try:
                handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
                opener = urllib.request.build_opener(handler)
                resp = opener.open("https://ipinfo.io/json", timeout=10)
                info = _json.loads(resp.read())
                log("", f"  Proxy: {G}{info.get('ip','?')} ({info.get('country','?')}) {info.get('city','?')}{D}", G)
            except Exception as e:
                log("", f"  Proxy check failed: {e}", R)
                ans = input(f"  {Y}Tetap lanjut? (y/n) [n]:{D} ").strip().lower()
                use_proxy = ans in ("y", "yes")
        print(f"  {'Proxy ON' if use_proxy else 'Proxy OFF'}\n")
    else:
        print(f"  {Y}proxies.txt kosong, jalan tanpa proxy{D}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ])

        results = []
        for i, (email, password) in enumerate(todo, 1):
            proxy_cfg = None
            if use_proxy and proxies:
                proxy_cfg = proxies[(i - 1) % len(proxies)]

            ctx_opts = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            }
            if proxy_cfg:
                ctx_opts["proxy"] = proxy_cfg

            ctx = browser.new_context(**ctx_opts)
            result = login_and_get_key(ctx, email, password, i, len(todo))
            results.append(result)
            ctx.close()

            is_fail = any(result[2].startswith(x) for x in ("ERROR", "LOGIN_FAILED", "EXTRACT_FAILED"))
            with open(FAILED_FILE if is_fail else RESULT_FILE, "a") as f:
                f.write(f"{result[0]}|{result[1]}|{result[2]}\n")
            if not is_fail:
                move_to_used(result[0])


            if i < len(todo):
                time.sleep(5)

        browser.close()

    ok = sum(1 for _, _, k in results if not any(k.startswith(x) for x in ("ERROR", "LOGIN_FAILED", "EXTRACT_FAILED")))
    fail = len(results) - ok
    print(f"\n{B}{'='*55}{D}")
    print(f"  {G}DONE{D}  {G}{ok} sukses{D}  {R}{fail} gagal{D}" if fail else f"  {G}DONE  {ok} sukses{D}")
    print(f"{B}{'='*55}{D}")
    for e, pw, k in results:
        if any(k.startswith(x) for x in ("ERROR", "LOGIN_FAILED", "EXTRACT_FAILED")):
            print(f"  {R}FAIL{D}  {e}  →  {R}{k}{D}")
        else:
            print(f"  {G} OK {D}  {e}  →  {G}{k}{D}")
    print(f"\n  Saved: {RESULT_FILE}\n")


if __name__ == "__main__":
    main()
