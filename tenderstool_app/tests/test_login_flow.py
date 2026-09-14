import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.services import selectors, tenderstool_client


class _TimeoutNavigation:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        raise PlaywrightTimeoutError("navigation timeout")


class _DummyPage:
    def __init__(self, url):
        self.url = url
        self.waited_for_load = False

    def expect_navigation(self, timeout):
        return _TimeoutNavigation()

    async def click(self, selector):
        pass

    async def wait_for_load_state(self, state, timeout):
        self.waited_for_load = True

    async def wait_for_url(self, url, timeout):
        raise PlaywrightTimeoutError("url timeout")


async def test_submit_login_form_accepts_success_when_navigation_event_times_out_but_url_changed():
    page = _DummyPage("https://www.adjudicacionestic.com/front/mi-panel.php")

    await tenderstool_client.submit_login_form(page)

    assert page.waited_for_load is True


async def test_submit_login_form_keeps_timeout_when_still_on_login():
    page = _DummyPage(selectors.LOGIN_URL)

    with pytest.raises(PlaywrightTimeoutError):
        await tenderstool_client.submit_login_form(page)
