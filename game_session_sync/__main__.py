import asyncio
import logging
import os
from pathlib import Path

from .app import GameSessionSync
from .config import load_config
from .log_helpers import setup_logging
from .notifier_utils import notify_error

log = logging.getLogger()


async def main():
    setup_logging()
    config_path = os.environ.get("CONFIG_YAML", "config.yaml")
    config = load_config(Path(config_path))
    app = GameSessionSync(config)
    try:
        await app.run()
    except KeyboardInterrupt:
        log.exception("Graceful exit by keyboard interrupt")
    except Exception as e:
        notify_error(e)
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
