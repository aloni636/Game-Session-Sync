import asyncio

import psutil

import win32api
import win32con
import win32event

from experiments.console import Console


def wait_pid_exit(pid: int, console: Console):
    # Minimal rights. Fails on protected processes but fine for most games.
    console.print(f"Waiting for pid {pid}")
    handle = win32api.OpenProcess(
        win32con.SYNCHRONIZE | win32con.PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        pid,
    )

    # Block in a worker thread so your main loop stays free
    rc = win32event.WaitForSingleObject(handle, win32event.INFINITE)
    if rc == win32con.WAIT_OBJECT_0:
        console.print(f"CLOSED: {pid}")

    return


async def main():
    console = Console()
    tasks = []

    while True:
        user_input = await asyncio.to_thread(
            input, f"[q: quit | pid: process-id ({len(tasks)} waiting)] > "
        )
        user_input = user_input.strip()
        if user_input == "q":
            print("Quitting")
            console.kill()
            return
        pid = int(user_input)
        process = psutil.Process(pid)
        print(f"Waiting for pid {pid}: {process.name()}")
        tasks.append(
            asyncio.create_task(asyncio.to_thread(wait_pid_exit, pid, console))
        )


if __name__ == "__main__":
    asyncio.run(main())
