import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence, TypeAlias, TypeVar
from zoneinfo import ZoneInfo

from notion_client import AsyncClient
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive, GoogleDriveFile

from game_session_sync.config import ConnectionConfig, NotionProperties
from game_session_sync.screenshot_producers.utils import parse_screenshot_filename

IO_TIMEOUT_SEC = 10

_metadata: TypeAlias = tuple[Path, datetime]


T = TypeVar("T")


def chunk_list(lst: list[T], n: int) -> Iterator[list[T]]:
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


@dataclass
class _SessionInfo:
    last_end: datetime
    drive_folder_id: str
    notion_page_id: str


# TODO: Convert drive object from pydrive2 to aiogoogle
class Uploader:
    def __init__(
        self,
        c_config: ConnectionConfig,
        notion_properties: NotionProperties,
        minimum_session_gap_min: int,
        minimum_session_length_min: int,
    ) -> None:
        self.notion_db_id = c_config.notion_database_id
        self.drive_root_id = c_config.drive_root_folder_id
        self.user_tz = ZoneInfo(c_config.notion_user_tz)
        self.notion_props = notion_properties
        self.minimum_session_gap_min = minimum_session_gap_min
        self.minimum_session_length_min = minimum_session_length_min

        self._notion = AsyncClient(auth=c_config.notion_api_token)
        gauth = GoogleAuth(c_config.drive_settings_file)
        if gauth.access_token_expired:
            gauth.LocalWebserverAuth()
        self._drive = GoogleDrive(gauth)

        self._stop_event = asyncio.Event()
        self._upload_task: dict[Path, asyncio.Task] = {}
        self.log = logging.getLogger(self.__class__.__name__)

    async def _upload(self, source_dir: Path) -> bool:
        self._stop_event.clear()
        # TODO: Use session_dirname to track session time-bounds by exact process lifetime

        # Design:
        # - _upload is called only after a session ends by the session manager.
        # - _upload can be stopped at any time to allow the manager to handle a new session
        # - Currently the screenshot writes dump to a single dir, but later each session object would create a new dir
        #   for the session itself with embedded timestamps at the dir name.
        #   That means that the current design should create new sessions, or update timestamps in notion before uploading
        # - Ideally, a clustering of screenshots would be used to update and create all new notion and drive folders
        #   and a second heavier pass would actually iterate over the screenshots and upload them to their respective session folders in drive
        # - Stopping can only be allowed at the second pass to protect notion as much as possible
        # - The third pass is at cleanup() call, as seen in self.upload(), and is responsible to enforce self.minimum_session_length_min
        #   by looking in notion for sessions which are smaller than the specified threshold AND are not the first session.
        #   This will avoid deleting sessions which are in-fact just a game crash (for example).
        #   It is guaranteed in the uploader logic that there would be no 2 consecutive sessions of the same title which are closer than self.minimum_session_gap_min
        #

        screenshots = [f for f in source_dir.iterdir() if f.is_file()]
        if not screenshots:
            return True

        # extract timestamp, groupby title
        by_title: dict[str, list[_metadata]] = {}
        for path in screenshots:
            title, timestamp, _ = parse_screenshot_filename(path.name, self.user_tz)
            by_title.setdefault(title, []).append((path, timestamp))

        # sortby timestamp, split by consecutive timestamp diff
        def split_by_gap(input_list: list[_metadata]) -> list[list[_metadata]]:
            input_list.sort(key=lambda v: v[1])

            out = [[input_list[0]]]
            for path, timestamp in input_list[1:]:
                _, prev_timestamp = out[-1][-1]
                diff_min = (timestamp - prev_timestamp).total_seconds() / 60
                # merge with last cluster
                if diff_min < self.minimum_session_gap_min:
                    out[-1].append((path, timestamp))
                # new cluster
                else:
                    out.append([(path, timestamp)])
            return out

        clusters: list[tuple[str, list[_metadata]]] = []
        for title, screenshot_list in by_title.items():
            splits = split_by_gap(screenshot_list)
            for split in splits:
                clusters.append((title, split))
        # sortby cluster start
        clusters.sort(key=lambda v: v[1][0][1])

        for title, screenshot_list in clusters:
            start: datetime = screenshot_list[0][1]
            info = await self._last_session(title)
            if (
                info is None  # new session
                or (start - info.last_end).total_seconds() / 60
                > self.minimum_session_gap_min  # gap too big
            ):
                info = await self._new_session(title, start)

            last_timestamp = None
            for chunk in chunk_list(screenshot_list, 8):
                # TODO: Integrate cleanup into _upload main loop
                last_timestamp = chunk[-1][1]
                await asyncio.gather(
                    *(
                        self._drive_upload_one(
                            info.drive_folder_id, str(path), path.name
                        )
                        for path, _ in chunk
                    )
                )
                if self._stop_event.is_set():
                    await self._update_notion_timestamp(
                        info.notion_page_id,
                        last_timestamp,
                    )
                    return False

            assert last_timestamp is not None
            await self._update_notion_timestamp(
                info.notion_page_id,
                last_timestamp,
            )
        return True

    # upload process cannot be run in multiple directories at the same time
    # because they both will race to delete files from it
    async def upload(self, source_dir: str):
        dirpath = Path(source_dir)
        task = self._upload_task.get(dirpath)
        if task is None:
            task = asyncio.create_task(self._upload(dirpath))
            task.add_done_callback(lambda _: self._upload_task.pop(dirpath, None))
            self._upload_task[dirpath] = task
        await task

    def stop(self):
        self._stop_event.set()

    async def _last_session(self, title: str) -> _SessionInfo | None:
        try:
            q: dict[str, Any] = await asyncio.wait_for(
                self._notion.databases.query(
                    database_id=self.notion_db_id,
                    filter={
                        "property": self.notion_props.title,
                        # https://developers.notion.com/reference/post-database-query-filter#select
                        "select": {"equals": title},
                    },
                    sorts=[
                        {"property": self.notion_props.end, "direction": "descending"}
                    ],
                    page_size=1,
                ),
                IO_TIMEOUT_SEC,
            )
            if q.get("results"):
                notion_page = q["results"][0]
                props = notion_page["properties"]
                session_id = props[self.notion_props.session_id]

                def get_utc_datetime(prop: str):
                    date_prop = props[prop]["date"]
                    iso_date_str = date_prop.get("end") or date_prop.get("start")
                    utc_date = datetime.fromisoformat(
                        iso_date_str.replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                    return utc_date

                last_end = get_utc_datetime(self.notion_props.end)
                last_start = get_utc_datetime(self.notion_props.start)
                self.log.info(
                    f"Last Notion session: end: {last_end.isoformat(timespec='seconds')}"
                )

                title_parent = await self._new_drive_dir(title, self.drive_root_id)
                session_folder = await self._new_drive_dir(
                    self._drive_timestamp(last_start), title_parent["id"]
                )
                return _SessionInfo(
                    last_end,
                    session_folder["id"],
                    notion_page["id"],
                )

            else:
                self.log.info(f"No sessions in Notion matching: {title}")

        except (
            KeyError,  # missing key in dictionary
            ValueError,  # iso parsing
            AttributeError,  # end_prop is None type
        ):
            self.log.info("Failed to parse Notion response.", exc_info=True)
        return None

    async def _new_session(self, title: str, start: datetime) -> _SessionInfo:
        start_str = self._drive_timestamp(start)
        session_id = f"{title} {start_str}"

        title_parent = await self._new_drive_dir(title, self.drive_root_id)
        session_folder = await self._new_drive_dir(start_str, title_parent["id"])

        notion_page = await self._new_notion_page(
            session_id,
            title,
            session_id,
            start,
            start,
            self._get_drive_embed_link(session_folder),
        )
        return _SessionInfo(start, session_folder["id"], notion_page["id"])

    # --- Drive helpers ---
    @staticmethod
    def _get_drive_embed_link(file: GoogleDriveFile) -> str:
        # See: https://stackoverflow.com/questions/20681974/how-to-embed-a-google-drive-folder-in-a-web-page
        return f"https://drive.google.com/embeddedfolderview?id={file['id']}#grid"

    @staticmethod
    def _get_drive_folder_link(file: GoogleDriveFile) -> str:
        return f"https://drive.google.com/drive/folders/{file['id']}"

    @staticmethod
    def _drive_query_escape(s: str) -> str:
        # https://developers.google.com/workspace/drive/api/guides/search-files#examples
        return s.replace("\\", "\\\\").replace("'", r"\'")

    async def _new_drive_dir(self, name: str, parent_id: str | None) -> GoogleDriveFile:
        # TODO: Use aiogoogle for true async work
        def f() -> tuple[GoogleDriveFile, bool]:
            q = (
                "mimeType='application/vnd.google-apps.folder' and trashed=false "
                f"and title='{self._drive_query_escape(name)}'"
                + (f" and '{parent_id}' in parents" if parent_id else "")
            )
            found = self._drive.ListFile({"q": q}).GetList()
            if found:
                return found[0], False
            meta: dict[str, Any] = {
                "title": name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_id:
                meta["parents"] = [{"id": parent_id}]
            file = self._drive.CreateFile(meta)
            file.Upload()
            file.InsertPermission(
                {"type": "anyone", "role": "reader", "allowFileDiscovery": False}
            )
            return file, True

        file, created = await asyncio.wait_for(asyncio.to_thread(f), IO_TIMEOUT_SEC)
        if created:
            self.log.info(
                f"Created Drive folder {name} ({file['id']}) with parent {parent_id}"
            )
        else:
            self.log.debug(
                f"Reusing Drive folder {name} ({file['id']}) with parent {parent_id}"
            )
        return file

    async def _drive_upload_one(
        self, drive_folder_id: str, path: str, drive_file_name: str
    ) -> GoogleDriveFile:
        # TODO: Use aiogoogle for true async work
        def f():
            file = self._drive.CreateFile(
                {"title": drive_file_name, "parents": [{"id": drive_folder_id}]}
            )
            file.SetContentFile(path)
            file.Upload()
            return file

        file = await asyncio.wait_for(asyncio.to_thread(f), IO_TIMEOUT_SEC)
        self.log.debug(
            f"Uploaded to drive: {path} -> {drive_folder_id!r}/{drive_file_name!r}"
        )
        self.log.debug(f"Deleting file: {path!r}")
        Path(path).unlink()
        return file

    def _notion_local_iso(self, dt: datetime) -> str:
        return dt.astimezone(self.user_tz).isoformat(timespec="seconds")

    def _drive_timestamp(self, dt: datetime) -> str:
        return dt.astimezone(self.user_tz).strftime("%Y-%m-%d %H_%M")

    async def _update_notion_timestamp(self, page_id: str, end: datetime):
        props = {
            self.notion_props.end: {
                "date": {
                    "start": self._notion_local_iso(end),
                    "end": None,
                }
            },
        }
        await self._notion.pages.update(page_id, properties=props)

    async def _new_notion_page(
        self,
        name: str,
        title: str,
        session_id: str,
        start: datetime,
        end: datetime,
        embed_link: str,
    ) -> dict[str, Any]:

        # https://developers.notion.com/reference/page-property-values
        props = {
            self.notion_props.name: {"title": [{"text": {"content": name}}]},
            self.notion_props.title: {"select": {"name": title}},
            self.notion_props.session_id: {
                "rich_text": [{"text": {"content": session_id}}]
            },
            self.notion_props.start: {
                "date": {
                    "start": self._notion_local_iso(start),
                    "end": None,
                }
            },
            self.notion_props.end: {
                "date": {
                    "start": self._notion_local_iso(end),
                    "end": None,
                }
            },
            self.notion_props.drive_link: {"url": embed_link},
        }
        # query for the page with the session id
        q: dict[str, Any] = await asyncio.wait_for(
            self._notion.databases.query(
                database_id=self.notion_db_id,
                filter={
                    "property": self.notion_props.session_id,
                    "rich_text": {"equals": session_id},
                },
                page_size=1,
            ),
            IO_TIMEOUT_SEC,
        )
        # upsert branch (shouldn't happen tho...)
        if q["results"]:
            page_id = q["results"][0]["id"]
            # avoid updating page name to allow the user to modify the page title during a session
            props.pop(self.notion_props.name, None)
            self.log.info(f"Updating Notion page {page_id} for session {session_id}")
            page = await self._notion.pages.update(page_id, properties=props)
        # insert branch
        else:
            self.log.info(
                f"Creating Notion page for session {session_id} in database {self.notion_db_id}"
            )
            page = await self._notion.pages.create(
                parent={"database_id": self.notion_db_id},
                properties=props,
            )

            await asyncio.wait_for(
                self._notion.blocks.children.append(
                    block_id=page["id"],
                    children=[
                        {
                            "object": "block",
                            "type": "embed",
                            "embed": {"url": embed_link},
                        }
                    ],
                ),
                IO_TIMEOUT_SEC,
            )
            self.log.debug(
                f"Added embed block to Notion page {page['id']} pointing to {embed_link}"
            )
        return page


async def _main():
    from .config import load_config
    from .log_helpers import Console, setup_test_logging

    OBSERVATORY = "./observatory"
    console = Console()
    setup_test_logging(console)

    config = load_config("config.dev.yaml")
    uploader = Uploader(
        config.connection,
        config.notion_properties,
        config.session.minimum_session_gap_min,
        config.session.minimum_session_length_min,
    )
    try:
        async with asyncio.TaskGroup() as tg:
            while True:
                user_input = (
                    await asyncio.to_thread(input, "[q: quit | u: upload | s: stop upload] > ")
                ).strip()
                if user_input == "q":
                    break
                if user_input == "u":
                    tg.create_task(uploader.upload(OBSERVATORY))
                if user_input == "s":
                    uploader.stop()
    finally:
        uploader.stop()
        console.kill()


if __name__ == "__main__":
    asyncio.run(_main())
