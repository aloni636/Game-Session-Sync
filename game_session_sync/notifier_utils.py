from datetime import datetime
from pathlib import Path
from random import Random

from win11toast import notify, update_progress

from .constants import APP_NAME, LOG_PATH

_rng = Random(42)


def _plural(sequence, name: str):
    suffix = "" if len(sequence) == 1 else "s"
    return f"{len(sequence)} {name}{suffix}"


def notify_error(e: Exception):
    notify(
        f"{APP_NAME}: Error",
        f"{type(e).__name__}: {str(e)}",
        button={
            "activationType": "protocol",
            "arguments": str("vscode://file/" / Path(LOG_PATH).expanduser().absolute()),
            "content": "Open logs in VSCode",
        },
    )


class ProgressNotifier:
    def __init__(self, clusters: list[tuple[str, list[tuple[Path, datetime]]]]) -> None:
        self._num_sessions: int = len(clusters)
        self._session_names: list[str] = [c[0] for c in clusters]
        self._session_idx: int = 0

        self._num_files = sum([len(c[1]) for c in clusters])
        self._files_uploaded: int = 0

        self._tag = f"game_sync_{_rng.randint(0, 0xFFFFFF):06x}"

        notify(
            title=f"{APP_NAME}: Uploading {_plural(clusters, 'Session')}",
            progress=self._build_progress_dict(),
            tag=self._tag,
        )

    def _build_progress_dict(self):
        return {
            "title": f"{self._session_idx+1}/{self._num_sessions} {self._session_names[self._session_idx]}",
            "status": "Uploading...",
            "value": self._files_uploaded / self._num_files,
            "valueStringOverride": f"{self._files_uploaded}/{self._num_files}",
        }

    def _update_progress(self):
        if self._session_idx == self._num_sessions:  # avoid out of bound indexing
            return
        update_progress(progress=self._build_progress_dict(), tag=self._tag)

    def increment_files(self, num_files: int):
        self._files_uploaded += num_files
        self._update_progress()

    def increment_session(self):
        self._session_idx += 1
        self._update_progress()

    def finish(self):
        update_progress({"status": "Finished"}, tag=self._tag)
