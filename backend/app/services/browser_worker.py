"""Managed, isolated Playwright sessions. Browser access is authorized by the engine, not URLs."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Literal

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Response,
    async_playwright,
    expect,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import Settings


class BrowserTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str | None = None
    name: str | None = None
    label: str | None = None
    placeholder: str | None = None
    text: str | None = None
    test_id: str | None = None
    css: str | None = None
    frame: str | None = None
    index: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def one_locator(self) -> BrowserTarget:
        if (
            sum(bool(v) for v in (self.role, self.label, self.placeholder, self.text, self.test_id, self.css))
            != 1
        ):
            raise ValueError("Specify exactly one locator: role, label, placeholder, text, test_id, css")
        return self


class BrowserAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "navigate",
        "snapshot",
        "click",
        "fill",
        "press",
        "select",
        "check",
        "wait_visible",
        "assert_visible",
        "assert_hidden",
        "assert_text",
        "assert_url",
        "assert_count",
        "screenshot",
        "report",
    ]
    test_case: str | None = Field(default=None, max_length=200)
    target: BrowserTarget | None = None
    url: str | None = Field(default=None, max_length=4000)
    value: str = Field(default="", max_length=12000, repr=False)
    secret: bool = False
    checked: bool = True
    count: int = Field(default=1, ge=0, le=10000)
    contains: bool = False
    timeout_ms: int | None = Field(default=None, ge=100, le=60000)
    summary: str = Field(default="", max_length=2000)


class BrowserWorkerManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.capacity = asyncio.Semaphore(settings.browser_max_sessions)
        self.workers: set[BrowserWorker] = set()

    def worker(self) -> BrowserWorker:
        worker = BrowserWorker(self)
        self.workers.add(worker)
        return worker

    async def close(self) -> None:
        await asyncio.gather(*(worker.close() for worker in tuple(self.workers)), return_exceptions=True)


class BrowserWorker:
    def __init__(self, manager: BrowserWorkerManager) -> None:
        self.manager = manager
        self.settings = manager.settings
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.started = monotonic()
        self.steps: list[dict[str, Any]] = []
        self.secrets: set[str] = set()
        self.masks: list[Locator] = []
        self.test_case = "Browser test"
        self.admitted = False
        self.closed = False
        self.reported: set[str] = set()
        self.network_errors: list[dict[str, Any]] = []

    def redact(self, value: str) -> str:
        for secret in sorted(self.secrets, key=len, reverse=True):
            if secret:
                value = value.replace(secret, "<redacted>")
        return value

    async def start(self) -> None:
        if self.closed:
            raise RuntimeError("Browser session closed")
        if self.page:
            return
        if self.admitted:
            raise RuntimeError("Browser startup previously failed; start a new test run")
        await self.manager.capacity.acquire()
        self.admitted = True
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            viewport={"width": 1440, "height": 900}, accept_downloads=False
        )
        self.context.set_default_timeout(self.settings.browser_action_timeout_ms)
        self.page = await self.context.new_page()
        # Tests never inherit another ticket's cookies or the operator's browser profile.
        self.context.on("page", self._new_page)
        self.context.on("dialog", lambda dialog: dialog.dismiss())
        self.context.on("response", self._response)

    def _response(self, response: Response) -> None:
        if response.status >= 400 and len(self.network_errors) < 50:
            self.network_errors.append(
                {"url": response.url, "status": response.status, "method": response.request.method}
            )

    def _new_page(self, page: Page) -> None:
        self.page = page

    def locator(self, target: BrowserTarget | None) -> Locator:
        if not target or not self.page:
            raise ValueError("This action requires a target locator")
        root: Any = self.page.frame_locator(target.frame) if target.frame else self.page
        if target.role:
            locator = root.get_by_role(
                target.role, **({"name": target.name, "exact": True} if target.name else {})
            )
        elif target.label:
            locator = root.get_by_label(target.label, exact=True)
        elif target.placeholder:
            locator = root.get_by_placeholder(target.placeholder, exact=True)
        elif target.text:
            locator = root.get_by_text(target.text, exact=True)
        elif target.test_id:
            locator = root.get_by_test_id(target.test_id)
        else:
            locator = root.locator(target.css)
        return locator.nth(target.index) if target.index is not None else locator

    async def snapshot(self) -> dict[str, str]:
        if not self.page:
            return {"url": "", "snapshot": "Browser has not started"}
        return {
            "url": self.redact(self.page.url),
            "title": self.redact(await self.page.title()),
            "snapshot": self.redact(await self.page.locator("body").aria_snapshot())[:18000],
        }

    async def screenshot(self) -> bytes | None:
        if not self.page or self.page.is_closed():
            return None
        # Mask password fields and explicit secret fields, even when a UI reveals their values.
        masks = [self.page.locator('input[type="password"]'), *self.masks]
        return await self.page.screenshot(type="png", full_page=False, mask=masks, timeout=15000)

    async def execute(self, action: BrowserAction) -> dict[str, Any]:
        if action.test_case:
            self.test_case = action.test_case
        if len(self.steps) >= self.settings.browser_max_actions:
            raise ValueError("Browser action limit reached")
        if monotonic() - self.started > self.settings.browser_run_timeout_sec:
            raise TimeoutError("Browser run timeout")
        if action.action == "report":
            raise ValueError("Reports are generated by the engine")
        step: dict[str, Any] = {
            "action": action.action,
            "test_case": self.test_case,
            "at": datetime.now(UTC).isoformat(),
            "status": "OK",
        }
        if action.target:
            step["target"] = {
                key: value[:200] if isinstance(value, str) else value
                for key, value in action.target.model_dump(exclude_none=True).items()
            }
        if action.action == "assert_url":
            step["expected"] = (action.url or "")[:200]
        elif action.action == "assert_text":
            step["expected"] = action.value[:200]
        elif action.action == "assert_count":
            step["expected"] = action.count
        self.reported.discard(self.test_case)
        try:
            await self.start()
            assert self.page
            timeout = min(
                action.timeout_ms or self.settings.browser_action_timeout_ms,
                self.settings.browser_action_timeout_ms,
            )
            if action.action == "navigate":
                if not action.url or not re.match(r"^https?://", action.url, re.I):
                    raise ValueError("Use an HTTP or HTTPS web URL")
                response = await self.page.goto(action.url, wait_until="domcontentloaded", timeout=timeout)
                step["http_status"] = response.status if response else None
                if response and response.status >= 400:
                    raise ValueError(f"Navigation returned HTTP {response.status}")
            elif action.action in {"snapshot", "screenshot"}:
                pass
            elif action.action == "assert_url":
                if not action.url:
                    raise ValueError("assert_url requires url")
                expected = re.compile(re.escape(action.url)) if action.contains else action.url
                await expect(self.page).to_have_url(expected, timeout=timeout)
            else:
                target = self.locator(action.target)
                if action.action == "click":
                    await target.click(timeout=timeout)
                elif action.action == "fill":
                    if action.secret or await target.get_attribute("type", timeout=timeout) == "password":
                        self.secrets.add(action.value)
                        self.masks.append(target)
                    await target.fill(action.value, timeout=timeout)
                elif action.action == "press":
                    await target.press(action.value, timeout=timeout)
                elif action.action == "select":
                    await target.select_option(action.value, timeout=timeout)
                elif action.action == "check":
                    await target.set_checked(action.checked, timeout=timeout)
                elif action.action == "wait_visible":
                    await target.wait_for(state="visible", timeout=timeout)
                elif action.action == "assert_visible":
                    await expect(target).to_be_visible(timeout=timeout)
                elif action.action == "assert_hidden":
                    await expect(target).to_be_hidden(timeout=timeout)
                elif action.action == "assert_text":
                    if action.contains:
                        await expect(target).to_contain_text(action.value, timeout=timeout)
                    else:
                        await expect(target).to_have_text(action.value, timeout=timeout)
                elif action.action == "assert_count":
                    await expect(target).to_have_count(action.count, timeout=timeout)
        except Exception as error:
            step["status"] = "FAIL" if isinstance(error, AssertionError) else "ERROR"
            # Playwright error strings include fill values, selectors and reflected page contents.
            step["error"] = type(error).__name__
            if "Executable doesn't exist" in str(error):
                step["error"] = "Chromium chưa cài. Chạy scripts/setup-browser.ps1"
        self.steps.append(step)
        try:
            state = await self.snapshot()
        except Exception:
            state = {"snapshot": "Không đọc được giao diện hiện tại"}
        return {**step, **state}

    def report(self, case: str | None = None, summary: str = "") -> dict[str, Any]:
        name = case or self.test_case
        steps = [step for step in self.steps if step["test_case"] == name]
        checks = [step for step in steps if step["action"].startswith("assert_")]
        status = (
            "FAIL"
            if any(step["status"] == "FAIL" for step in checks)
            else ("BLOCKED" if not checks or any(step["status"] != "OK" for step in steps) else "PASS")
        )
        self.reported.add(name)
        report = {
            "test_case": name,
            "status": status,
            "summary": self.redact(summary),
            "url": self.redact(self.page.url) if self.page else "",
            "at": datetime.now(UTC).isoformat(),
            "checks": checks,
            "steps": steps,
            "network_errors": [{**item, "url": self.redact(item["url"])} for item in self.network_errors],
        }
        return json.loads(self.redact(json.dumps(report)))

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.context:
                await self.context.close()
        finally:
            try:
                if self.browser:
                    await self.browser.close()
            finally:
                try:
                    if self.playwright:
                        await self.playwright.stop()
                finally:
                    if self.admitted:
                        self.manager.capacity.release()
                    self.manager.workers.discard(self)
