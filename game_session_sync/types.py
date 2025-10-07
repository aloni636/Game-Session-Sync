import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import Event
from functools import wraps
from typing import Generic, TypeVar, final

logger = logging.getLogger("AbstractProducer")


class Producer(ABC):
    """Wraps `__init__` and `async run()` for logging, and provides `self._stop_event` inside
    the `async run()` method for cooperative producer loop cancellation.
    """

    def __init__(self) -> None:
        self._stop_event = Event()
        logger.debug(f"{self.__class__.__name__} fully initialized")

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        # automatic run wrapper
        original_run = cls.run

        @wraps(original_run)
        async def _wrapped_run(self):
            logger.debug(f"{self.__class__.__name__} received run signal")
            self._stop_event.clear()
            return await original_run(self)

        cls.run = _wrapped_run

        # automatic super().__init__()
        original_init = cls.__init__
        if original_init is not Producer.__init__:

            @wraps(original_init)
            def wrapped_init(self, *args, **kwargs):
                Producer.__init__(self)
                return original_init(self, *args, **kwargs)

            cls.__init__ = wrapped_init

    @abstractmethod
    async def run(self) -> None:
        pass

    @final
    def stop(self):
        logger.debug(f"{self.__class__.__name__} received stop signal")
        self._stop_event.set()


T = TypeVar("T")


class LoggingQueue(asyncio.Queue[T], Generic[T]):
    async def put(self, item: T) -> None:
        logging.debug(f"Pushing event into EventBus queue: {item!r}")
        return await super().put(item)

    def put_nowait(self, item: T) -> None:
        logging.debug(f"Pushing event into EventBus queue: {item!r}")
        return super().put_nowait(item)

    async def get(self) -> T:
        item = await super().get()
        logging.debug(f"Popping event from EventBus queue: {item!r}")
        return item
