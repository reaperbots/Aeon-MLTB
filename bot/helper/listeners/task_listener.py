# ruff: noqa: RUF006
from asyncio import create_task, gather, sleep
from html import escape

from aiofiles.os import listdir, makedirs, remove
from aiofiles.os import path as aiopath
from aioshutil import move
from requests import utils as rutils

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    intervals,
    non_queued_dl,
    non_queued_up,
    queue_dict_lock,
    queued_dl,
    queued_up,
    same_directory_lock,
    task_dict,
    task_dict_lock,
)
from bot.core.config_manager import Config
from bot.core.torrent_manager import TorrentManager
from bot.helper.common import TaskConfig
from bot.helper.ext_utils.bot_utils import sync_to_async
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.files_utils import (
    clean_download,
    clean_target,
    create_recursive_symlink,
    get_path_size,
    join_files,
    remove_excluded_files,
)
from bot.helper.ext_utils.links_utils import is_gdrive_id
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.ext_utils.task_manager import check_running_tasks, start_from_queued
from bot.helper.mirror_leech_utils.gdrive_utils.upload import GoogleDriveUpload
from bot.helper.mirror_leech_utils.rclone_utils.transfer import RcloneTransferHelper
from bot.helper.mirror_leech_utils.status_utils.gdrive_status import (
    GoogleDriveStatus,
)
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_leech_utils.status_utils.rclone_status import RcloneStatus
from bot.helper.mirror_leech_utils.status_utils.telegram_status import TelegramStatus
from bot.helper.mirror_leech_utils.status_utils.yt_status import YtStatus
from bot.helper.mirror_leech_utils.telegram_uploader import TelegramUploader
from bot.helper.mirror_leech_utils.youtube_utils.youtube_upload import YouTubeUpload
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    delete_status,
    send_message,
    update_status_message,
)


class TaskListener(TaskConfig):
    def __init__(self):
        super().__init__()

    async def clean(self):
        try:
            if st := intervals["status"]:
                for intvl in list(st.values()):
                    intvl.cancel()
            intervals["status"].clear()
            await gather(TorrentManager.aria2.purgeDownloadResult(), delete_status())
        except Exception as e:
            LOGGER.error(e)

    def clear(self):
        self.subname = ""
        self.subsize = 0
        self.files_to_proceed = []
        self.proceed_count = 0
        self.progress = True

    async def remove_from_same_dir(self):
        async with task_dict_lock:
            if (
                self.folder_name
                and self.same_dir
                and self.mid in self.same_dir[self.folder_name]["tasks"]
            ):
                self.same_dir[self.folder_name]["tasks"].remove(self.mid)
                self.same_dir[self.folder_name]["total"] -= 1

    async def on_download_start(self):
        if (
            self.is_super_chat
            and Config.INCOMPLETE_TASK_NOTIFIER
            and Config.DATABASE_URL
        ):
            await database.add_incomplete_task(
                self.message.chat.id,
                self.message.link,
                self.tag,
            )

    async def on_download_complete(self):
        await sleep(2)
        if self.is_cancelled:
            return
        multi_links = False
        if (
            self.folder_name
            and self.same_dir
            and self.mid in self.same_dir[self.folder_name]["tasks"]
        ):
            async with same_directory_lock:
                while True:
                    async with task_dict_lock:
                        if self.mid not in self.same_dir[self.folder_name]["tasks"]:
                            return
                        if self.mid in self.same_dir[self.folder_name]["tasks"] and (
                            self.same_dir[self.folder_name]["total"] <= 1
                            or len(self.same_dir[self.folder_name]["tasks"]) > 1
                        ):
                            if self.same_dir[self.folder_name]["total"] > 1:
                                self.same_dir[self.folder_name]["tasks"].remove(
                                    self.mid,
                                )
                                self.same_dir[self.folder_name]["total"] -= 1
                                spath = f"{self.dir}{self.folder_name}"
                                des_id = next(
                                    iter(self.same_dir[self.folder_name]["tasks"]),
                                )
                                des_path = (
                                    f"{DOWNLOAD_DIR}{des_id}{self.folder_name}"
                                )
                                await makedirs(des_path, exist_ok=True)
                                LOGGER.info(
                                    f"Moving files from {self.mid} to {des_id}",
                                )
                                for item in await listdir(spath):
                                    if item.strip().endswith((".aria2", ".!qB")):
                                        continue
                                    item_path = (
                                        f"{self.dir}{self.folder_name}/{item}"
                                    )
                                    if item in await listdir(des_path):
                                        await move(
                                            item_path,
                                            f"{des_path}/{self.mid}-{item}",
                                        )
                                    else:
                                        await move(item_path, f"{des_path}/{item}")
                                multi_links = True
                            break
                    await sleep(1)
        async with task_dict_lock:
            if self.is_cancelled:
                return
            if self.mid in task_dict:
                download = task_dict[self.mid]
                self.name = download.name()
                gid = download.gid()
            else:
                return
        LOGGER.info(f"Download completed: {self.name}")

        if not (self.is_torrent or self.is_qbit):
            self.seed = False

        if multi_links:
            self.seed = False
            await self.on_upload_error(
                f"{self.name} Downloaded!\n\nWaiting for other tasks to finish...",
            )
            return

        if self.folder_name:
            self.name = self.folder_name.strip("/").split("/", 1)[0]

        if not await aiopath.exists(f"{self.dir}/{self.name}"):
            try:
                files = await listdir(self.dir)
                self.name = files[-1]
                if self.name == "yt-dlp-thumb":
                    self.name = files[0]
            except Exception as e:
                await self.on_upload_error(str(e))
                return

        dl_path = f"{self.dir}/{self.name}"
        self.size = await get_path_size(dl_path)
        self.is_file = await aiopath.isfile(dl_path)
        if self.seed:
            up_dir = self.up_dir = f"{self.dir}10000"
            up_path = f"{self.up_dir}/{self.name}"
            await create_recursive_symlink(self.dir, self.up_dir)
            LOGGER.info(f"Shortcut created: {dl_path} -> {up_path}")
        else:
            up_dir = self.dir
            up_path = dl_path
        await remove_excluded_files(
            self.up_dir or self.dir,
            self.excluded_extensions,
        )
        if not Config.QUEUE_ALL:
            async with queue_dict_lock:
                if self.mid in non_queued_dl:
                    non_queued_dl.remove(self.mid)
            await start_from_queued()

        if self.join and not self.is_file:
            await join_files(up_path)

        if self.extract and not self.is_nzb:
            up_path = await self.proceed_extract(up_path, gid)
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
            self.size = await get_path_size(up_dir)
            self.clear()
            await remove_excluded_files(up_dir, self.excluded_extensions)

        if self.watermark:
            up_path = await self.proceed_watermark(
                up_path,
                gid,
            )
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
            self.size = await get_path_size(up_dir)
            self.clear()

        if self.metadata:
            up_path = await self.proceed_metadata(
                up_path,
                gid,
            )
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
            self.size = await get_path_size(up_dir)
            self.clear()

        if self.ffmpeg_cmds:
            up_path = await self.proceed_ffmpeg(
                up_path,
                gid,
            )
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
            self.size = await get_path_size(up_dir)
            self.clear()

        if self.name_sub:
            up_path = await self.substitute(up_path)
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]

        up_path = await self.remove_www_prefix(up_path)
        self.is_file = await aiopath.isfile(up_path)
        self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]

        if self.screen_shots:
            up_path = await self.generate_screenshots(up_path)
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
            self.size = await get_path_size(up_dir)

        if self.convert_audio or self.convert_video:
            up_path = await self.convert_media(
                up_path,
                gid,
            )
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
            self.size = await get_path_size(up_dir)
            self.clear()

        if self.sample_video:
            up_path = await self.generate_sample_video(
                up_path,
                gid,
            )
            if self.is_cancelled:
                return
            self.is_file = await aiopath.isfile(up_path)
            self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
            self.size = await get_path_size(up_dir)
            self.clear()

        if self.compress:
            up_path = await self.proceed_compress(
                up_path,
                gid,
            )
            self.is_file = await aiopath.isfile(up_path)
            if self.is_cancelled:
                return
            self.clear()

        self.name = up_path.replace(f"{up_dir}/", "").split("/", 1)[0]
        self.size = await get_path_size(up_dir)

        if self.is_leech and not self.compress:
            await self.proceed_split(
                up_path,
                gid,
            )
            if self.is_cancelled:
                return
            self.clear()

        self.subproc = None

        add_to_queue, event = await check_running_tasks(self, "up")
        await start_from_queued()
        if add_to_queue:
            LOGGER.info(f"Added to Queue/Upload: {self.name}")
            async with task_dict_lock:
                task_dict[self.mid] = QueueStatus(self, gid, "Up")
            await event.wait()
            if self.is_cancelled:
                return
            LOGGER.info(f"Start from Queued/Upload: {self.name}")

        self.size = await get_path_size(up_dir)

        upload_service = ""

        if self.raw_up_dest == "yt":
            upload_service = "yt"
        elif self.raw_up_dest == "gd":
            upload_service = "gd"
        elif self.raw_up_dest == "rc":
            upload_service = "rc"

        if not upload_service:
            upload_service = self.user_dict.get(
                "DEFAULT_UPLOAD", Config.DEFAULT_UPLOAD
            )

        if self.is_leech:
            LOGGER.info(f"Leeching: {self.name} (no specific uploader or is_leech)")
            tg = TelegramUploader(self, up_dir)
            async with task_dict_lock:
                task_dict[self.mid] = TelegramStatus(self, tg, gid, "up")
            await gather(
                update_status_message(self.message.chat.id),
                tg.upload(),
            )
            await delete_message(tg.log_msg)
            del tg
        elif upload_service == "yt":
            LOGGER.info(f"Uploading to YouTube: {self.name} (Service selected: yt)")
            yt = YouTubeUpload(self, up_path)
            async with task_dict_lock:
                task_dict[self.mid] = YtStatus(self, yt, gid)
            await gather(
                update_status_message(self.message.chat.id),
                sync_to_async(yt.upload),
            )
            del yt
        elif is_gdrive_id(self.up_dest):
            LOGGER.info(
                f"Uploading to Google Drive (path-detected): {self.name} (Destination ID: {self.up_dest})"
            )
            drive = GoogleDriveUpload(self, up_path)
            async with task_dict_lock:
                task_dict[self.mid] = GoogleDriveStatus(self, drive, gid, "up")
            await gather(
                update_status_message(self.message.chat.id),
                sync_to_async(drive.upload),
            )
            del drive
        else:
            LOGGER.info("Uploading to Rclone")
            RCTransfer = RcloneTransferHelper(self)
            async with task_dict_lock:
                task_dict[self.mid] = RcloneStatus(self, RCTransfer, gid, "up")
            await gather(
                update_status_message(self.message.chat.id),
                RCTransfer.upload(up_path),
            )
            del RCTransfer

    async def on_upload_complete(
        self,
        link,
        files,
        folders,
        mime_type,
        rclone_path="",
        dir_id="",
    ):
        if (
            self.is_super_chat
            and Config.INCOMPLETE_TASK_NOTIFIER
            and Config.DATABASE_URL
        ):
            await database.rm_complete_task(self.message.link)
        msg = f"<b>Name: </b><code>{escape(self.name)}</code>\n\n<b>Size: </b>{get_readable_file_size(self.size)}"
        done_msg = f"{self.tag}\nYour task is complete\nPlease check your inbox."
        LOGGER.info(f"Task Done: {self.name}")

        # Determine the upload service for message formatting
        upload_service = ""
        if self.raw_up_dest == "yt" or (
            self.raw_up_dest and self.raw_up_dest.startswith("yt:")
        ):
            upload_service = "yt"
        elif self.raw_up_dest == "gd":
            upload_service = "gd"
        elif self.raw_up_dest == "rc":
            upload_service = "rc"

        if not upload_service:  # If -up didn't specify a service directly
            upload_service = self.user_dict.get(
                "DEFAULT_UPLOAD", Config.DEFAULT_UPLOAD
            )

        if upload_service == "yt":
            msg += "\n<b>Type: </b>Video/Playlist"  # Updated to reflect it can be a playlist
            if link:
                msg += f"\n<b>Link: </b><a href='{link}'>Link</a>"  # Generic "Link" as it can be video or playlist
            msg += f"\n\n<b>cc: </b>{self.tag}"

            await send_message(self.user_id, msg)
            if Config.LOG_CHAT_ID:
                await send_message(int(Config.LOG_CHAT_ID), msg)
            await send_message(
                self.message,
                f"{self.tag}\nYour video has been uploaded to YouTube successfully!",
            )
        elif self.is_leech:
            msg += f"\n<b>Total Files: </b>{folders}"
            if mime_type != 0:
                msg += f"\n<b>Corrupted Files: </b>{mime_type}"
            msg += f"\n<b>cc: </b>{self.tag}\n\n"
            if not files:
                await send_message(self.message, msg)
            else:
                fmsg = ""
                for index, (url, name) in enumerate(files.items(), start=1):
                    fmsg += f"{index}. <a href='{url}'>{name}</a>\n"
                    if len(fmsg.encode() + msg.encode()) > 4000:
                        await send_message(
                            self.user_id,
                            f"{msg}<blockquote expandable>{fmsg}</blockquote>",
                        )
                        if Config.LOG_CHAT_ID:
                            await send_message(
                                int(Config.LOG_CHAT_ID),
                                f"{msg}<blockquote expandable>{fmsg}</blockquote>",
                            )
                        await sleep(1)
                        fmsg = ""
                if fmsg != "":
                    await send_message(
                        self.user_id,
                        f"{msg}<blockquote expandable>{fmsg}</blockquote>",
                    )
                    if Config.LOG_CHAT_ID:
                        await send_message(
                            int(Config.LOG_CHAT_ID),
                            f"{msg}<blockquote expandable>{fmsg}</blockquote>",
                        )
                await send_message(self.message, done_msg)
        else:
            msg += f"\n\n<b>Type: </b>{mime_type}"
            if mime_type == "Folder":
                msg += f"\n<b>SubFolders: </b>{folders}"
                msg += f"\n<b>Files: </b>{files}"
            if link or (
                rclone_path and Config.RCLONE_SERVE_URL and not self.private_link
            ):
                buttons = ButtonMaker()
                if link and Config.SHOW_CLOUD_LINK:
                    buttons.url_button("☁️ Cloud Link", link)
                else:
                    msg += f"\n\nPath: <code>{rclone_path}</code>"
                if rclone_path and Config.RCLONE_SERVE_URL and not self.private_link:
                    remote, rpath = rclone_path.split(":", 1)
                    url_path = rutils.quote(f"{rpath}")
                    share_url = f"{Config.RCLONE_SERVE_URL}/{remote}/{url_path}"
                    if mime_type == "Folder":
                        share_url += "/"
                    buttons.url_button("🔗 Rclone Link", share_url)
                if not rclone_path and dir_id:
                    INDEX_URL = ""
                    if self.private_link:
                        INDEX_URL = self.user_dict.get("INDEX_URL", "") or ""
                    elif Config.INDEX_URL:
                        INDEX_URL = Config.INDEX_URL
                    if INDEX_URL:
                        share_url = f"{INDEX_URL}findpath?id={dir_id}"
                        buttons.url_button("⚡ Index Link", share_url)
                        if mime_type.startswith(("image", "video", "audio")):
                            share_urls = f"{INDEX_URL}findpath?id={dir_id}&view=true"
                            buttons.url_button("🌐 View Link", share_urls)
                button = buttons.build_menu(2)
            else:
                msg += f"\n\nPath: <code>{rclone_path}</code>"
                button = None
            msg += f"\n\n<b>cc: </b>{self.tag}"
            await send_message(self.user_id, msg, button)
            if Config.LOG_CHAT_ID:
                await send_message(int(Config.LOG_CHAT_ID), msg, button)
            await send_message(self.message, done_msg)
        if self.seed:
            await clean_target(self.up_dir)
            async with queue_dict_lock:
                if self.mid in non_queued_up:
                    non_queued_up.remove(self.mid)
            await start_from_queued()
            return
        await clean_download(self.dir)
        async with task_dict_lock:
            if self.mid in task_dict:
                del task_dict[self.mid]
            count = len(task_dict)
        if count == 0:
            await self.clean()
        else:
            await update_status_message(self.message.chat.id)

        async with queue_dict_lock:
            if self.mid in non_queued_up:
                non_queued_up.remove(self.mid)

        await start_from_queued()

    async def on_download_error(self, error, button=None):
        async with task_dict_lock:
            if self.mid in task_dict:
                del task_dict[self.mid]
            count = len(task_dict)
        await self.remove_from_same_dir()
        msg = f"{self.tag} Download: {escape(str(error))}"
        x = await send_message(self.message, msg, button)
        create_task(auto_delete_message(x, time=300))
        if count == 0:
            await self.clean()
        else:
            await update_status_message(self.message.chat.id)

        if (
            self.is_super_chat
            and Config.INCOMPLETE_TASK_NOTIFIER
            and Config.DATABASE_URL
        ):
            await database.rm_complete_task(self.message.link)

        async with queue_dict_lock:
            if self.mid in queued_dl:
                queued_dl[self.mid].set()
                del queued_dl[self.mid]
            if self.mid in queued_up:
                queued_up[self.mid].set()
                del queued_up[self.mid]
            if self.mid in non_queued_dl:
                non_queued_dl.remove(self.mid)
            if self.mid in non_queued_up:
                non_queued_up.remove(self.mid)

        await start_from_queued()
        await sleep(3)
        await clean_download(self.dir)
        if self.up_dir:
            await clean_download(self.up_dir)
        if self.thumb and await aiopath.exists(self.thumb):
            await remove(self.thumb)

    async def on_upload_error(self, error):
        async with task_dict_lock:
            if self.mid in task_dict:
                del task_dict[self.mid]
            count = len(task_dict)
        x = await send_message(self.message, f"{self.tag} {escape(str(error))}")
        create_task(auto_delete_message(x, time=300))
        if count == 0:
            await self.clean()
        else:
            await update_status_message(self.message.chat.id)

        if (
            self.is_super_chat
            and Config.INCOMPLETE_TASK_NOTIFIER
            and Config.DATABASE_URL
        ):
            await database.rm_complete_task(self.message.link)

        async with queue_dict_lock:
            if self.mid in queued_dl:
                queued_dl[self.mid].set()
                del queued_dl[self.mid]
            if self.mid in queued_up:
                queued_up[self.mid].set()
                del queued_up[self.mid]
            if self.mid in non_queued_dl:
                non_queued_dl.remove(self.mid)
            if self.mid in non_queued_up:
                non_queued_up.remove(self.mid)

        await start_from_queued()
        await sleep(3)
        await clean_download(self.dir)
        if self.up_dir:
            await clean_download(self.up_dir)
        if self.thumb and await aiopath.exists(self.thumb):
            await remove(self.thumb)
