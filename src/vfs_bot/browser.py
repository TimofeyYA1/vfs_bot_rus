from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from .classifier import classify_page, extract_dates
from .config import Settings
from .models import CheckState, SlotObservation, Target

logger = logging.getLogger(__name__)

BOOKING_TEXT = re.compile(
    r"start new booking|book an appointment|new booking|schedule appointment|"
    r"начать новую запись|записаться на подачу|записаться|новая запись",
    re.IGNORECASE,
)
LOGIN_TEXT = re.compile(r"sign in|log in|войти", re.IGNORECASE)
OPTION_SELECTOR = "[role='option'], mat-option, .mat-mdc-option, .mat-option"
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b")


class VfsBrowserError(RuntimeError):
    pass


class SessionNeedsAttention(VfsBrowserError):
    pass


class VFSBrowser:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "VFSBrowser":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self, *, force_headed: bool = False, ignore_saved_state: bool = False) -> None:
        self.settings.debug_dir.mkdir(parents=True, exist_ok=True)
        self.settings.storage_state_path.parent.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False if force_headed else self.settings.headless
        )

        context_kwargs: dict[str, object] = {
            "locale": self.settings.locale,
            "timezone_id": self.settings.timezone,
            "viewport": {"width": 1440, "height": 1000},
        }
        if not ignore_saved_state and self.settings.storage_state_path.exists():
            context_kwargs["storage_state"] = str(self.settings.storage_state_path)

        self._context = await self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self.settings.action_timeout_ms)
        self._context.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
        self.page = await self._context.new_page()

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def bootstrap_session(self) -> None:
        if not self.page or not self._context:
            raise RuntimeError("Browser is not started")

        await self.page.goto(self.settings.vfs_dashboard_url, wait_until="domcontentloaded")
        print(
            "\nВ открывшемся браузере войдите в VFS вручную. "
            "CAPTCHA/OTP, если появятся, проходятся только вручную."
        )
        await asyncio.to_thread(input, "После успешного входа и появления dashboard нажмите Enter... ")
        await self._context.storage_state(path=str(self.settings.storage_state_path))
        print(f"Сессия сохранена: {self.settings.storage_state_path}")

    async def check_target(self, target: Target) -> SlotObservation:
        if not self.page:
            raise RuntimeError("Browser is not started")

        try:
            await self._ensure_authenticated()
            await self._open_booking_form()
            await self._select_application_details(target)
            await self.page.wait_for_timeout(1500)

            body = await self._body_text()
            state = classify_page(
                body,
                has_calendar=await self._has_calendar(),
                has_slot_controls=await self._has_slot_controls(),
            )
            visible_dates = extract_dates(body)
            matching_dates = tuple(item for item in visible_dates if target.accepts_date(item))

            details = self._describe_state(state, visible_dates, matching_dates, target)
            observation = SlotObservation(
                target_id=target.id,
                state=state,
                checked_at=datetime.now(timezone.utc),
                details=details,
                visible_dates=visible_dates,
                matching_dates=matching_dates,
                source_url=self.page.url,
            )

            if state in {CheckState.UNKNOWN, CheckState.BLOCKED, CheckState.AUTH_REQUIRED}:
                await self._save_debug(target.id, state.value)
            return observation
        except SessionNeedsAttention:
            await self._save_debug(target.id, "auth_required")
            return SlotObservation(
                target_id=target.id,
                state=CheckState.AUTH_REQUIRED,
                details="VFS требует ручной вход, CAPTCHA или дополнительное подтверждение.",
                source_url=self.page.url if self.page else self.settings.vfs_dashboard_url,
            )
        except Exception as exc:
            logger.exception("Target check failed: %s", target.id)
            await self._save_debug(target.id, "error")
            return SlotObservation(
                target_id=target.id,
                state=CheckState.UNKNOWN,
                details=f"{type(exc).__name__}: {str(exc)[:250]}",
                source_url=self.page.url if self.page else self.settings.vfs_dashboard_url,
            )

    async def _ensure_authenticated(self) -> None:
        assert self.page is not None
        await self.page.goto(self.settings.vfs_dashboard_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(1200)
        body = await self._body_text()

        if not self._looks_like_login(body):
            return

        if not self.settings.vfs_email or not self.settings.vfs_password:
            raise SessionNeedsAttention("Login required and credentials are not configured")

        email = self.page.locator(
            "input[type='email'], input[name*='email' i], input[placeholder*='email' i]"
        ).first
        password = self.page.locator("input[type='password']").first

        if await email.count() == 0 or await password.count() == 0:
            raise SessionNeedsAttention("Could not find login fields")

        await email.fill(self.settings.vfs_email)
        await password.fill(self.settings.vfs_password.get_secret_value())

        submit = self.page.get_by_role("button", name=LOGIN_TEXT).first
        if await submit.count() == 0:
            submit = self.page.locator("button[type='submit']").first
        if await submit.count() == 0:
            raise SessionNeedsAttention("Could not find login button")

        await submit.click()
        await self.page.wait_for_timeout(2500)
        body = await self._body_text()

        if self._looks_like_login(body):
            raise SessionNeedsAttention("Login needs manual attention")

        if self._context:
            await self._context.storage_state(path=str(self.settings.storage_state_path))

    async def _open_booking_form(self) -> None:
        assert self.page is not None
        body = await self._body_text()
        if self._looks_like_application_form(body):
            return

        candidates = self.page.locator("button, a").filter(has_text=BOOKING_TEXT)
        if await candidates.count() == 0:
            candidates = self.page.get_by_text(BOOKING_TEXT).first
        else:
            candidates = candidates.first

        if await candidates.count() == 0:
            raise VfsBrowserError("Booking entry point not found")

        await candidates.click()
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(1000)

    async def _select_application_details(self, target: Target) -> None:
        await self._choose_combo(target.center, index=0)
        await self.page.wait_for_timeout(700)
        await self._choose_combo(target.category, index=1)
        await self.page.wait_for_timeout(700)
        if target.subcategory:
            await self._choose_combo(target.subcategory, index=2)
            await self.page.wait_for_timeout(700)

    async def _choose_combo(self, option_text: str, *, index: int) -> None:
        assert self.page is not None

        native_selects = self.page.locator("select")
        if await native_selects.count() > index:
            select = native_selects.nth(index)
            options = await select.locator("option").all()
            wanted = option_text.casefold()
            for option in options:
                label = (await option.inner_text()).strip()
                if wanted in label.casefold() or label.casefold() in wanted:
                    value = await option.get_attribute("value")
                    if value is not None:
                        await select.select_option(value=value)
                    else:
                        await select.select_option(label=label)
                    return

        combos = self.page.locator("[role='combobox'], mat-select, .mat-mdc-select-trigger")
        if await combos.count() <= index:
            raise VfsBrowserError(f"Combo #{index + 1} not found for option {option_text!r}")

        combo = combos.nth(index)
        await combo.click()
        await self.page.wait_for_timeout(300)

        wanted = option_text.casefold()
        options = self.page.locator(OPTION_SELECTOR)
        for option in await options.all():
            label = (await option.inner_text()).strip()
            if wanted in label.casefold() or label.casefold() in wanted:
                await option.click()
                return

        by_text = self.page.get_by_text(re.compile(re.escape(option_text), re.IGNORECASE)).last
        if await by_text.count():
            await by_text.click()
            return

        raise VfsBrowserError(f"Option not found: {option_text!r}")

    async def _body_text(self) -> str:
        assert self.page is not None
        try:
            return await self.page.locator("body").inner_text(timeout=self.settings.action_timeout_ms)
        except Exception:
            return ""

    def _looks_like_login(self, body: str) -> bool:
        folded = body.casefold()
        has_password = "password" in folded or "пароль" in folded
        has_email = "email" in folded or "электрон" in folded
        return has_password and has_email

    def _looks_like_application_form(self, body: str) -> bool:
        folded = body.casefold()
        center = any(term in folded for term in ("visa application centre", "визовый центр"))
        category = any(term in folded for term in ("appointment category", "категория"))
        return center and category

    async def _has_calendar(self) -> bool:
        assert self.page is not None
        selectors = "input[type='date'], mat-calendar, .mat-calendar, [role='grid']"
        return await self.page.locator(selectors).count() > 0

    async def _has_slot_controls(self) -> bool:
        assert self.page is not None
        candidates = self.page.locator("button, [role='button'], [role='option']")
        texts = await candidates.all_inner_texts()
        return any(TIME_RE.search(text) for text in texts)

    def _describe_state(
        self,
        state: CheckState,
        visible_dates: tuple,
        matching_dates: tuple,
        target: Target,
    ) -> str:
        if state == CheckState.OPEN:
            if matching_dates:
                return "Найдены слоты с датами внутри заданного диапазона."
            if visible_dates and (target.date_from or target.date_to):
                return "Слоты есть, но видимые даты не попали в заданный диапазон."
            return "Страница содержит признаки доступных слотов; проверьте VFS сразу."
        if state == CheckState.CLOSED:
            return "VFS явно сообщает об отсутствии доступных слотов."
        if state == CheckState.BLOCKED:
            return "Страница похожа на rate-limit/WAF блокировку."
        if state == CheckState.AUTH_REQUIRED:
            return "VFS требует вход или ручное подтверждение."
        return "Разметка не совпала с известными состояниями; сохранён debug snapshot."

    async def _save_debug(self, target_id: str, suffix: str) -> None:
        if not self.page:
            return
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safe_target = re.sub(r"[^a-zA-Z0-9_.-]", "_", target_id)
            base = self.settings.debug_dir / f"{stamp}_{safe_target}_{suffix}"
            await self.page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
            body = await self._body_text()
            base.with_suffix(".txt").write_text(body[:30_000], encoding="utf-8")
        except Exception:
            logger.exception("Failed to save debug snapshot")
