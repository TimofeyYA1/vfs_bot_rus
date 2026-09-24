from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta

from .browser import VFSBrowser
from .config import Settings
from .models import CheckState, SlotObservation, Target
from .notifier import TelegramNotifier
from .storage import StateStore

logger = logging.getLogger(__name__)

ALERT_STATES = {
    CheckState.OPEN,
    CheckState.AUTH_REQUIRED,
    CheckState.BLOCKED,
    CheckState.UNKNOWN,
}


class SlotMonitor:
    def __init__(
        self,
        settings: Settings,
        targets: list[Target],
        store: StateStore,
        notifier: TelegramNotifier,
    ):
        self.settings = settings
        self.targets = targets
        self.store = store
        self.notifier = notifier
        self._last_heartbeat = datetime.now(UTC)

    async def run_forever(self) -> None:
        await self.notifier.send(
            f"🤖 VFS France monitor запущен. Целей: {len(self.targets)}. "
            f"Интервал: {self.settings.check_interval_seconds}s + jitter."
        )

        async with VFSBrowser(self.settings) as browser:
            while True:
                await self._run_cycle(browser)
                await self._maybe_heartbeat()
                delay = self.settings.check_interval_seconds + random.uniform(
                    0, self.settings.check_jitter_seconds
                )
                logger.info("Sleeping %.1fs", delay)
                await asyncio.sleep(delay)

    async def run_once(self) -> list[SlotObservation]:
        async with VFSBrowser(self.settings) as browser:
            return await self._run_cycle(browser)

    async def _run_cycle(self, browser: VFSBrowser) -> list[SlotObservation]:
        results: list[SlotObservation] = []
        for target in self.targets:
            logger.info("Checking target=%s center=%s", target.id, target.center)
            observation = await browser.check_target(target)
            results.append(observation)
            change = self.store.update(observation)

            logger.info(
                "Result target=%s state=%s changed=%s",
                target.id,
                observation.state.value,
                change.state_changed,
            )

            if self._should_alert(
                target,
                observation,
                change.state_changed,
                change.fingerprint_changed,
            ):
                await self.notifier.observation(target, observation)

            if observation.state in {CheckState.AUTH_REQUIRED, CheckState.BLOCKED}:
                # Continuing would only hammer the same blocked/expired session.
                break
        return results

    def _should_alert(
        self,
        target: Target,
        observation: SlotObservation,
        state_changed: bool,
        fingerprint_changed: bool,
    ) -> bool:
        if observation.state == CheckState.OPEN:
            has_window = target.date_from is not None or target.date_to is not None
            if has_window and observation.visible_dates and not observation.matching_dates:
                return False
            return state_changed or fingerprint_changed
        if observation.state in ALERT_STATES:
            return state_changed
        return False

    async def _maybe_heartbeat(self) -> None:
        now = datetime.now(UTC)
        if now - self._last_heartbeat < timedelta(hours=self.settings.heartbeat_hours):
            return
        snapshot = sorted(self.store.snapshot().items())
        await self.notifier.heartbeat(snapshot)
        self._last_heartbeat = now
