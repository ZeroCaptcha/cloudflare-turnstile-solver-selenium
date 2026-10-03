"""The two flows, each on a Selenium driver, so they fit into your own scripts and tests: fill a
Cloudflare Turnstile widget with a token and submit its form, or open a page behind a Cloudflare
challenge with its cf_clearance cookie."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from zerocaptcha_client import ZeroCaptcha

# Runs in the page: puts the token where the widget would, in its response field (named
# cf-turnstile-response unless the widget renames it), creating the field if the widget has not
# rendered it, then calls the widget's data-callback as the widget would. Returns how many fields
# it filled.
FILL_TURNSTILE_TOKEN = """
const token = arguments[0];
const widget = document.querySelector("[data-sitekey]");
const name = (widget && widget.getAttribute("data-response-field-name")) || "cf-turnstile-response";
const form = (widget && widget.closest("form")) || document.querySelector("form");
let fields = [...document.querySelectorAll(`[name="${name}"]`)];
if (fields.length === 0 && form !== null) {
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = name;
  form.append(input);
  fields = [input];
}
for (const field of fields) field.value = token;
const callback = widget && widget.getAttribute("data-callback");
if (callback && typeof window[callback] === "function") window[callback](token);
return fields.length;
"""


def chrome(
    proxy: Optional[str] = None,
    user_agent: Optional[str] = None,
    headless: bool = True,
    extra_arguments: Sequence[str] = (),
) -> webdriver.Chrome:
    """Chrome, headless by default, through a proxy and with a user agent if you give them, and
    any other command-line arguments you pass.

    Chrome takes a proxy's host and port only: use a proxy that lets your IP address in without a
    password, as most providers offer, or a local forwarder in front of it.
    """
    options = webdriver.ChromeOptions()
    arguments: List[str] = []
    if headless:
        arguments.append("--headless=new")
    if proxy:
        parts = urlsplit(proxy)
        arguments.append(f"--proxy-server={parts.scheme}://{parts.hostname}:{parts.port}")
    if user_agent:
        arguments.append(f"--user-agent={user_agent}")
    for argument in [*arguments, *extra_arguments]:
        options.add_argument(argument)
    return webdriver.Chrome(options=options)


def read_widget(driver: webdriver.Chrome) -> Dict[str, Optional[str]]:
    """The widget's sitekey, and its action and cData if it sets them. Waits up to 15 seconds."""
    widget = WebDriverWait(driver, 15).until(
        expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "[data-sitekey]"))
    )
    return {
        "website_key": widget.get_attribute("data-sitekey"),
        "action": widget.get_attribute("data-action"),
        "cdata": widget.get_attribute("data-cdata"),
    }


def solve_and_submit(driver: webdriver.Chrome, client: ZeroCaptcha) -> str:
    """Solves the Cloudflare Turnstile widget on the page, fills its token in and submits the form
    it sits in. Returns once the answer to the form has loaded."""
    widget = read_widget(driver)
    token = client.solve_turnstile(
        driver.current_url, widget["website_key"] or "", action=widget["action"], cdata=widget["cdata"]
    )
    # The token works once, for 300 seconds: fill it in and submit straight away.
    driver.execute_script(FILL_TURNSTILE_TOKEN, token)
    form = driver.find_element(By.CSS_SELECTOR, "form:has([data-sitekey])")
    buttons = form.find_elements(By.CSS_SELECTOR, '[type="submit"]')
    old_page = driver.find_element(By.TAG_NAME, "html")
    if buttons:
        buttons[0].click()
    else:
        driver.execute_script("arguments[0].requestSubmit()", form)
    WebDriverWait(driver, 30).until(expected_conditions.staleness_of(old_page))
    return token


def open_with_clearance(driver: webdriver.Chrome, url: str, clearance: Dict[str, str]) -> None:
    """Opens a page behind a Cloudflare challenge with a clearance from ZeroCaptcha. Start the driver
    with chrome(proxy, clearance["user_agent"]): the clearance works only through the proxy the
    task used, with the user agent that earned it.

    A browser can set a cookie only for the site it is on, so this opens the site (the challenge
    page answers), sets cf_clearance, and opens the page again.
    """
    driver.get(url)
    driver.add_cookie({"name": "cf_clearance", "value": clearance["cf_clearance"], "path": "/"})
    driver.get(url)
