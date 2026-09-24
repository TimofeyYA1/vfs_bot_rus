from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from .models import CheckState, SlotObservation, Target

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None):
        self.token = token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send(self, text: str) -> None:
        if not self.enabled:
            logger.info("Telegram disabled. Message: %s", text.replace("\n", " | "))
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()

    async def observation(self, target: Target, item: SlotObservation) -> None:
        state_label = {
            CheckState.OPEN: "🚨 СЛОТЫ ОБНАРУЖЕНЫ",
            CheckState.CLOSED: "✅ Слотов пока нет",
            CheckState.AUTH_REQUIRED: "🔐 Нужна авторизация VFS",
            CheckState.BLOCKED: "⛔ VFS ограничил доступ",
            CheckState.UNKNOWN: "⚠️ Неизвестное состояние VFS",
        }[item.state]

        lines = [
            state_label,
            f"Центр: {target.center}",
            f"Категория: {target.category}",
        ]
        if target.subcategory:
            lines.append(f"Подкатегория: {target.subcategory}")

        if item.matching_dates:
            lines.append("Подходящие даты: " + ", ".join(d.isoformat() for d in item.matching_dates))
        elif item.visible_dates:
            lines.append("Видимые даты: " + ", ".join(d.isoformat() for d in item.visible_dates[:12]))

        if item.details:
            lines.append(f"Детали: {item.details[:500]}")

        lines.append(item.source_url)
        await self.send("\n".join(lines))

    async def heartbeat(self, states: Sequence[tuple[str, CheckState]]) -> None:
        lines = ["💚 VFS monitor работает"]
        lines.extend(f"{target_id}: {state.value}" for target_id, state in states)
        await self.send("\n".join(lines))
