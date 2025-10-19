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
class BaseInputEvent:
    idle_seconds: float
    timestamp: datetime = _now_field


# NOTE: Not in use as there's no prep work to do before starting a session
# @dataclass(slots=True)
# class WindowOpenEvent(BaseWindowEvent):
#     pass


@dataclass(slots=True)
class GameMinimizedEvent(BaseWindowEvent):
    pass


@dataclass(slots=True)
class GameFullscreenEvent(BaseWindowEvent):
    pass


@dataclass(slots=True)
class GameCloseEvent(BaseWindowEvent):
    pass


@dataclass(slots=True)
class InputIdleEvent(BaseInputEvent):
    pass


@dataclass(slots=True)
class InputActiveEvent(BaseInputEvent):
    pass


EventBus: TypeAlias = LoggingQueue[
    GameMinimizedEvent
    | GameFullscreenEvent
    | GameCloseEvent
    | InputIdleEvent
    | InputActiveEvent
]
