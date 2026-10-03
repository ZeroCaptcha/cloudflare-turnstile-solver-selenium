<!-- zc:header (generated from the registry; edit repos/registry.json) -->
# Cloudflare Turnstile and challenge pages in Selenium

[![CI](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-selenium/actions/workflows/ci.yml/badge.svg)](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-selenium/actions/workflows/ci.yml)

Solve Cloudflare Turnstile in Selenium with Python: read the widget's sitekey, get a token from the ZeroCaptcha API, fill cf-turnstile-response and submit. Also passes a Cloudflare challenge page by adding its cf_clearance cookie with the same proxy and user agent. Tested end to end.

[Website](https://zerocaptcha.io/cloudflare-turnstile-solver/selenium) · [Docs](https://zerocaptcha.io/docs) · [Quickstart](https://zerocaptcha.io/docs/quickstart) · [API reference](https://zerocaptcha.io/docs/reference/api) · [Pricing](https://zerocaptcha.io/pricing)
<!-- /zc:header -->

## What it does

Two small Selenium flows in Python, for pages you own or are allowed to automate:

- **`solve_turnstile.py`** opens a page with a Cloudflare Turnstile widget, reads its sitekey (and action and cData), gets a token from the ZeroCaptcha API, puts it in the widget's `cf-turnstile-response` field, calls the widget's callback, and submits the form.
- **`pass_challenge.py`** passes the Cloudflare challenge page ("Just a moment...") in front of a site: ZeroCaptcha solves it through your proxy and returns the `cf_clearance` cookie with the user agent it is bound to; Chrome then opens the site through the same proxy, with that cookie and that user agent.

Both are functions in `flows.py` (`solve_and_submit`, `open_with_clearance`) that take your own driver, so they drop into existing scripts and test suites. The API client in `zerocaptcha_client.py` uses the standard library only.

## Quickstart

1. Create an account on the ZeroCaptcha website, create an API key on the dashboard and add funds (crypto, from $10). A task is charged only when it succeeds.
2. Install Selenium (Python 3.10 or later, with Google Chrome; Selenium Manager fetches the matching driver), and put the API's address and your key in your environment:

   ```sh
   python -m pip install -r requirements.txt
   export ZEROCAPTCHA_API=https://api.zerocaptcha.io
   export ZEROCAPTCHA_KEY=zc_live_...
   ```

3. Solve a Cloudflare Turnstile widget and submit its form. `TARGET_URL` is the page with the widget; `HEADED=1` shows the browser:

   ```sh
   TARGET_URL=https://your-site.example/login python solve_turnstile.py
   ```

4. Or pass a Cloudflare challenge page, through your own proxy:

   ```sh
   PROXY_URL=http://proxy.example.net:8080 TARGET_URL=https://your-site.example/ python pass_challenge.py
   ```

## Use it in your own script

```python
from selenium.webdriver.common.by import By

from flows import chrome, solve_and_submit
from zerocaptcha_client import ZeroCaptcha

driver = chrome()
try:
    driver.get("https://your-site.example/login")
    driver.find_element(By.NAME, "email").send_keys("me@example.com")
    solve_and_submit(driver, ZeroCaptcha())  # reads ZEROCAPTCHA_API and ZEROCAPTCHA_KEY
    print(driver.title)
finally:
    driver.quit()
```

## How it works

**A Cloudflare Turnstile widget.** The widget is an element with `data-sitekey`, and it puts its token in a hidden `cf-turnstile-response` field of its form (or the name in `data-response-field-name`). The site sends that token to Cloudflare's siteverify when the form arrives. `solve_and_submit` asks ZeroCaptcha for a token for the page's URL and sitekey, with the widget's `data-action` and `data-cdata` when it sets them (many sites check both when they verify the token), writes it into that field with `FILL_TURNSTILE_TOKEN` (creating the field if the widget has not rendered one), calls the function named in `data-callback` if there is one, and submits. The script is plain JavaScript, so it works the same from Selenium for Java, C# or Ruby.

**A Cloudflare challenge page.** A challenge is passed once per visitor, and Cloudflare then remembers the visitor by its `cf_clearance` cookie, which works only from the same IP address and with the same user agent. So the task runs through your proxy, and Chrome is started with that proxy and that user agent (`chrome(proxy, clearance["user_agent"])`). A browser can set a cookie only for the site it is on, so `open_with_clearance` opens the site once (the challenge page answers), sets the cookie, and opens it again.

## Honest limits

- **A token works once, for 300 seconds.** Solve right before you submit; a failed submit needs a new token.
- **Chrome takes a proxy's host and port, not its password.** For challenge pages, use a proxy that lets your IP address in without a password (most providers offer an IP allowlist), or a local forwarder in front of it. The task itself can use the proxy's password.
- **Explicitly rendered widgets** (`turnstile.render(...)` with no `data-sitekey` in the page) need the sitekey, action and cData from the render call's `sitekey`, `action` and `cData` options; the [sitekey guide](https://zerocaptcha.io/guides/find-cloudflare-turnstile-sitekey) shows where to find them.
- **A clearance is bound to the proxy's IP address and the user agent,** and lasts as long as the site's Challenge Passage setting allows (30 minutes by default).
- **Only for sites you own or are allowed to automate.** The [Acceptable Use Policy](https://zerocaptcha.io/legal/acceptable-use) applies to every task.

## FAQ

**Does it work with undetected-chromedriver?**
Yes: the flows take any Selenium driver. The [undetected-chromedriver article](https://zerocaptcha.io/blog/selenium-undetected-chromedriver-cloudflare) explains what it changes and when a token or a clearance is still needed.

**Why not let the widget solve itself in the browser?**
In headless and automated browsers the widget often fails or loops; see the [headless browser article](https://zerocaptcha.io/blog/cloudflare-turnstile-headless-browser). A token from the API is used the same way the widget's own would be.

**Can I use the official Python SDK instead of `zerocaptcha_client.py`?**
Yes: `pip install zerocaptcha` and call `client.solve(...)` and `client.solve_challenge(...)`; see [zerocaptcha-python](https://github.com/ZeroCaptcha/zerocaptcha-python). The small client here keeps the example to one dependency.

**What does a solve cost?**
The [pricing page](https://zerocaptcha.io/pricing) lists the price per 1,000 solved tasks for each task type. Only a task that succeeds is charged.

## Run the tests

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The tests run both flows in a real headless Chrome against stand-ins on your machine: an API, a login page with a Cloudflare Turnstile widget, and a proxy that answers for a site behind a Cloudflare challenge. No key, no real task, nothing spent.

<!-- zc:footer (generated from the registry) -->
## More from ZeroCaptcha

- The website: [ZeroCaptcha](https://zerocaptcha.io), the [docs](https://zerocaptcha.io/docs), the [guides](https://zerocaptcha.io/guides), the [blog](https://zerocaptcha.io/blog) and the [status page](https://zerocaptcha.io/status)
- Start here: [zerocaptcha](https://github.com/ZeroCaptcha/zerocaptcha), [cloudflare-turnstile-solver](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver), [cloudflare-challenge-solver](https://github.com/ZeroCaptcha/cloudflare-challenge-solver)
- Examples by language: [cloudflare-turnstile-solver-python](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-python), [cloudflare-turnstile-solver-nodejs](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-nodejs), [cloudflare-turnstile-solver-go](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-go), [cloudflare-turnstile-solver-php](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-php), [cloudflare-turnstile-solver-java](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-java), [cloudflare-turnstile-solver-csharp](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-csharp), [cloudflare-turnstile-solver-rust](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-rust)
- Browser automation: [cloudflare-turnstile-solver-playwright](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-playwright), [cloudflare-turnstile-solver-puppeteer](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-puppeteer), **cloudflare-turnstile-solver-selenium**
- SDKs, MCP server and migration: [zerocaptcha-js](https://github.com/ZeroCaptcha/zerocaptcha-js), [zerocaptcha-python](https://github.com/ZeroCaptcha/zerocaptcha-python), [zerocaptcha-go](https://github.com/ZeroCaptcha/zerocaptcha-go), [zerocaptcha-mcp](https://github.com/ZeroCaptcha/zerocaptcha-mcp), [createtask-api-migration](https://github.com/ZeroCaptcha/createtask-api-migration)
- Lists: [awesome-cloudflare-turnstile](https://github.com/ZeroCaptcha/awesome-cloudflare-turnstile)

## Licence

MIT: see [LICENSE](LICENSE).

## Disclaimer

ZeroCaptcha is an independent service, not affiliated with or endorsed by Cloudflare. Cloudflare and Turnstile are trademarks of Cloudflare, Inc. Use ZeroCaptcha only on sites you own or are allowed to automate, as the [Acceptable Use Policy](https://zerocaptcha.io/legal/acceptable-use) says; any site owner can [opt out](https://zerocaptcha.io/opt-out).
<!-- /zc:footer -->
