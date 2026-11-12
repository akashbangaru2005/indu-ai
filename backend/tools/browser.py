import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class BrowserController:

    def __init__(self):
        self._thread = None
        self._loop = None
        self._playwright = None
        self._browser = None
        self._page = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indu-browser")

    def _start_browser(self):

        if sync_playwright is None:
            raise RuntimeError("Install playwright and run: python -m playwright install chromium")

        if self._browser and self._browser.is_connected():
            return

        self._playwright = sync_playwright().start()

        self._browser = self._playwright.chromium.launch(
            headless=False
        )

        self._page = self._browser.new_page()

        self._page.set_default_timeout(15000)
        self._page.set_default_navigation_timeout(30000)

        print("🌐 Indu Browser started")

    def _open(self, url: str):

        self._start_browser()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        self._page.goto(
            url,
            wait_until="domcontentloaded"
        )

        return f"Opened {url}"

    def _search_google(self, query: str):

        self._start_browser()

        url = (
            "https://www.google.com/search?q="
            + quote_plus(query)
        )

        self._page.goto(
            url,
            wait_until="domcontentloaded"
        )

        return f"Searching Google for {query}"

    def _back(self):

        self._start_browser()

        self._page.go_back(
            wait_until="domcontentloaded"
        )

        return "Going back."

    def _forward(self):

        self._start_browser()

        self._page.go_forward(
            wait_until="domcontentloaded"
        )

        return "Going forward."

    def _refresh(self):

        self._start_browser()

        self._page.reload(
            wait_until="domcontentloaded"
        )

        return "Page refreshed."

    def _scroll_down(self):

        self._start_browser()

        self._page.mouse.wheel(
            0,
            700
        )

        return "Scrolled down."

    def _scroll_up(self):

        self._start_browser()

        self._page.mouse.wheel(
            0,
            -700
        )

        return "Scrolled up."

    def _execute_sync(self, command: str):

        command = command.lower().strip()
        command = command.rstrip(".!?")

        if command == "open youtube":
            return self._open(
                "https://www.youtube.com"
            )

        if command == "open google":
            return self._open(
                "https://www.google.com"
            )

        if command == "open github":
            return self._open(
                "https://github.com"
            )

        if command == "open whatsapp":
            return self._open(
                "https://web.whatsapp.com"
            )

        if command.startswith("search for "):

            query = command[
                len("search for "):
            ].strip()

            if query:
                return self._search_google(query)

            return "What should I search for?"

        if command == "go back":
            return self._back()

        if command == "go forward":
            return self._forward()

        if command == "refresh":
            return self._refresh()

        if command == "scroll down":
            return self._scroll_down()

        if command == "scroll up":
            return self._scroll_up()

        return "I don't know that browser command yet."

    async def execute(self, command: str):

        return await asyncio.get_running_loop().run_in_executor(
            self._executor,
            self._execute_sync,
            command
        )

    def _close_sync(self):

        if self._browser:
            self._browser.close()
            self._browser = None

        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    async def close(self):

        try:
            await asyncio.get_running_loop().run_in_executor(self._executor, self._close_sync)
        finally:
            self._executor.shutdown(wait=True)
