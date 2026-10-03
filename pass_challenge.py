"""Passes the Cloudflare challenge page ("Just a moment...") in front of TARGET_URL with
ZeroCaptcha, then opens the page in Chrome through the same proxy, with the cf_clearance cookie and
the user agent it is bound to:

    ZEROCAPTCHA_API=https://api.zerocaptcha.io ZEROCAPTCHA_KEY=zc_live_... \\
        PROXY_URL=http://proxy.example.net:8080 \\
        TARGET_URL=https://your-site.example/ python pass_challenge.py

Chrome takes a proxy's host and port only, so use a proxy that lets your IP address in without a
password. HEADED=1 shows the browser. Use it only on sites you own or are allowed to automate.
"""

import os
import sys

from flows import chrome, open_with_clearance
from zerocaptcha_client import ZeroCaptcha


def main() -> int:
    target, proxy = os.environ.get("TARGET_URL"), os.environ.get("PROXY_URL")
    if not target or not proxy:
        print("Set TARGET_URL to the page behind the challenge and PROXY_URL to your proxy.", file=sys.stderr)
        return 2
    clearance = ZeroCaptcha().solve_challenge(target, proxy)
    driver = chrome(proxy, clearance["user_agent"], headless=os.environ.get("HEADED") != "1")
    try:
        open_with_clearance(driver, target, clearance)
        print(f"{driver.current_url}: {driver.title}")
    finally:
        driver.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
