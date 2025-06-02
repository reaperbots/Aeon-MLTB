import asyncio
import os
import shutil
import tempfile
import time

from bot.helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_message,
)

SUPPORTED_EXTS = {
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".aiff",
    ".aif",
    ".aifc",
    ".au",
    ".snd",
    ".raw",
    ".gsm",
}


def is_supported(filename: str) -> bool:
    return os.path.splitext(filename or "")[-1].lower() in SUPPORTED_EXTS


async def spectrum_handler(_, message):
    replied = message.reply_to_message
    media = replied.document or replied.audio

    if not media:
        await send_message(
            message, "Reply to an audio or document message with /sox."
        )
        return

    if not is_supported(media.file_name):
        await send_message(
            message, "Unsupported file format for Sox. Try, WAV, MP3, FLAC, etc."
        )
        return

    temp_dir = tempfile.mkdtemp(prefix="sox_")
    file_path = os.path.join(temp_dir, media.file_name or "input")
    output_path = os.path.join(temp_dir, "spectrum.png")

    progress_message = await send_message(message, "Downloading... 0%")
    last_update = 0

    async def progress(current, total):
        nonlocal last_update
        now = time.time()
        if now - last_update > 2:
            percent = current * 100 / total
            downloaded_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            await edit_message(
                progress_message,
                f"Downloading... {downloaded_mb:.2f}MB / {total_mb:.2f}MB {percent:.1f}%",
            )
            last_update = now

    try:
        await replied.download(file_path, progress=progress)
        await edit_message(progress_message, "Generating spectrum...")

        process = await asyncio.create_subprocess_exec(
            "sox",
            file_path,
            "-n",
            "spectrogram",
            "-o",
            output_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return_code = await process.wait()

        if return_code != 0:
            await edit_message(
                progress_message,
                "Failed to generate spectrum. The file may be corrupted or unsupported.",
            )
            return

        await message.reply_photo(output_path)
        await delete_message(progress_message)

    except Exception as e:
        await edit_message(progress_message, f"Unexpected error: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
