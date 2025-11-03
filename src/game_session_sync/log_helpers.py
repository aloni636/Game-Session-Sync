import dataclasses
import logging
import subprocess
from logging.handlers import RotatingFileHandler
from pprint import pformat
from typing import IO, cast

from game_session_sync.constants import LOG_PATH


# Open a new console window running PowerShell that echoes stdin lines
class Console:
    def __init__(self) -> None:
        self._p = subprocess.Popen(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoExit",
                "-Command",
                # Read from $input and print each line as-is
                "$input | ForEach-Object { $_ }",
            ],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            stdin=subprocess.PIPE,
            text=True,  # send str, not bytes
            bufsize=1,  # line-buffered
        )
        self.stdin = self._p.stdin

    def print(self, line: str):
        self._p.stdin = cast(
            IO[str], self._p.stdin
        )  # tells pylint p.stdin cannot be None
        self._p.stdin.write(line + "\n")
        self._p.stdin.flush()

    def kill(self):
        self._p.kill()


def dataclass_format(dataclass) -> str:
    return pformat(dataclasses.asdict(dataclass), indent=2, compact=False)


def setup_logging():
    # Common formatter
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s | %(message)s"
    )

    # Console handler (debug level)
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)

    # File handler (info level, rotation)
    file = RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file.setLevel(logging.INFO)
    file.setFormatter(fmt)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file)


def setup_test_logging(user_console: Console, level=logging.DEBUG):
    # Time only formatter
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(funcName)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Reroute log stream to terminal
    console = logging.StreamHandler(user_console.stdin)
    console.setLevel(level)
    console.setFormatter(fmt)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)
