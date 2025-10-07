import asyncio
from asyncio import Event, Task

from .console import Console


class Runner:
    def __init__(self, name: str, console: Console, interval_ms: float) -> None:
        self.name = name
        self.console = console
        self._stop_event = Event()
        self.interval_ms = interval_ms

    async def run(self):
        while not self._stop_event.is_set():
            start = asyncio.get_event_loop().time()

            # loop business logic
            self.console.print(f"[{self.name}] hello from {self.name}")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    # compensate for non zero duration work at each iteration
                    (self.interval_ms / 1000)
                    - (asyncio.get_event_loop().time() - start),
                )
            except asyncio.TimeoutError:
                continue

    def stop(self):
        self._stop_event.set()


class Manager:
    def __init__(
        self,
        console: Console,
        interval_ms: float,
        shutdown_ms: float,
    ) -> None:
        self.console = console
        self.interval_ms = interval_ms
        self.shutdown_ms = shutdown_ms

        self._spawned_runners = 0
        self._runners: dict[str, Runner] = dict()
        self._tasks: dict[str, Task] = dict()

    async def spawn_runner(self, name: str | None = None):
        if name is None:
            name = str(self._spawned_runners)
        runner = Runner(name, self.console, self.interval_ms)
        task = asyncio.create_task(runner.run())

        self._runners[name] = runner
        self._tasks[name] = task
        self._spawned_runners += 1

        print(f"[Manager] Spawned runner {name}")

    async def drop_runner(self, name: str | None = None):
        if name is None:
            if len(self._runners) == 0:
                return
            name = list(self._runners.keys())[-1]
        try:
            self._runners[name].stop()
            task = self._tasks[name]
        except KeyError:
            return
        try:
            print(f"[Manager] Shutting down runner {name} gracefully")
            await asyncio.wait_for(task, timeout=self.shutdown_ms / 1000)
        except asyncio.TimeoutError:
            task.cancel()
            print(
                f"[Manager] Forcefully cancelled task {name} after {self.shutdown_ms} ms"
            )
        finally:
            self._runners.pop(name)
            self._tasks.pop(name)


# Demo
async def main():
    console = Console()
    manager = Manager(console, 3000, 1000)

    while True:
        user_input = await asyncio.to_thread(
            input, "[s: spawn | k <name>: kill | q: quit] > "
        )
        if user_input == "s":
            await manager.spawn_runner()
        if user_input == "k":
            await manager.drop_runner()
        elif user_input.startswith("k "):
            name = user_input[2:]
            await manager.drop_runner(name)
        if user_input == "q":
            break
    console.kill()


if __name__ == "__main__":
    asyncio.run(main())
