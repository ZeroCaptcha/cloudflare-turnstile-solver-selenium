"""Both flows in a real headless Chrome, against stand-ins for the API, a site with a Cloudflare
Turnstile widget, and a site behind a Cloudflare challenge: no key, no real task, nothing spent."""

from __future__ import annotations

import os
import unittest

from selenium import webdriver

from flows import FILL_TURNSTILE_TOKEN, chrome, open_with_clearance, solve_and_submit
from stand_ins import (
    CHALLENGED_SITE,
    CLEARANCE,
    KEY,
    SITEKEY,
    TOKEN,
    USER_AGENT,
    StandInApi,
    StandInChallengeProxy,
    StandInSite,
)
from zerocaptcha_client import ZeroCaptcha


def browser(proxy: str = "", user_agent: str = "") -> webdriver.Chrome:
    # Chrome's sandbox needs user namespaces, which some CI runners (Ubuntu 24.04) do not grant.
    extra = ["--no-sandbox"] if os.environ.get("CI") else []
    return chrome(proxy or None, user_agent or None, extra_arguments=extra)


class FlowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api = StandInApi()
        cls.client = ZeroCaptcha(cls.api.url, KEY, interval=0.01)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.api.close()

    def test_fills_the_token_in_and_submits_the_form(self) -> None:
        site = StandInSite()
        driver = browser()
        try:
            driver.get(f"{site.url}/login")
            self.assertEqual(solve_and_submit(driver, self.client), TOKEN)
            self.assertEqual(driver.title, "Logged in")
            self.assertEqual(site.posted[-1]["cf-turnstile-response"], TOKEN)
            create = next(r for r in self.api.requests if r["method"] == "POST")
            self.assertEqual(
                create["body"],
                {
                    "type": "TurnstileTaskProxyless",
                    "websiteURL": f"{site.url}/login",
                    "websiteKey": SITEKEY,
                    # Read from the widget, the action and cData reach the API.
                    "action": "login",
                    "cdata": "session-7f3a9c2e",
                },
            )
        finally:
            driver.quit()
            site.close()

    def test_the_widgets_callback_gets_the_token(self) -> None:
        site = StandInSite()
        driver = browser()
        try:
            driver.get(f"{site.url}/login")
            self.assertEqual(driver.execute_script(FILL_TURNSTILE_TOKEN, TOKEN), 1)
            self.assertEqual(driver.execute_script("return document.body.dataset.callback"), TOKEN)
        finally:
            driver.quit()
            site.close()

    def test_opens_a_page_behind_a_challenge_with_its_clearance_through_the_proxy(self) -> None:
        proxy = StandInChallengeProxy()
        try:
            clearance = self.client.solve_challenge(CHALLENGED_SITE, proxy.url)
            self.assertEqual(clearance, {"cf_clearance": CLEARANCE, "user_agent": USER_AGENT})
            driver = browser(proxy.url, clearance["user_agent"])
            try:
                open_with_clearance(driver, CHALLENGED_SITE, clearance)
                self.assertEqual(driver.title, "Welcome")
            finally:
                driver.quit()
            last = [seen for seen in proxy.seen if seen["url"] == CHALLENGED_SITE][-1]
            self.assertEqual(last["user_agent"], USER_AGENT)
            self.assertEqual(last["cookies"].get("cf_clearance"), CLEARANCE)
        finally:
            proxy.close()

    def test_without_the_clearance_the_challenge_page_stays(self) -> None:
        proxy = StandInChallengeProxy()
        driver = browser(proxy.url)
        try:
            driver.get(CHALLENGED_SITE)
            self.assertEqual(driver.title, "Just a moment...")
        finally:
            driver.quit()
            proxy.close()


if __name__ == "__main__":
    unittest.main()
