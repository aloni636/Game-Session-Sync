import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


# credits: https://gist.github.com/medihack/7af1f98ea468aa7ad00102c7d84c65d8
def async_debounce(
    wait_sec: float,
):
    def decorator(
        func: Callable[..., Awaitable[T]],
    ):
        task: Optional[asyncio.Task[T]] = None

        @wraps(func)
        async def debounced(*args: Any, **kwargs: Any) -> asyncio.Task[T]:
            nonlocal task

            async def call_func() -> T:
                await asyncio.sleep(wait_sec)
                return await func(*args, **kwargs)

            if task and not task.done():
                task.cancel()

            task = asyncio.create_task(call_func())
            return task

        return debounced

    return decorator
