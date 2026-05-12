from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import dropbox
from dropbox.files import FileMetadata


@dataclass
class DropboxCSVFile:
    name: str
    path_lower: str
    server_modified: str
    size: int
    content_hash: str
    local_path: Path


def get_dropbox_client(
    access_token: str | None = None,
    app_key: str | None = None,
    app_secret: str | None = None,
    refresh_token: str | None = None,
) -> dropbox.Dropbox:
    """Create a Dropbox client.

    Preferred production setup uses app_key + app_secret + refresh_token.
    A plain access_token is still supported for quick local testing, but Dropbox
    access tokens are usually short-lived and can expire.
    """
    access_token = (access_token or "").strip()
    app_key = (app_key or "").strip()
    app_secret = (app_secret or "").strip()
    refresh_token = (refresh_token or "").strip()

    if refresh_token:
        if not app_key or not app_secret:
            raise ValueError("Dropbox refresh token requires DROPBOX_APP_KEY and DROPBOX_APP_SECRET.")
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
            timeout=60,
        )

    if access_token:
        return dropbox.Dropbox(access_token, timeout=60)

    raise ValueError(
        "Missing Dropbox credentials. Use DROPBOX_APP_KEY, DROPBOX_APP_SECRET, and DROPBOX_REFRESH_TOKEN in Streamlit secrets."
    )


def list_csv_files(dbx: dropbox.Dropbox, folder_path: str) -> list[FileMetadata]:
    folder_path = (folder_path or "").strip() or ""
    entries: list[FileMetadata] = []
    result = dbx.files_list_folder(folder_path, recursive=False)
    while True:
        for entry in result.entries:
            if isinstance(entry, FileMetadata) and entry.name.lower().endswith(".csv"):
                entries.append(entry)
        if not result.has_more:
            break
        result = dbx.files_list_folder_continue(result.cursor)
    entries.sort(key=lambda e: (e.server_modified, e.path_lower or e.name))
    return entries


def download_file(dbx: dropbox.Dropbox, metadata: FileMetadata, download_dir: Path) -> DropboxCSVFile:
    download_dir.mkdir(parents=True, exist_ok=True)
    safe_name = metadata.name.replace("/", "_").replace("\\", "_")
    local_path = download_dir / safe_name
    _, response = dbx.files_download(metadata.path_lower)
    local_path.write_bytes(response.content)
    return DropboxCSVFile(
        name=metadata.name,
        path_lower=metadata.path_lower or metadata.name,
        server_modified=metadata.server_modified.isoformat() if metadata.server_modified else "",
        size=int(metadata.size or 0),
        content_hash=metadata.content_hash or hashlib.sha256(response.content).hexdigest(),
        local_path=local_path,
    )


def download_new_csvs(
    folder_path: str,
    download_dir: Path,
    access_token: str | None = None,
    app_key: str | None = None,
    app_secret: str | None = None,
    refresh_token: str | None = None,
) -> list[DropboxCSVFile]:
    dbx = get_dropbox_client(
        access_token=access_token,
        app_key=app_key,
        app_secret=app_secret,
        refresh_token=refresh_token,
    )
    files = list_csv_files(dbx, folder_path)
    return [download_file(dbx, f, download_dir) for f in files]
