"""Opens TARGET_URL in Chrome, solves its Cloudflare Turnstile widget with ZeroCaptcha, fills the
token in, submits the form and prints where it landed:

    ZEROCAPTCHA_API=https://api.zerocaptcha.io ZEROCAPTCHA_KEY=zc_live_... \\
        TARGET_URL=https://your-site.example/login python solve_turnstile.py

HEADED=1 shows the browser. Use it only on pages you own or are allowed to automate.
"""

import os
import sys

from flows import chrome, solve_and_submit
from zerocaptcha_client import ZeroCaptcha


def main() -> int:
    target = os.environ.get("TARGET_URL")
    if not target:
        print("Set TARGET_URL to the page with the Cloudflare Turnstile widget.", file=sys.stderr)
        return 2
    client = ZeroCaptcha()
    driver = chrome(headless=os.environ.get("HEADED") != "1")
    try:
        driver.get(target)
        solve_and_submit(driver, client)
        print(f"Submitted. Now on {driver.current_url}: {driver.title}")
    finally:
        driver.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
