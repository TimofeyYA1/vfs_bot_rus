from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .browser import VFSBrowser
from .config import Settings, load_targets
from .monitor import SlotMonitor
from .notifier import TelegramNotifier
from .storage import StateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vfs-monitor",
        description="Monitor France visa appointment slots in VFS Global Russia.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Run continuous monitoring")
    sub.add_parser("once", help="Check all enabled targets once")
    sub.add_parser("bootstrap", help="Open a headed browser and save a VFS login session")
    sub.add_parser("validate", help="Validate environment and targets configuration")
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def make_monitor(settings: Settings) -> SlotMonitor:
    targets = load_targets(settings.targets_path)
    store = StateStore(settings.database_path)
    token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else None
    notifier = TelegramNotifier(token=token, chat_id=settings.telegram_chat_id)
    return SlotMonitor(settings=settings, targets=targets, store=store, notifier=notifier)


async def async_main(args: argparse.Namespace) -> int:
    settings = Settings()

    if args.command == "validate":
        targets = load_targets(settings.targets_path)
        print(f"Config OK. Enabled targets: {len(targets)}")
        for target in targets:
            print(f"- {target.id}: {target.center} / {target.category}")
        return 0

    if args.command == "bootstrap":
        browser = VFSBrowser(settings)
        await browser.start(force_headed=True, ignore_saved_state=True)
        try:
            await browser.bootstrap_session()
        finally:
            await browser.close()
        return 0

    monitor = make_monitor(settings)
    if args.command == "once":
        observations = await monitor.run_once()
        for item in observations:
            print(f"{item.target_id}: {item.state.value} | {item.details}")
        return 0

    await monitor.run_forever()
    return 0


def main() -> None:
    args = build_parser().parse_args()
    configure_logging(args.log_level)
    try:
        raise SystemExit(asyncio.run(async_main(args)))
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(130) from None
    except Exception as exc:
        logging.getLogger(__name__).exception("Fatal error")
        print(f"Fatal: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
