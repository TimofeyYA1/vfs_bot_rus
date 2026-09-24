# Runbook

## First setup

1. Copy `.env.example` to `.env`.
2. Copy `targets.example.yml` to `targets.yml`.
3. Create a Telegram bot and put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` into `.env`.
4. Install the project and Chromium:
   `python -m pip install -e ".[dev]" && playwright install chromium`.
5. Run `python -m vfs_bot validate`.
6. Run `python -m vfs_bot bootstrap` and complete VFS login manually.
7. Run `python -m vfs_bot once`.
8. Only after the one-shot check looks correct, run `python -m vfs_bot run`.

## What to edit when VFS changes its UI

Look in `.data/debug/` for a screenshot and a text snapshot. Update:

- booking entry text in `BOOKING_TEXT`;
- application combobox handling in `_choose_combo`;
- state phrases in `classifier.py`.

Never "fix" a UI change by treating `UNKNOWN` as `CLOSED`.

## Session expired

Run `python -m vfs_bot bootstrap` again. The new storage state replaces
`.data/vfs-storage-state.json`.

## VFS blocks the request

Increase `CHECK_INTERVAL_SECONDS`, keep jitter enabled and stop the service for a while.
This project intentionally does not include CAPTCHA solvers or WAF bypasses.

## Docker

Bootstrap the session locally first so `.data/vfs-storage-state.json` exists, then:

```bash
docker compose up -d --build
docker compose logs -f
```
