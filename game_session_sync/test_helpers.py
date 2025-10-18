import asyncio

from .log_helpers import Console, setup_test_logging
from .types import Producer


async def producer_test_run(watcher: Producer):
    console = Console()
    setup_test_logging(console)

    try:
        asyncio.create_task(watcher.run())
        while True:
            user_input = (await asyncio.to_thread(input, "[q: quit] >")).strip()
            if user_input == "q":
                break
    finally:
        watcher.stop()
        console.kill()
