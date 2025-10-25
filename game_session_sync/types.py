import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import Event
from functools import wraps
from typing import Generic, TypeVar, final


class Producer(ABC):
    """Wraps `__init__` and `async run()` for logging, and provides `self._stop_event` inside
    the `async run()` method for cooperative producer loop cancellation.
    """

    def __init__(self) -> None:
        self._stop_event = Event()
        self.log = logging.getLogger(self.__class__.__name__)

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        # automatic run wrapper
        original_run = cls.run

        @wraps(original_run)
        async def _wrapped_run(self):
            self.log.info("Received run signal")
            self._stop_event.clear()
            return await original_run(self)

        cls.run = _wrapped_run

        # automatic super().__init__()
        original_init = cls.__init__
        if original_init is not Producer.__init__:

            @wraps(original_init)
            def wrapped_init(self, *args, **kwargs):
                Producer.__init__(self)
                original_init(self, *args, **kwargs)
                self.log.info(f"Fully initialized")

            cls.__init__ = wrapped_init

    @abstractmethod
    async def run(self) -> None:
        pass

    @final
    def stop(self):
        self.log.info(f"Received stop signal")
        self._stop_event.set()


T = TypeVar("T")


class LoggingQueue(asyncio.Queue[T], Generic[T]):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._log = logging.getLogger(self.__class__.__name__)

    async def put(self, item: T) -> None:
        self._log.info(f"Putting: {item!r}")
        return await super().put(item)

    def put_nowait(self, item: T) -> None:
        self._log.info(f"Putting: {item!r}")
        return super().put_nowait(item)

    async def get(self) -> T:
        item = await super().get()
        self._log.info(f"Getting: {item!r}")
        return item
