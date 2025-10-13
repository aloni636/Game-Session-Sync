import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


# credits: https://gist.github.com/medihack/7af1f98ea468aa7ad00102c7d84c65d8
def async_debounce(
    wait_sec: float,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[asyncio.Task[T]]]]:
    def decorator(
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[asyncio.Task[T]]]:
        task: Optional[asyncio.Task[T]] = None

        @wraps(func)
        async def debounced(*args: Any, **kwargs: Any) -> asyncio.Task[T]:
            nonlocal task

            async def call_func() -> T:
                await asyncio.sleep(wait_sec)
                print("[Debounce]: Running func")
                return await func(*args, **kwargs)

            if task and not task.done():
                print("[Debounce]: Debouncing / Called too soon")
                task.cancel()

            task = asyncio.create_task(call_func())
            return task

        return debounced

    return decorator


@async_debounce(7)
async def foo():
    print("[Foo]: Finished")


async def main():
    sleep_for = 0

    while True:
        await foo()

        print(f"[Caller]: Sleeping for {sleep_for} seconds")
        await asyncio.sleep(sleep_for)
        sleep_for = (sleep_for + 5) % 10 + 1


if __name__ == "__main__":
    asyncio.run(main())
