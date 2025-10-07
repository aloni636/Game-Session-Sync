# run using poetry run python -m experiments.await_race

import asyncio
import random

from .console import Console

rng = random.Random(42)


async def queue_get() -> str:
    await asyncio.sleep(2)
    return rng.choice(["a", "b", "c"])


async def interrupt() -> None:
    await asyncio.to_thread(input, "[stop: enter] > ")
    return


async def main():
    console = Console()

    interrupt_task = asyncio.create_task(interrupt())
    while True:
        queue_get_task = asyncio.create_task(queue_get())
        done, _ = await asyncio.wait(
            {queue_get_task, interrupt_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if queue_get_task in done:
            queue_item = queue_get_task.result()
            console.print(f"queue item: {queue_item}")
        if interrupt_task in done:
            print("cancelling...")
            break
    console.kill()


if __name__ == "__main__":
    asyncio.run(main())
