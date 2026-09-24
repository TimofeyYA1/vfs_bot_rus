from __future__ import annotations

import re
from datetime import date, datetime

from .models import CheckState

SPACE_RE = re.compile(r"\s+")
DATE_PATTERNS = (
    re.compile(r"\b(?P<d>\d{1,2})[./-](?P<m>\d{1,2})[./-](?P<y>20\d{2})\b"),
    re.compile(r"\b(?P<y>20\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b"),
)

BLOCKED_PHRASES = (
    "access denied",
    "temporarily blocked",
    "too many requests",
    "request blocked",
    "forbidden",
    "доступ запрещен",
    "доступ запрещён",
    "слишком много запросов",
    "временно заблокирован",
)

AUTH_PHRASES = (
    "enter your email and password",
    "введите адрес электронной почты и пароль",
    "verify you are human",
    "captcha",
    "one time password",
    "one-time password",
    "одноразовый пароль",
    "проверка безопасности",
)

CLOSED_PHRASES = (
    "no appointment slots are currently available",
    "no appointment slots available",
    "no slots available",
    "currently no slots are available",
    "we are sorry, but no appointment slots",
    "нет доступных временных интервалов",
    "нет свободных слотов",
    "нет доступных слотов",
    "свободных мест нет",
)

OPEN_PHRASES = (
    "appointment slots are available",
    "select appointment date",
    "choose a time slot",
    "available date",
    "available slot",
    "выберите дату записи",
    "выберите время",
    "доступные даты",
    "доступное время",
)


def normalize_text(text: str) -> str:
    return SPACE_RE.sub(" ", text.casefold()).strip()


def classify_page(
    text: str,
    *,
    has_calendar: bool = False,
    has_slot_controls: bool = False,
) -> CheckState:
    normalized = normalize_text(text)

    if any(phrase in normalized for phrase in BLOCKED_PHRASES):
        return CheckState.BLOCKED
    if any(phrase in normalized for phrase in AUTH_PHRASES):
        return CheckState.AUTH_REQUIRED
    if any(phrase in normalized for phrase in CLOSED_PHRASES):
        return CheckState.CLOSED
    if has_slot_controls or any(phrase in normalized for phrase in OPEN_PHRASES):
        return CheckState.OPEN
    if has_calendar and "appointment" in normalized:
        return CheckState.OPEN
    return CheckState.UNKNOWN


def extract_dates(text: str) -> tuple[date, ...]:
    found: set[date] = set()
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                found.add(
                    datetime(
                        int(match.group("y")),
                        int(match.group("m")),
                        int(match.group("d")),
                    ).date()
                )
            except ValueError:
                continue
    return tuple(sorted(found))
