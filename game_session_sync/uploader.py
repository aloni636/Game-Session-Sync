# Game Session Sync - compact (pandas + PyDrive2 + Notion) + logging + toast
# Deps: pandas python-dotenv notion-client pydrive2 win11toast
# Poetry: poetry add pandas python-dotenv notion-client pydrive2 win11toast

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from notion_client import AsyncClient
from PIL import Image
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive, GoogleDriveFile

from game_session_sync.config import ConnectionConfig, NotionProperties

from .screenshot_producers.types import BaseScreenshot

IO_TIMEOUT_SEC = 10


@dataclass
class _SessionInfo:
    last_end: datetime
    drive_folder_id: str
    notion_page_id: str


# TODO: Convert drive object from pydrive2 to aiogoogle
class Uploader:
    # TODO: write a 1-3 line docstring for the purpose of this class based on the context from the entire repo
    def __init__(
        self,
        c_config: ConnectionConfig,
        notion_properties: NotionProperties,
        minimum_session_gap_min: int,
    ) -> None:
        self.notion_db_id = c_config.notion_database_id
        self.drive_root_id = c_config.drive_root_folder_id
        self.user_tz = ZoneInfo(c_config.notion_user_tz)
        self.minimum_session_gap_min = minimum_session_gap_min
        self.notion_props = notion_properties

        self._notion = AsyncClient(auth=c_config.notion_api_token)
        gauth = GoogleAuth(c_config.drive_settings_file)
        if gauth.access_token_expired:
            gauth.LocalWebserverAuth()
        self._drive = GoogleDrive(gauth)

        self._session_title_cache: dict[str, _SessionInfo] = dict()

        self.log = logging.getLogger(self.__class__.__name__)

    async def upload(self, title: str, screenshot: BaseScreenshot):
        image = screenshot.image
        time = screenshot.time

        info = self._session_title_cache.get(title, None)
        if info is None:  # at first upload cache is empty
            self.log.debug(f"Cache miss for title {title}; querying remote state")
            info = await self._get_last_session(title)

        gap_min = None
        if info is None or (
            gap_min := (time - info.last_end).total_seconds() / 60
            >= self.minimum_session_gap_min
        ):
            gap_desc = "n/a" if gap_min is None else f"{gap_min:.1f}"
            self.log.info(
                f"Creating new remote session for {title} "
                f"(gap={gap_desc} min threshold={self.minimum_session_gap_min})"
            )
            info = await self._create_session(title, time)
        else:
            self.log.info(
                f"Reusing remote session for {title} "
                f"(page_id={info.notion_page_id} folder_id={info.drive_folder_id})"
            )

        self._session_title_cache[title] = info
        self._session_title_cache[title].last_end = time
        await self._drive_upload_one(
            info.drive_folder_id,
            image,
            f"{title} {time.strftime('%Y.%m.%d - %H.%M.%S.%f')}",
        )

        def local_iso(dt: datetime) -> str:
            return dt.astimezone(self.user_tz).isoformat(timespec="seconds")

        page_id = info.notion_page_id
        props = {
            self.notion_props.end: {
                "date": {
                    "start": local_iso(screenshot.time),
                    "end": None,
                }
            },
        }
        page = await self._notion.pages.update(page_id, properties=props)
        self.log.info(
            f"Uploaded screenshot for {title} to Drive folder {info.drive_folder_id} and notion page {page_id}"
        )

    # async def get_last_session(self, title: str, max_gap_min: int) -> Session | None:
    #     info = await self._get_last_session(title)
    #     if info is None:
    #         return None
    #     now = datetime.now()
    #     now - info.last_end

    # --- Notion state (last uploaded end) ---
    async def _get_last_session(self, title: str) -> _SessionInfo | None:
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
                session_id = notion_page["properties"][self.notion_props.session_id]

                def get_utc_datetime(prop: str):
                    date_prop = notion_page["properties"][prop]["date"]
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

                start_str = last_start.astimezone(self.user_tz).strftime(
                    "%Y-%m-%d %H_%M"
                )

                title_parent = await self._upsert_drive_folder(
                    title, self.drive_root_id
                )
                session_folder = await self._upsert_drive_folder(
                    start_str, title_parent["id"]
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

    async def _create_session(self, title: str, start: datetime) -> _SessionInfo:
        start_str = start.astimezone(self.user_tz).strftime("%Y-%m-%d %H_%M")
        session_id = f"{title} {start_str}"

        title_parent = await self._upsert_drive_folder(title, self.drive_root_id)
        session_folder = await self._upsert_drive_folder(start_str, title_parent["id"])

        notion_page = await self._upsert_notion(
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

    async def _upsert_drive_folder(
        self, name: str, parent_id: str | None
    ) -> GoogleDriveFile:
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
        self, drive_folder_id: str, image: Image.Image, drive_file_name: str
    ) -> GoogleDriveFile:
        # TODO: Use aiogoogle for true async work
        def f():
            file = self._drive.CreateFile(
                {"title": drive_file_name, "parents": [{"id": drive_folder_id}]}
            )
            buf = BytesIO()
            image.save(buf, format="PNG")
            file.content = buf
            file.Upload()
            return file

        file = await asyncio.wait_for(asyncio.to_thread(f), IO_TIMEOUT_SEC)
        self.log.debug(
            f"Drive upload complete: file={drive_file_name} folder={drive_folder_id}"
        )
        return file

    async def _upsert_notion(
        self,
        name: str,
        title: str,
        session_id: str,
        start: datetime,
        end: datetime,
        embed_link: str,
    ) -> dict[str, Any]:

        def local_iso(dt: datetime) -> str:
            return dt.astimezone(self.user_tz).isoformat(timespec="seconds")

        # https://developers.notion.com/reference/page-property-values
        props = {
            self.notion_props.name: {"title": [{"text": {"content": name}}]},
            self.notion_props.title: {"select": {"name": title}},
            self.notion_props.session_id: {
                "rich_text": [{"text": {"content": session_id}}]
            },
            self.notion_props.start: {
                "date": {
                    "start": local_iso(start),
                    "end": None,
                }
            },
            self.notion_props.end: {
                "date": {
                    "start": local_iso(end),
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
        # Upsert branch
        if q["results"]:
            page_id = q["results"][0]["id"]
            # avoid updating page name to allow the user to modify the page title during a session
            props.pop(self.notion_props.name, None)
            self.log.info(f"Updating Notion page {page_id} for session {session_id}")
            page = await self._notion.pages.update(page_id, properties=props)
        # Insert branch
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
