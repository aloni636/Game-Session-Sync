from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeAlias

from ..types import LoggingQueue

_now_field = field(default_factory=lambda: datetime.now().astimezone())


@dataclass(slots=True)
class BaseWindowEvent:
    title: str
    time: datetime = _now_field


@dataclass(slots=True)
class _InputEvent:
    idle_seconds: float
    timestamp: datetime = _now_field


@dataclass(slots=True)
class WindowOpenEvent(BaseWindowEvent):
    pass


@dataclass(slots=True)
class WindowMinimizedEvent(BaseWindowEvent):
    pass


@dataclass(slots=True)
class WindowFullscreenEvent(BaseWindowEvent):
    pass


@dataclass(slots=True)
class WindowCloseEvent(BaseWindowEvent):
    pass


@dataclass(slots=True)
class InputIdleEvent(_InputEvent):
    pass


@dataclass(slots=True)
class InputActiveEvent(_InputEvent):
    pass


EventBus: TypeAlias = LoggingQueue[
    WindowOpenEvent
    | WindowMinimizedEvent
    | WindowFullscreenEvent
    | WindowCloseEvent
    | InputIdleEvent
    | InputActiveEvent
]
