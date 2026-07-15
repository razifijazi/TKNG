# TKNG — TokenGO Auto Register

Playwright-based auto-registration + API key creation for TokenGO.

## Setup

```bash
pip install playwright
playwright install chromium
```

## Usage

1. Edit `email.txt` — add accounts (format: `email|password`)
2. (Optional) Edit `proxies.txt` — add proxies (format: `host:port:user:pass`)
3. Run:
```bash
python3 register_batch.py
```
4. Choose proxy on/off when prompted

## Output

- `accounts.txt` — all results (`email|password|apikey`)
- `used.txt` — successful registrations (moved from email.txt)
- `photo/` — screenshots per run

## Proxy Formats

```
# Static
1.2.3.4:8080:user1:pass1

# Rotating (same format, provider rotates IP)
gateway.provider.com:20000:user1:pass1
```
