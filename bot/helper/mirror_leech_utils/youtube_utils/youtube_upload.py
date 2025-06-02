import os
from logging import getLogger

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.helper.ext_utils.bot_utils import SetInterval, async_to_sync
from bot.helper.ext_utils.files_utils import get_mime_type
from bot.helper.mirror_leech_utils.youtube_utils.youtube_helper import YouTubeHelper

LOGGER = getLogger(__name__)


class YouTubeUpload(YouTubeHelper):
    def __init__(self, listener, path):
        self.listener = listener
        self._updater = None
        self._path = path
        self._is_errored = False
        super().__init__()
        self.is_uploading = True

    def _upload_playlist(self, folder_path, playlist_name):
        """Uploads all videos in a folder and adds them to a new playlist."""
        video_ids = []
        video_files_count = 0
        LOGGER.info(f"Starting playlist upload for folder: {folder_path}")

        try:
            for item_name in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item_name)
                if os.path.isfile(item_path):
                    mime_type = get_mime_type(item_path)
                    if mime_type and mime_type.startswith("video/"):
                        video_files_count += 1
                        LOGGER.info(f"Uploading video file: {item_path}")
                        try:
                            video_id_or_url = self._upload_video(
                                item_path, item_name, mime_type
                            )
                            if (
                                video_id_or_url
                                and "youtube.com/watch?v=" in video_id_or_url
                            ):
                                video_id = video_id_or_url.split("=")[-1]
                                video_ids.append(video_id)
                                LOGGER.info(
                                    f"Successfully uploaded video: {item_name}, ID: {video_id}"
                                )
                            elif self.listener.is_cancelled:
                                LOGGER.info(
                                    "Playlist upload cancelled during video upload."
                                )
                                return None  # Or handle as partial success
                            else:
                                LOGGER.warning(
                                    f"Failed to upload video or extract ID: {item_name}"
                                )
                        except Exception as e:
                            LOGGER.error(f"Error uploading video {item_name}: {e}")
                            # Optionally, decide if one video failure should stop the whole playlist
                            # For now, we continue and try to upload other videos
                    else:
                        LOGGER.debug(
                            f"Skipping non-video file: {item_path} (MIME: {mime_type})"
                        )
                if self.listener.is_cancelled:
                    LOGGER.info("Playlist upload process cancelled.")
                    return None  # Or handle cleanup for partially uploaded videos

            if not video_ids:
                LOGGER.info("No videos found or uploaded in the folder.")
                if video_files_count > 0:  # Videos were found but failed to upload
                    raise ValueError(
                        "No videos were successfully uploaded from the folder."
                    )
                return "No videos to upload in playlist."  # Or specific message

            LOGGER.info(f"Creating playlist: {playlist_name}")
            playlist_request_body = {
                "snippet": {
                    "title": playlist_name,
                    "description": f"Playlist created from folder: {playlist_name}",
                    "tags": ["mirror-leech-bot", "playlist-upload"],
                },
                "status": {"privacyStatus": "private"},  # Or user-defined
            }
            playlist_insert_request = self.service.playlists().insert(
                part="snippet,status", body=playlist_request_body
            )
            playlist_response = playlist_insert_request.execute()
            playlist_id = playlist_response["id"]
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            LOGGER.info(
                f"Playlist created: {playlist_name}, ID: {playlist_id}, URL: {playlist_url}"
            )

            for video_id in video_ids:
                if self.listener.is_cancelled:
                    LOGGER.info(
                        "Playlist upload cancelled before adding all videos to playlist."
                    )
                    break  # Stop adding more videos
                LOGGER.info(f"Adding video ID {video_id} to playlist {playlist_id}")
                playlist_item_request_body = {
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                }
                playlist_item_insert_request = self.service.playlistItems().insert(
                    part="snippet", body=playlist_item_request_body
                )
                playlist_item_insert_request.execute()
                LOGGER.info(
                    f"Successfully added video ID {video_id} to playlist {playlist_id}"
                )

            # Update total_files for the listener, this might need adjustment based on how listener expects it
            self.total_files = len(
                video_ids
            )  # Count of successfully uploaded and added videos
            return playlist_url

        except HttpError as e:
            LOGGER.error(f"YouTube API error during playlist operation: {e}")
            raise e  # Re-raise to be caught by the main upload method's error handler
        except Exception as e:
            LOGGER.error(f"Error during playlist creation or video addition: {e}")
            raise e  # Re-raise

    def user_setting(self):
        """Handle user-specific YouTube token settings"""
        if self.listener.up_dest.startswith("yt:"):
            self.token_path = f"tokens/{self.listener.user_id}.pickle"
            self.listener.up_dest = self.listener.up_dest.replace("yt:", "", 1)
        elif hasattr(self.listener, "user_id") and self.listener.user_id:
            self.token_path = f"tokens/{self.listener.user_id}.pickle"

    def upload(self):
        """Main upload function"""
        self.user_setting()
        try:
            self.service = self.authorize(
                self.listener.user_id if hasattr(self.listener, "user_id") else ""
            )
        except Exception as e:
            LOGGER.error(f"YouTube authorization failed: {e}")
            async_to_sync(
                self.listener.on_upload_error, f"YouTube authorization failed: {e!s}"
            )
            return

        LOGGER.info(f"Uploading to YouTube: {self._path}")
        self._updater = SetInterval(self.update_interval, self.progress)
        upload_result_url = None
        upload_type = None
        files_processed = 0

        try:
            if os.path.isfile(self._path):
                mime_type = get_mime_type(self._path)
                if not mime_type or not mime_type.startswith("video/"):
                    raise ValueError(f"File is not a video. MIME type: {mime_type}")

                upload_result_url = self._upload_video(
                    self._path, self.listener.name, mime_type
                )
                upload_type = "Video"
                if upload_result_url:
                    files_processed = 1
                LOGGER.info(f"Uploaded Single Video To YouTube: {self._path}")

            elif os.path.isdir(self._path):
                playlist_name = os.path.basename(self._path)
                upload_result_url = self._upload_playlist(self._path, playlist_name)
                upload_type = "Playlist"
                # self.total_files is updated within _upload_playlist
                files_processed = self.total_files
                LOGGER.info(f"Uploaded Playlist To YouTube: {self._path}")
            else:
                raise ValueError(f"Path is not a file or directory: {self._path}")

            if self.listener.is_cancelled:
                LOGGER.info("Upload cancelled by listener.")
                return

            if upload_result_url is None and not self.listener.is_cancelled:
                # Check if it was due to no videos in folder for playlist
                if upload_type == "Playlist" and self.total_files == 0:
                    LOGGER.info("Playlist upload resulted in no videos uploaded.")
                    # Keep upload_result_url as None or specific message from _upload_playlist
                else:
                    raise ValueError(
                        "Upload result is None but not cancelled by listener and not an empty playlist."
                    )

        except Exception as err:
            if isinstance(err, RetryError):
                LOGGER.info(f"Total Attempts: {err.last_attempt.attempt_number}")
                err = err.last_attempt.exception()
            err = str(err).replace(">", "").replace("<", "")
            LOGGER.error(err)
            async_to_sync(self.listener.on_upload_error, err)
            self._is_errored = True
        finally:
            self._updater.cancel()

        if self.listener.is_cancelled and not self._is_errored:
            LOGGER.info("Upload process was cancelled by listener.")
            return

        if self._is_errored:
            LOGGER.error("Upload process failed with an error.")
            return

        if (
            upload_result_url is None
            and upload_type == "Playlist"
            and files_processed == 0
        ):
            # Handle case where playlist was "successful" but no videos were uploaded (e.g. empty folder)
            # The error or specific message should ideally come from _upload_playlist
            async_to_sync(
                self.listener.on_upload_error,
                "No videos found in the folder to upload to playlist.",
            )
            return

        async_to_sync(
            self.listener.on_upload_complete,
            upload_result_url,
            files_processed,  # total_files (videos in playlist or 1 for single video)
            1 if upload_type == "Playlist" else 0,  # total_folders
            upload_type,  # mime_type ("Playlist" or "Video")
        )
        return

    @retry(
        wait=wait_exponential(multiplier=2, min=3, max=6),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
    )
    def _upload_video(self, file_path, file_name, mime_type):
        """Upload video to YouTube"""

        # Default video metadata
        title = file_name
        description = f"Uploaded by Mirror-leech-telegram-bot\n\nOriginal filename: {file_name}"
        tags = ["mirror-leech-bot", "telegram-bot", "upload"]
        category_id = "22"  # People & Blogs
        privacy_status = "private"  # unlisted, private, public

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        # Create media upload object
        media_body = MediaFileUpload(
            file_path,
            mimetype=mime_type,
            resumable=True,
            chunksize=1024 * 1024 * 4,  # 4MB chunks
        )

        # Create the upload request
        insert_request = self.service.videos().insert(
            part=",".join(body.keys()), body=body, media_body=media_body
        )

        response = None
        retries = 0

        while response is None and not self.listener.is_cancelled:
            try:
                self.status, response = insert_request.next_chunk()
                if self.status:
                    self.upload_progress = int(self.status.progress() * 100)
                    LOGGER.info(f"Upload progress: {self.upload_progress}%")

            except HttpError as err:
                if err.resp.status in [500, 502, 503, 504, 429] and retries < 5:
                    retries += 1
                    LOGGER.warning(
                        f"HTTP error {err.resp.status}, retrying... ({retries}/5)"
                    )
                    continue
                error_content = (
                    err.content.decode("utf-8") if err.content else "Unknown error"
                )
                LOGGER.error(f"YouTube upload failed: {error_content}")
                raise err
            except Exception as e:
                LOGGER.error(f"Unexpected error during upload: {e}")
                raise e

        if self.listener.is_cancelled:
            return None

        # Clean up the file after successful upload (only if it's a single file upload path)
        # For playlists, videos are removed individually in _upload_video after each successful upload.
        # However, _upload_video is also used by _upload_playlist.
        # We need to ensure that remove(file_path) in _upload_video doesn't cause issues
        # when called from _upload_playlist where file_path is part of a larger folder operation.
        # The current implementation of _upload_video removes the file it uploads. This is fine.

        # self.file_processed_bytes and self.total_files are updated differently now.
        # For single video: self.total_files +=1 (as before, implicitly by on_upload_complete call)
        # For playlist: self.total_files is set in _upload_playlist

        # Reset file_processed_bytes for the next potential file if this method is called again in some context
        # Though typically one YouTubeUpload instance handles one upload operation (file or folder).
        # self.file_processed_bytes = 0 # This might be better handled at start of _upload_video

        if response:
            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            LOGGER.info(f"Video uploaded successfully: {video_url}")

            # If _upload_video is called from _upload_playlist, it returns the URL.
            # The video_id is then extracted in _upload_playlist.
            # If called directly from 'upload' for a single file, it also returns the URL.
            # The `remove(file_path)` is inside _upload_video, so it will be called for each video.

            # For single video uploads, self.total_files should be incremented.
            # For playlist uploads, _upload_playlist will manage the count of successfully uploaded videos.
            # Let's adjust self.total_files incrementing logic.
            # It's currently incremented in _upload_video. This means if _upload_video is called N times for a playlist,
            # self.total_files will be N. This is correct for the listener's perspective if files_processed is this value.
            # The line `self.total_files += 1` in _upload_video is fine.
            # `self.file_processed_bytes = 0` is also fine there.

            return video_url

        # If listener cancelled during next_chunk loop, response will be None.
        if self.listener.is_cancelled:
            LOGGER.info("Video upload cancelled during chunk upload.")
            return None  # Propagate cancellation

        raise ValueError(
            "Upload completed (or cancelled) but no response received and not handled by cancellation"
        )

    def get_upload_status(self):
        return {
            "progress": self.upload_progress,
            "speed": self.speed,
            "processed_bytes": self.processed_bytes,
            "total_files": self.total_files,
            "is_uploading": self.is_uploading,
        }
