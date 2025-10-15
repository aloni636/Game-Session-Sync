import subprocess
from typing import IO, cast


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
