# Game Session Sync - compact (pandas + PyDrive2 + Notion) + logging + toast
# Deps: pandas python-dotenv notion-client pydrive2 win11toast
# Poetry: poetry add pandas python-dotenv notion-client pydrive2 win11toast

import hashlib
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import partial
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import dotenv_values, find_dotenv, load_dotenv
from notion_client import APIResponseError, Client
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive, GoogleDriveFile
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Note: notify() is preferable to toast() because it isn't blocking
from win11toast import notify, update_progress


# --- config ---
def get_env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise KeyError(f"Required environment variable {key} is not set")
    return value


env_path = find_dotenv()
if env_path:
    load_dotenv(env_path)
    print(dotenv_values(env_path))
    env_path_log_msg = f"Loaded dotenv file: {env_path}"
else:
    env_path_log_msg = "No dotenv file found"
print(env_path_log_msg)


# --- environment variables ---
# required
SCREENSHOT_DIR = Path(get_env("SCREENSHOT_DIR"))
DRIVE_PARENT_ID = get_env("DRIVE_PARENT_ID")
NOTION_TOKEN = get_env("NOTION_TOKEN")
NOTION_DB_ID = get_env("NOTION_DB_ID")
MINIMUM_SESSION_GAP = int(get_env("MINIMUM_SESSION_GAP", "30"))
LOCAL_TZ = ZoneInfo(get_env("LOCAL_TZ"))
# optional
MAX_WORKERS = int(get_env("UPLOAD_WORKERS", "6"))
APP_NAME = get_env("APP_NAME", "Game Session Sync")
LOG_DIR = Path(get_env("LOG_DIR", "."))
LOG_FILENAME = get_env("LOG_FILENAME", "game_session_sync.log")

NAME_RE = (
    r"^(.*?)\s+(?:Screenshot\s+)?"
    r"(\d{4}\.\d{2}\.\d{2})\s*-\s*"
    r"(\d{2}\.\d{2}\.\d{2})"
    r".*\.(png|mp4)$"
)


# --- logging ---
def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / LOG_FILENAME

    logger = logging.getLogger("sessions")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    fh = RotatingFileHandler(
        log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.debug(f"Logger initialized in path {log_path}")
    return logger


logger = setup_logging()
logger.debug(env_path_log_msg)


# class GameSessionSync(FileSystemEventHandler):
#     async def hydrate(self):

#         pass

#     def __init__(self) -> None:
#         super().__init__()
#         gauth = GoogleAuth()
#         gauth.LocalWebserverAuth()
#         self.drive = GoogleDrive(gauth)
#         logger.info("Authenticated to Google Drive")

#         self.notion = Client(auth=NOTION_TOKEN)
#         logger.info("Initialized Notion client")

#     def on_any_event(self, event: FileSystemEvent) -> None:
#         # event.
#         last_start, last_end = get_last_gaming_session(notion)
#         screenshots_df = get_screenshots_df(last_start, last_end)

#         upload_sessions(screenshots_df, drive, notion)

#         elapsed = time.time() - start
#         logger.info(f"Finished in {elapsed:.1f} seconds")
#         print(event)

#     pass


# --- Notion state (last uploaded end) ---
def get_last_gaming_session(notion: Client) -> tuple[datetime, datetime]:
    last_start = datetime.min.replace(tzinfo=timezone.utc)
    last_end = datetime.min.replace(tzinfo=timezone.utc)
    try:
        q: dict[str, Any] = notion.databases.query(  # type: ignore
            database_id=NOTION_DB_ID,
            sorts=[{"property": "End", "direction": "descending"}],
            page_size=1,
        )
        if q.get("results"):

            def get_utc_datetime(prop: str):
                date_prop = q["results"][0]["properties"][prop]["date"]
                iso_date_str = date_prop.get("end") or date_prop.get("start")
                utc_date = datetime.fromisoformat(
                    iso_date_str.replace("Z", "+00:00")
                ).astimezone(timezone.utc)
                return utc_date

            last_end = get_utc_datetime("End")
            last_start = get_utc_datetime("Start")
            logger.info(
                f"Last Notion session: start: {last_start.isoformat(timespec='seconds')} end: {last_end.isoformat(timespec='seconds')}"
            )
        else:
            logger.info("No sessions in Notion. Using epoch.")

    # handle cases of invalid NOTION_DB_ID, i.e.
    # notion_client.errors.APIResponseError: Could not find database with ID: {NOTION_DB_ID}. Make sure the relevant pages and databases are shared with your integration.
    except APIResponseError as e:
        logger.exception(f"Failed to fetch data from notion DB with ID {NOTION_DB_ID}")
        raise e

    # KeyError - missing key in dictionary, ValueError - iso parsing, AttributeError - end_prop is None type
    except (KeyError, ValueError, AttributeError):
        logger.info(
            "Failed to parse Notion response. Using minimum epoch.", exc_info=True
        )

    return last_start, last_end


class EarlyExit(Exception):
    pass


# --- build df (vectorized) ---
def get_screenshots_df(last_start: datetime, last_end: datetime) -> pd.DataFrame:
    files = [f for f in SCREENSHOT_DIR.rglob("*") if f.is_file()]
    logger.debug(f"Found {len(files)} initial file entries in {SCREENSHOT_DIR}")

    if not files:
        notify(APP_NAME, f"{SCREENSHOT_DIR.resolve()} Is Empty")
        logger.info(f"{SCREENSHOT_DIR} is empty")
        raise EarlyExit

    df = pd.DataFrame({"name": [p.name for p in files], "path": files})
    ext = df["name"].str.extract(NAME_RE, flags=re.IGNORECASE)
    df["title"] = ext[0].str.strip().str.replace(r"\s+", " ", regex=True)
    df["dt"] = pd.to_datetime(
        (ext[1].fillna("") + " " + ext[2].fillna("")),
        format="%Y.%m.%d %H.%M.%S",
        errors="coerce",
    )
    before = len(df)
    df["dt"] = (
        df["dt"]
        .dt.tz_localize(LOCAL_TZ, ambiguous="infer", nonexistent="shift_forward")
        .dt.tz_convert(timezone.utc)
    )
    df = (
        df.dropna(subset=["title", "dt"])
        .sort_values(["title", "dt"])
        .reset_index(drop=True)
    )
    logger.debug(f"Parsed {len(df)}/{before} into valid timeline rows")

    gap = df.groupby("title")["dt"].diff().dt.total_seconds().div(60)
    new_session = gap.isna() | (gap >= MINIMUM_SESSION_GAP)
    df["session_group"] = new_session.groupby(df["title"]).cumsum().astype(int)

    groupby = df.groupby(["title", "session_group"], as_index=False)
    df["start"] = groupby["dt"].transform("min")
    df["end"] = groupby["dt"].transform("max")
    df["drive_name"] = (
        df["title"]
        + " "
        + df["start"].dt.tz_convert(LOCAL_TZ).dt.strftime("%Y-%m-%d %H:%M:%S")
    )

    before = len(df)
    df = df[
        df["dt"].dt.floor("min") > last_end
    ]  # Note: last_end is capped by notion to minutes frequency
    logger.debug(f"Filtered {len(df)}/{before} into entries ready to upload")

    if df.empty:
        logger.info(
            f"No new screenshots in {SCREENSHOT_DIR} after {last_end.isoformat(timespec='minutes')}"
        )
        raise EarlyExit

    sessions = df.groupby(["title", "start", "end", "drive_name"], as_index=False).agg(
        count=("path", "size"),
        paths=("path", list),
        names=("name", list),
    )
    logger.info(f"Aggregated {len(df)} files into {len(sessions)} sessions")

    logger.info(f"Sessions ready to upload: {len(sessions)}")
    return sessions


# --- Drive helpers ---
def create_embed_link(file: GoogleDriveFile) -> str:
    # See: https://stackoverflow.com/questions/20681974/how-to-embed-a-google-drive-folder-in-a-web-page
    return f"https://drive.google.com/embeddedfolderview?id={file['id']}#grid"


def create_drive_folder_link(file: GoogleDriveFile) -> str:
    return f"https://drive.google.com/drive/folders/{file['id']}"


def _gq_escape(s: str) -> str:
    # https://developers.google.com/workspace/drive/api/guides/search-files#examples
    return s.replace("\\", "\\\\").replace("'", r"\'")


def upsert_folder(
    name: str, parent_id: str | None, drive: GoogleDrive
) -> GoogleDriveFile:
    q = (
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        f"and title='{_gq_escape(name)}'"
        + (f" and '{parent_id}' in parents" if parent_id else "")
    )
    found = drive.ListFile({"q": q}).GetList()
    if found:
        return found[0]
    meta = {"title": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [{"id": parent_id}]  # type: ignore
    file = drive.CreateFile(meta)
    file.Upload()
    file.InsertPermission(
        {"type": "anyone", "role": "reader", "allowFileDiscovery": False}
    )
    logger.info(f"Created {name} folder in Google Drive with parent ID {parent_id}")
    return file


def upload_files_concurrent(
    drive: GoogleDrive,
    drive_folder_id: str,
    local_paths: list[Path],
    drive_names: list[str],
    callback: Callable[[int], Any] | None = None,
) -> int:

    current_files = drive.ListFile(
        {
            "q": f"'{drive_folder_id}' in parents and trashed=false",
            "fields": "items(id,title)",
        }
    ).GetList()
    if set((f.name for f in local_paths)).issubset((f["title"] for f in current_files)):
        if callback:
            callback(len(local_paths))
        logger.info(
            f"Fast skipped drive folder {drive_folder_id} because all local file names are in drive folder"
        )
        return len(local_paths)

    def local_md5(local_path: Path):
        with open(local_path, "rb") as f:
            return hashlib.file_digest(f, "md5").hexdigest()

    def drive_bytes_and_md5(drive_name: str) -> tuple[int | None, str | None]:
        q = f"'{drive_folder_id}' in parents and title = '{drive_name}' and trashed = false"
        files = drive.ListFile(
            {"q": q, "maxResults": 1, "fields": "items(id,fileSize,md5Checksum)"}
        ).GetList()
        # file doesn't exist
        if not files:
            return None, None
        f = files[0]
        # file exists but doesn't have fileSize or md5Checksum (folder or symlinks)
        if ("fileSize" not in f) or ("md5Checksum" not in f):
            return None, None
        return int(f.get("fileSize", 0)), f.get("md5Checksum")

    def upload_one(local_path: Path, drive_name: str) -> str | None:
        drive_bytes, drive_md5 = drive_bytes_and_md5(drive_name)
        # use short circuit to avoid computing local_md5 for nothing
        if (local_path.stat().st_size == drive_bytes) and (
            local_md5(local_path) == drive_md5
        ):
            logger.debug(
                f"Skipped '{local_path}' due to equal size and md5 hash compared to '{drive_name}' in Google Drive"
            )
            return drive_name
        for attempt in range(3):
            try:
                file = drive.CreateFile(
                    {"title": drive_name, "parents": [{"id": drive_folder_id}]}
                )
                file.SetContentFile(str(local_path))
                file.Upload()
                return drive_name
            except Exception as e:
                logger.warning(
                    f"Failed to upload {local_path} to {drive_name} under parent id {drive_folder_id}"
                )
                if attempt == 2:
                    raise e
                time.sleep(1.5 * (attempt + 1))

    uploaded = 0
    total = len(drive_names)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [
            ex.submit(upload_one, local_path, drive_name)
            for local_path, drive_name in zip(local_paths, drive_names)
        ]
        for future in as_completed(futures):
            name = future.result()
            if name is not None:
                uploaded += 1
            if callback:
                callback(uploaded)
    logger.info(f"Uploaded {total} files to {drive_folder_id}")
    return uploaded


def upsert_notion(
    notion: Client,
    name: str,
    title: str,
    drive_name: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    embed_link: str,
) -> dict[str, Any]:
    def local_iso(ts: pd.Timestamp) -> str:
        return ts.tz_convert(LOCAL_TZ).to_pydatetime().isoformat(timespec="seconds")

    # https://developers.notion.com/reference/page-property-values
    props = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Title": {"select": {"name": title}},
        "Key": {"rich_text": [{"text": {"content": drive_name}}]},
        "Start": {
            "date": {
                "start": local_iso(start),
                "end": None,
            }
        },
        "End": {
            "date": {
                "start": local_iso(end),
                "end": None,
            }
        },
        "Drive Link": {"url": embed_link},
    }
    q: dict[str, Any] = notion.databases.query(  # type: ignore
        database_id=NOTION_DB_ID,
        filter={"property": "Key", "rich_text": {"equals": drive_name}},
        page_size=1,
    )
    if q["results"]:
        page_id = q["results"][0]["id"]
        # avoid updating page name to allow custom page title mid session
        props.pop("Name", None)
        page = notion.pages.update(page_id, properties=props)
    else:
        page = notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties=props,
        )

        notion.blocks.children.append(
            block_id=page["id"],  # type: ignore
            children=[
                {"object": "block", "type": "embed", "embed": {"url": embed_link}}
            ],
        )
    return page  # type: ignore


# --- upload per session, embed link in Notion ---
def upload_sessions(to_upload: pd.DataFrame, drive: GoogleDrive, notion: Client):
    notify(
        title=f"{APP_NAME}: Uploading",
        body=f"Syncing {len(to_upload)} session{'s' if len(to_upload)>1 else ''}",
        progress={
            "title": "",
            "status": "",
            "value": 0.0,
            "valueStringOverride": f"",
        },
    )
    files_count: int = to_upload["count"].sum()
    uploaded_files_count = 0
    for idx, s in to_upload.iterrows():  # s -> session
        game_title_folder = upsert_folder(s["title"], DRIVE_PARENT_ID, drive)
        session_folder_name = s["start"].tz_convert(LOCAL_TZ).strftime("%Y-%m-%d %H_%M")
        session_folder = upsert_folder(
            session_folder_name, game_title_folder["id"], drive
        )

        files_uploaded = upload_files_concurrent(
            drive,
            session_folder["id"],
            s["paths"],
            s["names"],
            lambda i: update_progress(
                {
                    "title": f"{idx+1}/{len(to_upload)}: {s['title']}",  # type: ignore
                    "status": f"Uploading: {session_folder_name}",
                    "value": (i + uploaded_files_count) / files_count,
                    "valueStringOverride": f"{i + uploaded_files_count}/{files_count} files",
                }
            ),
        )
        uploaded_files_count += files_uploaded

        embed_link = create_embed_link(session_folder)

        page = upsert_notion(
            notion,
            s["drive_name"],
            s["title"],
            s["drive_name"],
            s["start"],
            s["end"],
            embed_link,
        )

        notify(
            f"{APP_NAME}: View In Notion",
            f"Title: {s['title']}\nSession: {session_folder_name}",
            on_click=page["url"],
        )

    update_progress({"status": "Completed!"})


# --- main ---
if __name__ == "__main__":
    start = time.time()
    try:
        if not SCREENSHOT_DIR.exists():
            raise FileNotFoundError(SCREENSHOT_DIR)

        gauth = GoogleAuth()
        gauth.LocalWebserverAuth()
        drive = GoogleDrive(gauth)
        logger.info("Authenticated to Google Drive")

        notion = Client(auth=NOTION_TOKEN)
        logger.info("Initialized Notion client")

        last_start, last_end = get_last_gaming_session(notion)
        screenshots_df = get_screenshots_df(last_start, last_end)

        upload_sessions(screenshots_df, drive, notion)

        elapsed = time.time() - start
        logger.info(f"Finished in {elapsed:.1f} seconds")

        # event_handler = GameSessionSync()
        # observer = Observer()
        # observer.schedule(event_handler, str(SCREENSHOT_DIR.resolve()), recursive=False)
        # observer.start()
        # try:
        #     while True:
        #         time.sleep(1)
        # finally:
        #     observer.stop()
        #     observer.join()

    except EarlyExit:
        logger.info("Encountered early exit, check previous logs")

    except KeyboardInterrupt as e:
        logger.warning("Interrupted by user")

    except Exception as e:
        logger.exception("An unexpected error occurred:")
        notify(
            f"{APP_NAME}: Unexpected Error",
            "Click to open logs in VSCode",
            on_click=f"vscode://file/{(LOG_DIR/LOG_FILENAME).resolve()}",
        )
        raise e
