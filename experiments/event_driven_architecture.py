import asyncio
from asyncio import Queue


# TODO: Experiment with 
# [X] Queue
# [ ] Event
# [ ] Condition
# [ ] Lock
# [ ] Semaphore/BoundedSemaphore
# [ ] Future
# [ ] Task cancellation via asyncio.CancelledError

class ConsoleProducer:
    def __init__(self, queue: Queue) -> None:
        self.queue = queue

    async def run(self) -> None:
        while True:
            line = await asyncio.to_thread(input, "> ")
            await self.queue.put(line)
            print(f"[producer] put item: {line}")


class Consumer:
    def __init__(self, queue: Queue) -> None:
        self.queue = queue

    async def run(self) -> None:
        while True:
            item = await self.queue.get()
            print(f"[consumer] consumed item: {item}")
            self.queue.task_done()
            print(f"[consumer] remaining items: {self.queue.qsize()}")


async def main():
    queue = Queue()
    await asyncio.gather(ConsoleProducer(queue).run(), Consumer(queue).run())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nexiting.")
