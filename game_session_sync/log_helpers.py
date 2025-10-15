import dataclasses
import logging
from logging.handlers import RotatingFileHandler
from pprint import pformat

# TODO: Isolate experiments by reimplementing Console here
from experiments.console import Console


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
        "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file.setLevel(logging.INFO)
    file.setFormatter(fmt)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file)


def setup_test_logging(user_console: Console):
    # Time only formatter
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(funcName)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Reroute log stream to terminal
    console = logging.StreamHandler(user_console.stdin)
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
