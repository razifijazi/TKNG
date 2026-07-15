#!/usr/bin/env python3
"""
TokenGO Batch Auto-Register + API Key Creation
Reads:  email.txt     (email|password per line)
Writes: accounts.txt   (email|password|apikey per line)
Proxy:  proxies.txt    (protocol://user:pass@host:port per line)
"""

import time, sys, re, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
EMAIL_FILE = BASE_DIR / "email.txt"
RESULT_FILE = BASE_DIR / "accounts.txt"
USED_FILE = BASE_DIR / "used.txt"
PROXY_FILE = BASE_DIR / "proxies.txt"
SIGNUP_URL = "https://dashboard.tokengo.com/sign-up?aff=eIFh"


def ss(page, name):
    (BASE_DIR / "photo").mkdir(exist_ok=True)
    page.screenshot(path=str(BASE_DIR / "photo" / f"{name}.png"), full_page=True)


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
            if parts:
                done.add(parts[0].strip())
    return done


def load_proxies():
    """Load proxies from proxies.txt. Format: host:port:user:pass (one per line)"""
    proxies = []
    if not PROXY_FILE.exists():
        return proxies
    for line in PROXY_FILE.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) >= 4:
            host, port, user, pw = parts[0], parts[1], parts[2], parts[3]
            proxies.append({
                "server": f"http://{host}:{port}",
                "username": user,
                "password": pw,
            })
        elif len(parts) == 2:
            proxies.append({"server": f"http://{parts[0]}:{parts[1]}"})
    return proxies




def move_to_used(email):
    """Move email entry from email.txt to used.txt after success."""
    lines = EMAIL_FILE.read_text().strip().splitlines()
    kept = []
    moved = None
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.split("|")[0].strip() == email:
            moved = stripped
        else:
            kept.append(line)
    if moved:
        EMAIL_FILE.write_text("\n".join(kept) + "\n")
        with open(USED_FILE, "a") as f:
            f.write(moved + "\n")
    return moved

def register_one(page, email, password, idx, total):
    tag = f"[{idx}/{total}]"
    print(f"{tag} {email}")

    try:
        # --- Login ---
        print(f"{tag} Login...")
        page.goto(SIGNUP_URL, wait_until="networkidle")
        page.click("button:has-text('Gmail')")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        page.wait_for_selector("#identifierId", state="visible", timeout=15000)
        page.fill("#identifierId", email)
        page.click("#identifierNext")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        sel = 'input[name="Passwd"]:not([aria-hidden="true"])'
        page.wait_for_selector(sel, state="visible", timeout=15000)
        page.fill(sel, password)
        page.click("#passwordNext")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # GSuite speedbump
        try:
            b = page.locator("button:has-text('I understand')")
            b.wait_for(state="visible", timeout=5000)
            b.click()
            page.wait_for_load_state("networkidle")
            time.sleep(2)
        except:
            pass

        # OAuth consent
        try:
            b = page.locator("button:has-text('Continue')")
            b.wait_for(state="visible", timeout=8000)
            b.click()
            page.wait_for_load_state("networkidle")
            time.sleep(5)
        except:
            pass

        if "tokengo" not in page.url:
            print(f"{tag} LOGIN FAILED: {page.url}")
            ss(page, f"e{idx:02d}_fail")
            return email, password, "LOGIN_FAILED"
        print(f"{tag} Logged in")

        # --- API Keys ---
        print(f"{tag} /api-keys...")
        page.goto("https://dashboard.tokengo.com/api-keys", wait_until="networkidle")
        time.sleep(2)

        body = page.inner_text("body")
        if "auto-key" not in body:
            print(f"{tag} Create key...")
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

        # --- Reveal ---
        print(f"{tag} Reveal key...")
        try:
            row = page.locator("tr:has-text('auto-key')")
            row.locator("button").first.click()
            time.sleep(2)
        except:
            pass

        ss(page, f"e{idx:02d}_done")

        # --- Extract ---
        body = page.inner_text("body")
        apikey = None
        for pat in [r'(tk-[\w-]+)', r'(sk-[\w-]+)', r'(tgk-[\w-]+)', r'(0[\w]{30,})']:
            m = re.findall(pat, body)
            if m:
                for k in m:
                    if len(k) > 15 and "auto" not in k.lower():
                        apikey = k
                        break
                if apikey:
                    break

        if not apikey:
            apikey = "EXTRACT_FAILED"

        print(f"{tag} OK: {apikey[:15]}...")
        return email, password, apikey

    except Exception as e:
        traceback.print_exc()
        try:
            ss(page, f"e{idx:02d}_err")
        except:
            pass
        return email, password, f"ERROR:{str(e)[:80]}"


def main():
    accounts = load_accounts()
    if not accounts:
        print("email.txt kosong!")
        return

    done = load_done()
    todo = [(e, p) for e, p in accounts if e not in done]
    if not todo:
        print("Semua akun sudah diproses!")
        return

    # --- Proxy toggle ---
    proxies = load_proxies()
    use_proxy = False
    proxy_list = []

    print(f"\n{'='*50}")
    print(f"  Accounts: {len(todo)} baru ({len(done)} sudah selesai)")
    print(f"  Proxies:  {len(proxies)} tersedia")
    print(f"{'='*50}\n")

    if proxies:
        ans = input("Gunakan proxy? (on/off) [off]: ").strip().lower()
        use_proxy = ans in ("on", "y", "yes", "1")
        if use_proxy:
            proxy_list = proxies
            print(f"  Proxy ON - {len(proxy_list)} proxy loaded\n")
        else:
            print("  Proxy OFF\n")
    else:
        print("  proxies.txt kosong, jalan tanpa proxy\n")

    # --- Run ---
    with sync_playwright() as p:
        # Create fresh context per-account if using proxy (clean state)
        if use_proxy:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ])
        else:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ])

        results = []
        for i, (email, password) in enumerate(todo, 1):
            # Pick proxy (rotate through list)
            proxy_cfg = None
            if use_proxy and proxy_list:
                proxy_cfg = proxy_list[(i - 1) % len(proxy_list)]
                print(f"  Using proxy: {proxy_cfg['server']}")

            # Fresh context per account (isolated cookies/state)
            ctx_opts = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            }
            if proxy_cfg:
                ctx_opts["proxy"] = proxy_cfg

            ctx = browser.new_context(**ctx_opts)
            page = ctx.new_page()

            result = register_one(page, email, password, i, len(todo))
            results.append(result)

            # Append immediately
            with open(RESULT_FILE, "a") as f:
                f.write(f"{result[0]}|{result[1]}|{result[2]}\n")
            # Move to used.txt on success
            if not any(result[2].startswith(x) for x in ("ERROR", "LOGIN_FAILED", "EXTRACT_FAILED")):
                move_to_used(result[0])
                print(f"  Moved {result[0]} -> used.txt")

            ctx.close()

            if i < len(todo):
                print(f"  Wait 5s...\n")
                time.sleep(5)

        browser.close()

    # --- Summary ---
    ok = sum(1 for _, _, k in results if not any(k.startswith(x) for x in ("ERROR", "LOGIN_FAILED", "EXTRACT_FAILED")))
    fail = len(results) - ok
    print(f"\n{'='*50}")
    print(f"  DONE: {ok} sukses, {fail} gagal")
    print(f"{'='*50}")
    for e, pw, k in results:
        s = "OK" if not any(k.startswith(x) for x in ("ERROR", "LOGIN_FAILED", "EXTRACT_FAILED")) else "FAIL"
        print(f"  [{s}] {e} -> {k[:25]}")
    print(f"\n  Saved: {RESULT_FILE}")


if __name__ == "__main__":
    main()
