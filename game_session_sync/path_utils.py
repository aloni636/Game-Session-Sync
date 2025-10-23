from __future__ import annotations

from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


def resolve_path(
    path: PathLike,
) -> Path:
    """Resolve a path into an absolute Path."""
    return Path(path).expanduser().resolve(strict=True)
