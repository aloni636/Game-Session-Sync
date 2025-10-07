from asyncio import Queue
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeAlias

from PIL import Image

from ..types import LoggingQueue


@dataclass(slots=True)
class BaseScreenshot:
    image: Image.Image
    time: datetime = field(default_factory=lambda: datetime.now().astimezone())


@dataclass(slots=True)
class PeriodicScreenshot(BaseScreenshot):
    pass


@dataclass(slots=True)
class ManualScreenshot(BaseScreenshot):
    pass


ScreenshotBus: TypeAlias = LoggingQueue[PeriodicScreenshot | ManualScreenshot]
