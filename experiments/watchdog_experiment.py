import os

from PIL import Image
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from experiments.console import Console


class Handler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()

    # def on_created(self, event: FileSystemEvent) -> None:
    #     print(
    #         "[{event_type}] Event received: {path}".format(
    #             path=event.src_path,
    #             event_type="directory" if event.is_directory else "file",
    #         )
    #     )
    #     if event.is_directory:
    #         return

    #     # watchdog may supply bytes on some backends; normalize to str.
    #     src_path = os.fsdecode(event.src_path)
    #     print("Reading file...")
    #     with open(src_path) as f:
    #         content = f.read()
    #     print("File read: {file_size}".format(file_size=len(content.encode("utf-8"))))

    #     # with Image.open(src_path) as img:
    #     #     img.load()
    #     # os.remove(src_path)
    def on_any_event(self, event: FileSystemEvent) -> None:
        print(event)


if __name__ == "__main__":
    handler = Handler()
    observer = Observer()
    observer.schedule(handler, "./observatory", recursive=True)

    try:
        observer.start()
        print("Watching... ctrl+c to stop")
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()
