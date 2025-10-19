import asyncio
import logging
import os

from .app import GameSessionSync
from .config import load_config
from .log_helpers import setup_logging

log = logging.getLogger()


async def main():
    setup_logging()
    config_path = os.environ.get("CONFIG_YAML", "config.yaml")
    config = load_config(config_path)
    app = GameSessionSync(config)
    try:
        await app.run()
    except* Exception as eg:
        log.exception("Exception raised to top of the stack and crashed the software")
        raise
    finally:
        app.stop()


if __name__ == "__main__":
    asyncio.run(main())
