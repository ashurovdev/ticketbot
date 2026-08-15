"""Command-line entry point."""

from __future__ import annotations

import asyncio

from ticketbot.app import run_bot
from ticketbot.config import ConfigError


def main() -> None:
    try:
        asyncio.run(run_bot())
    except ConfigError as error:
        raise SystemExit(f"Configuration error: {error}") from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
