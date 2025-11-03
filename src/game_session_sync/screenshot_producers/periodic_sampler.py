import asyncio
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import mss
import mss.tools

from ..naming_utils import build_screenshot_filename
from ..types import Producer


# TODO: Switch to DXcam and turbojpeg
class PeriodicSampler(Producer):
    def __init__(
        self, interval_sec: int, target_dir: Path, title: str, tz: ZoneInfo
    ) -> None:
        self.interval_sec = interval_sec
        self.target_dir = target_dir
        self.title = title
        self.tz = tz

    async def run(self):
        next_time = time.perf_counter()
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                # TODO: select the monitor based on the game (fullscreen) window
                sct_img = sct.grab(sct.monitors[0])  # all monitors combined
                self.log.info(f"Took screenshot: {sct_img.size}")
                dct_path = self.target_dir / build_screenshot_filename(
                    self.title, ".png", self.tz
                )
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=dct_path)

                # sct.grab and to_png are slow and require drift handling
                next_time += self.interval_sec
                sleep = next_time - time.perf_counter()
                if sleep < 0:
                    next_time = time.perf_counter()  # reset if too late
                    sleep = self.interval_sec
                try:
                    await asyncio.wait_for(self._stop_event.wait(), sleep)
                except asyncio.TimeoutError:
                    continue


if __name__ == "__main__":
    from pathlib import Path

    import tzlocal

    from game_session_sync.test_helpers import producer_test_run

    watcher = PeriodicSampler(
        3, Path("./images"), "Deus Ex Mankind Divided", tzlocal.get_localzone()
    )
    asyncio.run(producer_test_run(watcher))
