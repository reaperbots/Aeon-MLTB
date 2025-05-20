# Features

## QBittorrent

- External access to web UI for file removal or settings adjustment. Sync with database using the sync button in bot settings.
- Select files from a torrent before or during download using the mltb file selector (requires Base URL) (task option).
- Seed torrents to a specific ratio and duration (task option).
- Edit global options during runtime via bot settings (global option).

## Aria2c

- Select torrent files before or during download (requires Base URL) (task option).
- Seed torrents to a specific ratio and duration (task option).
- Netrc authentication support (global option).
- Direct link authentication (even with just a username or password) (task option).
- Edit global options during runtime via bot settings (global option).

## Sabnzbd

- External web interface access for file removal or settings adjustments. Sync with database using the sync button in bot settings.
- Remove files from jobs before or during download using the mltb file selector (requires Base URL) (task option).
- Edit global options during runtime via bot settings (global option).
- Manage Usenet servers (add/edit/remove).

## TG Upload/Download

- Split size settings (global, user, and task option).
- Custom thumbnails (user and task option).
- Leech filename prefix (user option).
- Set upload type: document or media (global, user, and task option).
- Upload to a specific chat (supergroup, channel, private, or topic) (global, user, and task option).
- Equal split size (global and user option).
- Media group support for split file parts (global and user option).
- Download restricted Telegram messages via public/private/supergroup links (task option).
- Choose transfer session (bot or user) for premium accounts (global, user, and task option).
- Hybrid upload using bot and user sessions based on file size (global, user, and task option).
- Upload with custom thumbnail layout (global, user, and task option).
- Topic support.

## Google Drive

- Download, upload, clone, delete, and count files/folders.
- Count files and folders in Drive.
- Search in folders or TeamDrives.
- Use `token.pickle` fallback when no Service Account is available.
- Random Service Account per task.
- Recursive search support with root or TeamDrive ID (task option).
- Prevent duplicates (global and user option).
- Custom upload destinations (global, user, and task option).
- Choose between `token.pickle` or Service Account with button support (global, user, and task option).
- Index link support for [Bhadoo's Index](https://gitlab.com/GoogleDriveIndex/Google-Drive-Index/-/blob/master/src/worker.js).

## Rclone

- Transfer (download/upload/clone server-side) with or without random Service Accounts (global and user option).
- Choose config, remote, and path with or without button support (global, user, and task option).
- Set custom flags per task or globally (global, user, and task option).
- File/folder selection via buttons (task option).
- Use `rclone.conf` (global and user option).
- Serve combined remotes as an index (global option).
- Custom upload destinations (global, user, and task option).

## Status

- View download, upload, extract, archive, seed, and clone statuses.
- Unlimited task status pages (global option).
- Interval-based status updates (global option).
- Navigate with next/previous buttons (global and user option).
- Filter task view by status and type if more than 30 (global and user option).
- Step controls for pagination (global and user option).
- User-specific status (manual refresh only).

## Yt-dlp

- Quality selection buttons (task option).
- Custom `yt-dlp` options (global, user, and task option).
- Netrc support (global option).
- Cookie support (global option).
- Embed original thumbnail in leech.
- Supports all audio formats.

## JDownloader

- Sync settings (global option).
- Wait for file selection/variant changes before download starts.
- DLC file support.
- Edit settings via JDownloader web interface, Android/iOS apps, or browser extensions.

## Mongo Database

- Stores bot and user settings, including thumbnails and private files.
- Stores RSS data and incomplete task messages.
- Stores JDownloader settings.
- Automatically stores and updates `config.py`, using it for variable definitions.

## Torrents Search

- Search torrents via Torrent Search API.
- Use qBittorrent's plugin system for enhanced search.

## Archives

- Extract split archives with/without passwords.
- Zip files/folders with or without passwords and support for splits (leech).
- Uses 7z for extraction (supports all types).

## RSS

- Based on [rss-chan](https://github.com/hyPnOtICDo0g/rss-chan).
- RSS feeds (user option).
- Title filters (feed option).
- Edit feeds live: pause, resume, command and filter edits (feed option).
- Sudo controls for user feeds.
- Fully button-based command execution.

## Overall

- Docker support for `amd64`, `arm64/v8`, `arm/v7`.
- Runtime variable editing and private file overwrite (bot/user).
- Auto-update on startup and restart via `UPSTREAM_REPO`.
- Telegraph integration ([loaderX-bot](https://github.com/SVR666)).
- Reply-based Mirror/Leech/Watch/Clone/Count/Delete.
- Multi-link/file support for mirror/leech/clone in one command.
- Custom names for all links (excluding torrents); extensions required except for yt-dlp (global and user option).
- Exclude file extensions from upload/clone (global and user option).
- View Link button for browser access (instead of direct download).
- Queueing system for all tasks (global option).
- Zip/unzip multiple links into one directory (task option).
- Bulk download from Telegram TXT file or newline-separated links (task option).
- Join previously split files (task option).
- Sample video and screenshot generators (task option).
- Cancel upload/clone/archive/extract/split/queue (task option).
- Cancel specific task statuses using buttons (global option).
- Convert videos/audios to specific format with filter (task option).
- Force-start queue tasks with command/args (task option).
- Shell and executor support.
- Add sudo users.
- Save upload paths.
- Rename files before upload via name substitution.
- Select use of `rclone.conf` or `token.pickle` without `mpt:` or `mrcc:` prefix.
- Execute FFmpeg commands post-download (task option).
- Change Metadata automatically.
- Add watermark text automatically.
- Custom caption format.