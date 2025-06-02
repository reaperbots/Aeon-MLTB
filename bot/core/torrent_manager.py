import contextlib
from asyncio import gather
from inspect import iscoroutinefunction
from pathlib import Path

from aioaria2 import Aria2WebsocketClient
from aiohttp import ClientError
from aioqbt.client import create_client
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot import LOGGER, aria2_options


def wrap_with_retry(obj, max_retries=3):
    """Wraps all awaitable methods of an object with a tenacity retry policy.

    Args:
        obj: The object whose methods to wrap.
        max_retries: The maximum number of retry attempts.

    Returns:
        The object with its awaitable methods wrapped.
    """
    for attr_name in dir(obj):
        if attr_name.startswith("_"):
            continue

        attr = getattr(obj, attr_name)
        if iscoroutinefunction(attr):
            retry_policy = retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=5),
                retry=retry_if_exception_type(
                    (ClientError, TimeoutError, RuntimeError),
                ),
            )
            wrapped = retry_policy(attr)
            setattr(obj, attr_name, wrapped)
    return obj


class TorrentManager:
    """Manages Aria2c and qBittorrent client instances and provides
    common torrent operations.
    """

    aria2 = None
    qbittorrent = None

    @classmethod
    async def initiate(cls):
        """Initializes and wraps Aria2c and qBittorrent client instances."""
        cls.aria2 = await Aria2WebsocketClient.new("http://localhost:6800/jsonrpc")
        cls.qbittorrent = await create_client("http://localhost:8090/api/v2/")
        cls.qbittorrent = wrap_with_retry(cls.qbittorrent)

    @classmethod
    async def close_all(cls):
        """Closes connections to both Aria2c and qBittorrent clients."""
        await gather(cls.aria2.close(), cls.qbittorrent.close())

    @classmethod
    async def aria2_remove(cls, download):
        """Removes a download from Aria2c.

        Forces removal if the download is active, paused, or waiting.
        Otherwise, removes the download result.

        Args:
            download: A dictionary containing download information from Aria2c.
        """
        if download.get("status", "") in ["active", "paused", "waiting"]:
            await cls.aria2.forceRemove(download.get("gid", ""))
        else:
            with contextlib.suppress(Exception):
                await cls.aria2.removeDownloadResult(download.get("gid", ""))

    @classmethod
    async def remove_all(cls):
        """Pauses all downloads and then removes them from both Aria2c and qBittorrent."""
        await cls.pause_all()
        await gather(
            cls.qbittorrent.torrents.delete("all", False),
            cls.aria2.purgeDownloadResult(),
        )
        downloads = []
        results = await gather(
            cls.aria2.tellActive(),
            cls.aria2.tellWaiting(0, 1000),
        )
        for res in results:
            downloads.extend(res)
        tasks = []
        tasks.extend(
            cls.aria2.forceRemove(download.get("gid")) for download in downloads
        )
        with contextlib.suppress(Exception):
            await gather(*tasks)

    @classmethod
    async def overall_speed(cls):
        """Calculates the overall download and upload speed from both clients.

        Returns:
            A tuple containing (download_speed, upload_speed) in bytes/sec.
        """
        s1, s2 = await gather(
            cls.qbittorrent.transfer.info(),
            cls.aria2.getGlobalStat(),
        )
        download_speed = s1.dl_info_speed + int(s2.get("downloadSpeed", "0"))
        upload_speed = s1.up_info_speed + int(s2.get("uploadSpeed", "0"))
        return download_speed, upload_speed

    @classmethod
    async def pause_all(cls):
        """Pauses all downloads in both Aria2c and qBittorrent."""
        await gather(cls.aria2.forcePauseAll(), cls.qbittorrent.torrents.stop("all"))

    @classmethod
    async def change_aria2_option(cls, key, value):
        """Changes a specific option for all active/waiting Aria2c downloads
        and globally if applicable.

        Args:
            key: The Aria2c option key to change.
            value: The new value for the option.
        """
        downloads = []
        results = await gather(
            cls.aria2.tellActive(),
            cls.aria2.tellWaiting(0, 1000),
        )
        for res in results:
            downloads.extend(res)

        tasks = [
            cls.aria2.changeOption(download.get("gid"), {key: value})
            for download in downloads
            if download.get("status", "") != "complete"
        ]

        if tasks:
            try:
                await gather(*tasks)
            except Exception as e:
                LOGGER.error(e)

        if key not in ["checksum", "index-out", "out", "pause", "select-file"]:
            await cls.aria2.changeGlobalOption({key: value})
            aria2_options[key] = value


def aria2_name(download_info):
    """Extracts a display name for an Aria2c download.

    Prefers the BitTorrent info name if available, otherwise tries to
    derive a name from the file paths.

    Args:
        download_info: A dictionary containing Aria2c download information.

    Returns:
        A string representing the display name of the download, or an empty string.
    """
    if "bittorrent" in download_info and download_info["bittorrent"].get("info"):
        return download_info["bittorrent"]["info"]["name"]
    if download_info.get("files"):
        if download_info["files"][0]["path"].startswith("[METADATA]"):
            return download_info["files"][0]["path"]
        file_path = download_info["files"][0]["path"]
        dir_path = download_info["dir"]
        if file_path.startswith(dir_path):
            return Path(file_path[len(dir_path) + 1 :]).parts[0]
        return ""
    return ""


def is_metadata(download_info):
    """Checks if an Aria2c download is a metadata-only download.

    Args:
        download_info: A dictionary containing Aria2c download information.

    Returns:
        True if the download is metadata-only, False otherwise.
    """
    return any(
        f["path"].startswith("[METADATA]") for f in download_info.get("files", [])
    )
