"""
TrackPull - Modern Music & Playlist Downloader for Windows.

Version: 1.0.1
Features:
- Dual-column responsive studio layout
- Full bilingual localization (Ukrainian & English) with dynamic switching
- Human-friendly, non-technical feature labels
- Hardware-accelerated multi-threaded yt-dlp engine with Deno & FFmpeg
- Zero tearing / glitch-free native Windows experience

Author: TrackPull Open Source Maintainers
License: MIT
"""

from __future__ import annotations

import os
import re
import sys
import shutil
import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any, List, Set
import urllib.parse

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
except ImportError as gui_import_error:
    sys.stderr.write(
        f"Critical error: Failed to import GUI libraries: {gui_import_error}\n"
        "Ensure CustomTkinter is installed via 'pip install customtkinter'.\n"
    )
    sys.exit(1)

try:
    import yt_dlp
except ImportError as engine_import_error:
    sys.stderr.write(
        f"Critical error: Failed to import yt-dlp: {engine_import_error}\n"
        "Ensure yt-dlp is installed via 'pip install yt-dlp'.\n"
    )
    sys.exit(1)


# ============================================================================
# LOCALIZATION (i18n) DICTIONARY: UKRAINIAN & ENGLISH
# ============================================================================

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "UA": {
        "app_title": "TrackPull",
        "app_subtitle": "Швидкий та зручний завантажувач музики",
        "theme_label": "Тема:",
        "lang_label": "Мова:",
        "theme_dark": "Темна",
        "theme_light": "Світла",
        "theme_system": "Системна",
        "ffmpeg_ready": "FFmpeg: Готовий",
        "ffmpeg_missing": "FFmpeg: Відсутній (клікніть)",
        "card_format": "Формат та якість звуку",
        "quality_title": "Якість звуку:",
        "quality_lossless": "Якість: Без втрат (Lossless)",
        "bitrate_320": "320 kbps (Найвища якість)",
        "bitrate_256": "256 kbps (Висока якість)",
        "bitrate_192": "192 kbps (Середня якість)",
        "bitrate_128": "128 kbps (Економія місця)",
        "card_options": "Додаткові зручності",
        "switch_playlist": "Завантажити весь плейлист",
        "switch_metadata": "Додати автора та назву пісні",
        "switch_thumbnail": "Зберегти обкладинку треку",
        "card_directory": "Куди зберігати музику",
        "btn_browse": "Обрати папку...",
        "btn_open_folder": "Відкрити папку",
        "url_title": "Посилання на пісню або плейлист:",
        "url_placeholder": "Вставте посилання з YouTube, SoundCloud тощо...",
        "btn_paste": "Вставити",
        "btn_clear": "✕",
        "btn_download": "ЗАВАНТАЖИТИ МУЗИКУ",
        "btn_downloading": "ЗАВАНТАЖЕННЯ...",
        "btn_resume": "ПРОДОВЖИТИ ЗАВАНТАЖЕННЯ",
        "btn_cancel": "Зупинити",
        "btn_stopping": "Зупинка...",
        "playlist_badge_idle": "Плейлист: Очікування",
        "playlist_badge_format": "Плейлист: {index} з {total} ({index}/{total})",
        "playlist_badge_single": "Одиночний трек",
        "playlist_completed_summary": "Плейлист: {completed} з {total} збережено!",
        "status_ready": "Статус: Готовий до роботи",
        "status_preparing": "Статус: Підготовка до завантаження...",
        "status_extracting": "Статус: Пошук та отримання треку...",
        "status_converting": "Статус: Перетворення звуку (FFmpeg)...",
        "status_embedding_thumb": "Статус: Додавання обкладинки...",
        "status_embedding_meta": "Статус: Запис назви та автора...",
        "status_completed": "Статус: Завершено успішно!",
        "status_cancelled": "Статус: Завантаження зупинено",
        "status_error": "Статус: Помилка завантаження",
        "status_playlist_error": "Помилка на пісні [{index}/{total}]. Натисніть «ПРОДОВЖИТИ», щоб завантажити далі!",
        "speed_label": "Швидкість: ",
        "eta_label": "Час: ",
        "card_terminal": "Хід завантаження (журнал):",
        "btn_clear_log": "Очистити",
        "log_started": "=== TrackPull v1.0.1 успішно запущено. ===",
        "log_ffmpeg_found": "FFmpeg готовий до конвертації аудіо.",
        "log_deno_active": "Прискорювач YouTube (Deno) активний.",
        "log_resuming_from": "Продовження завантаження плейлиста з пісні {index} з {total} ({index}/{total})...",
        "msg_empty_url_title": "Порожнє посилання",
        "msg_empty_url_body": "Будь ласка, вставте посилання на пісню або плейлист у поле вводу.",
        "msg_invalid_url_title": "Некоректне посилання",
        "msg_invalid_url_body": "Посилання має починатися з http:// або https://",
        "msg_success_title": "Успіх",
        "msg_success_body": "Музику успішно завантажено та збережено!",
        "msg_resume_title": "Помилка пісні в плейлисті",
        "msg_resume_body": (
            "Не вдалося завантажити пісню #{failed_index} з {total}.\n\n"
            "Натисніть зелену кнопку «ПРОДОВЖИТИ ЗАВАНТАЖЕННЯ», щоб пропустити проблемний файл та продовжити завантаження наступних пісень (з {next_index} з {total})!"
        ),
        "msg_folder_not_found_title": "Папка не знайдена",
        "msg_folder_not_found_body": "Вказана папка не існує на комп'ютері:\n",
        "msg_ffmpeg_missing_title": "FFmpeg не знайдено",
        "msg_ffmpeg_missing_body": "FFmpeg не знайдено. Без нього неможливо перетворити звук у вибраний формат та зберегти обкладинку.\n\nПродовжити без нього?",
        "dialog_ffmpeg_title": "Що таке FFmpeg та для чого він потрібен",
        "dialog_ffmpeg_header": "Що означає 'FFmpeg: Готовий' і для чого він потрібен:",
        "dialog_ffmpeg_content": (
            "FFmpeg — це головний мультимедійний двигун програми.\n\n"
            "YouTube та інші сайти транслюють музику у специфічних веб-форматах (наприклад, .webm). "
            "FFmpeg автоматично:\n"
            "1. Перетворює вихідний потік у звичний MP3, M4A, FLAC або WAV для прослуховування на будь-якому пристрої чи в машині.\n"
            "2. 'Вшиває' обкладинку альбому прямо всередину аудіофайлу.\n"
            "3. Записує ім'я виконавця та назву треку (теги).\n\n"
            "Зелений напис 'FFmpeg: Готовий' означає, що двигун виявлено на вашому комп'ютері (у папці bin/ або в системі) "
            "і всі функції працюватимуть на 100%!"
        ),
        "btn_close": "Зрозуміло, закрити",
    },
    "EN": {
        "app_title": "TrackPull",
        "app_subtitle": "Fast & intuitive music and playlist downloader",
        "theme_label": "Theme:",
        "lang_label": "Language:",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "theme_system": "System",
        "ffmpeg_ready": "FFmpeg: Ready",
        "ffmpeg_missing": "FFmpeg: Missing (Click)",
        "card_format": "Audio Format & Quality",
        "quality_title": "Sound Quality:",
        "quality_lossless": "Quality: Lossless (No Quality Loss)",
        "bitrate_320": "320 kbps (Studio Master)",
        "bitrate_256": "256 kbps (High Quality)",
        "bitrate_192": "192 kbps (Standard Quality)",
        "bitrate_128": "128 kbps (Compact / Space Saver)",
        "card_options": "Download Features",
        "switch_playlist": "Download entire playlist",
        "switch_metadata": "Save song title & artist (Tags)",
        "switch_thumbnail": "Save album cover art",
        "card_directory": "Save Location",
        "btn_browse": "Browse folder...",
        "btn_open_folder": "Open folder",
        "url_title": "Song or playlist link:",
        "url_placeholder": "Paste link from YouTube, SoundCloud, YouTube Music...",
        "btn_paste": "Paste",
        "btn_clear": "✕",
        "btn_download": "DOWNLOAD MUSIC",
        "btn_downloading": "DOWNLOADING...",
        "btn_resume": "CONTINUE DOWNLOAD",
        "btn_cancel": "Cancel",
        "btn_stopping": "Stopping...",
        "playlist_badge_idle": "Playlist: Ready",
        "playlist_badge_format": "Playlist: {index} of {total} ({index}/{total})",
        "playlist_badge_single": "Single Track",
        "playlist_completed_summary": "Playlist: {completed} of {total} saved!",
        "status_ready": "Status: Ready to download",
        "status_preparing": "Status: Preparing download...",
        "status_extracting": "Status: Fetching song details...",
        "status_converting": "Status: Converting audio (FFmpeg)...",
        "status_embedding_thumb": "Status: Embedding cover art...",
        "status_embedding_meta": "Status: Writing song tags...",
        "status_completed": "Status: Download completed!",
        "status_cancelled": "Status: Download stopped",
        "status_error": "Status: Download error",
        "status_playlist_error": "Error on song [{index}/{total}]. Click 'CONTINUE' to resume remaining!",
        "speed_label": "Speed: ",
        "eta_label": "ETA: ",
        "card_terminal": "Activity Log (Console):",
        "btn_clear_log": "Clear",
        "log_started": "=== TrackPull v1.0.1 ready. ===",
        "log_ffmpeg_found": "FFmpeg is ready for audio processing.",
        "log_deno_active": "YouTube accelerator (Deno) is active.",
        "log_resuming_from": "Resuming playlist download from song {index} of {total} ({index}/{total})...",
        "msg_empty_url_title": "Empty Link",
        "msg_empty_url_body": "Please paste a link to a song or playlist in the input field.",
        "msg_invalid_url_title": "Invalid Link",
        "msg_invalid_url_body": "The link must start with http:// or https://",
        "msg_success_title": "Success",
        "msg_success_body": "Audio successfully downloaded and saved!",
        "msg_resume_title": "Playlist Song Error",
        "msg_resume_body": (
            "Failed to download song #{failed_index} of {total}.\n\n"
            "Click the green 'CONTINUE DOWNLOAD' button to skip this file and download remaining songs (from {next_index} of {total})!"
        ),
        "msg_folder_not_found_title": "Folder Not Found",
        "msg_folder_not_found_body": "Specified folder does not exist:\n",
        "msg_ffmpeg_missing_title": "FFmpeg Missing",
        "msg_ffmpeg_missing_body": "FFmpeg is missing. Without it, audio conversion and cover art embedding will not work.\n\nContinue anyway?",
        "dialog_ffmpeg_title": "What is FFmpeg & Why is it needed",
        "dialog_ffmpeg_header": "What 'FFmpeg: Ready' means and why it's there:",
        "dialog_ffmpeg_content": (
            "FFmpeg is the core multimedia conversion engine used by TrackPull.\n\n"
            "Websites like YouTube stream audio in proprietary formats (.webm or raw .m4a). "
            "FFmpeg automatically:\n"
            "1. Converts the stream into standard MP3, M4A, FLAC, or WAV for playback in cars, phones, and music players.\n"
            "2. Embeds high-resolution cover art directly into the audio file.\n"
            "3. Writes the song title, artist name, and album metadata.\n\n"
            "The green 'FFmpeg: Ready' badge confirms that FFmpeg was found (in bin/ or system PATH) "
            "and all conversions will run with 100% fidelity!"
        ),
        "btn_close": "Got it, close",
    }
}


# ============================================================================
# CONFIGURATION AND DATA STRUCTURES
# ============================================================================

@dataclass(frozen=True)
class DownloadOptions:
    """Immutable data container encapsulating user-configured download options."""
    url: str
    output_directory: str
    audio_format: str
    audio_bitrate: str
    is_playlist: bool
    embed_metadata: bool
    embed_thumbnail: bool
    playlist_start_index: int = 1


class SystemDependencyChecker:
    """Utility class for inspecting external binaries (FFmpeg, Deno)."""

    @staticmethod
    def get_application_root() -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def initialize_runtime_environment(cls) -> None:
        base_dir: str = cls.get_application_root()
        candidate_paths: List[str] = [
            os.path.join(base_dir, "bin"),
            base_dir,
        ]

        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            winget_root = os.path.join(local_app_data, "Microsoft", "WinGet", "Packages")
            if os.path.isdir(winget_root):
                try:
                    for folder_name in os.listdir(winget_root):
                        lower_name = folder_name.lower()
                        if "ffmpeg" in lower_name or "deno" in lower_name:
                            full_pkg_dir = os.path.join(winget_root, folder_name)
                            candidate_paths.append(full_pkg_dir)
                            for root, dirs, _ in os.walk(full_pkg_dir):
                                if os.path.basename(root).lower() == "bin":
                                    candidate_paths.append(root)
                except Exception:
                    pass

        current_path: str = os.environ.get("PATH", "")
        new_valid_dirs: List[str] = [
            p for p in candidate_paths if os.path.isdir(p) and p not in current_path
        ]

        if new_valid_dirs:
            os.environ["PATH"] = os.pathsep.join(new_valid_dirs) + os.pathsep + current_path

    @classmethod
    def locate_ffmpeg(cls) -> tuple[bool, str]:
        system_path: Optional[str] = shutil.which("ffmpeg")
        if system_path:
            return True, system_path

        base_directory: str = cls.get_application_root()
        local_candidates: List[str] = [
            os.path.join(base_directory, "bin", "ffmpeg.exe"),
            os.path.join(base_directory, "ffmpeg.exe"),
            os.path.join(base_directory, "ffmpeg", "bin", "ffmpeg.exe"),
        ]

        for candidate_path in local_candidates:
            if os.path.isfile(candidate_path) and os.access(candidate_path, os.X_OK):
                return True, candidate_path

        return False, ""

    @classmethod
    def locate_deno(cls) -> tuple[bool, str]:
        deno_system = shutil.which("deno")
        if deno_system:
            return True, deno_system

        base_directory = cls.get_application_root()
        local_candidates = [
            os.path.join(base_directory, "bin", "deno.exe"),
            os.path.join(base_directory, "deno.exe"),
        ]
        for candidate in local_candidates:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return True, candidate

        return False, ""

    @staticmethod
    def get_default_download_directory() -> str:
        user_home: str = os.path.expanduser("~")
        music_folder: str = os.path.join(user_home, "Music")
        if os.path.isdir(music_folder):
            return music_folder

        downloads_folder: str = os.path.join(user_home, "Downloads")
        if os.path.isdir(downloads_folder):
            return downloads_folder

        return user_home


# ============================================================================
# YT-DLP CUSTOM LOGGER AND PROGRESS HANDLING
# ============================================================================

class YTDLPMessageLogger:
    """Custom logger redirecting yt-dlp messages to the UI console with playlist detection."""

    PLAYLIST_REGEX = re.compile(r'(?:video|item)?\s*(\d+)\s+of\s+(\d+)', re.IGNORECASE)

    def __init__(
        self,
        dispatch_log: Callable[[str, str], None],
        on_playlist_step: Optional[Callable[[int, int], None]] = None,
        on_track_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._dispatch_log: Callable[[str, str], None] = dispatch_log
        self._on_playlist_step: Optional[Callable[[int, int], None]] = on_playlist_step
        self._on_track_error: Optional[Callable[[str], None]] = on_track_error

    def _check_playlist_mention(self, message: str) -> None:
        match = self.PLAYLIST_REGEX.search(message)
        if match and self._on_playlist_step:
            try:
                idx = int(match.group(1))
                total = int(match.group(2))
                self._on_playlist_step(idx, total)
            except ValueError:
                pass

    def debug(self, message: str) -> None:
        clean_msg: str = message.strip()
        if not clean_msg:
            return

        self._check_playlist_mention(clean_msg)

        if "[download]" in clean_msg and "%" in clean_msg:
            return

        if clean_msg.startswith(("[ExtractAudio] Destination:", "[Metadata] Adding metadata", "[Thumbnails]")):
            self._dispatch_log(clean_msg, "INFO")
        elif clean_msg.startswith("[download] Destination:"):
            dest_name = clean_msg.replace("[download] Destination:", "").strip()
            self._dispatch_log(f"Файл: {os.path.basename(dest_name)}", "INFO")

    def info(self, message: str) -> None:
        clean_msg: str = message.strip()
        if not clean_msg:
            return
        self._check_playlist_mention(clean_msg)
        if not ("%" in clean_msg and "[download]" in clean_msg):
            self._dispatch_log(clean_msg, "INFO")

    def warning(self, message: str) -> None:
        clean_msg: str = message.strip()
        if clean_msg:
            if "No supported JavaScript runtime could be found" not in clean_msg:
                self._dispatch_log(f"Увага: {clean_msg}", "WARNING")

    def error(self, message: str) -> None:
        clean_msg: str = message.strip()
        if clean_msg:
            if self._on_track_error:
                self._on_track_error(clean_msg)
            self._dispatch_log(f"Помилка: {clean_msg}", "ERROR")


# ============================================================================
# ASYNCHRONOUS DOWNLOAD WORKER
# ============================================================================

class AudioDownloadWorker(threading.Thread):
    """Worker thread running yt-dlp asynchronously with resilient playlist & resume support."""

    def __init__(
        self,
        options: DownloadOptions,
        ffmpeg_location: str,
        deno_location: str,
        on_progress: Callable[[float, str, str, str, Optional[int], Optional[int]], None],
        on_phase_change: Callable[[str], None],
        on_log: Callable[[str, str], None],
        on_complete: Callable[[bool, str, bool, Optional[int], Optional[int], int], None],
    ) -> None:
        super().__init__(name="AudioDownloadWorkerThread", daemon=True)
        self.options: DownloadOptions = options
        self.ffmpeg_location: str = ffmpeg_location
        self.deno_location: str = deno_location
        self.on_progress: Callable[[float, str, str, str, Optional[int], Optional[int]], None] = on_progress
        self.on_phase_change: Callable[[str], None] = on_phase_change
        self.on_log: Callable[[str, str], None] = on_log
        self.on_complete: Callable[[bool, str, bool, Optional[int], Optional[int], int], None] = on_complete

        self._cancellation_requested: threading.Event = threading.Event()
        self._logged_postprocessors: Set[str] = set()

        self.current_playlist_index: Optional[int] = self.options.playlist_start_index if self.options.is_playlist else None
        self.current_playlist_total: Optional[int] = None
        self.current_track_title: str = ""
        self.completed_tracks_count: int = 0
        self.failed_tracks: List[int] = []
        self.last_failed_index: Optional[int] = None

    def request_cancellation(self) -> None:
        self._cancellation_requested.set()

    def _on_playlist_step_detected(self, index: int, total: int) -> None:
        self.current_playlist_index = index
        self.current_playlist_total = total

    def _on_track_error_detected(self, error_message: str) -> None:
        if self.current_playlist_index:
            self.last_failed_index = self.current_playlist_index
            if self.current_playlist_index not in self.failed_tracks:
                self.failed_tracks.append(self.current_playlist_index)

    def _progress_hook(self, payload: Dict[str, Any]) -> None:
        if self._cancellation_requested.is_set():
            raise yt_dlp.utils.DownloadCancelled("Завантаження зупинено користувачем.")

        status: Optional[str] = payload.get("status")

        if status == "downloading":
            downloaded_bytes: int = payload.get("downloaded_bytes") or 0
            total_bytes: Optional[int] = payload.get("total_bytes") or payload.get("total_bytes_estimate")
            speed: Optional[float] = payload.get("speed")
            eta_seconds: Optional[int] = payload.get("eta")
            filename: str = os.path.basename(payload.get("filename", ""))

            info_dict: Dict[str, Any] = payload.get("info_dict") or {}
            p_idx = (
                payload.get("playlist_index") or
                info_dict.get("playlist_index") or
                payload.get("playlist_autonumber")
            )
            p_cnt = (
                payload.get("n_entries") or
                payload.get("playlist_count") or
                info_dict.get("n_entries") or
                info_dict.get("playlist_count")
            )

            if p_idx:
                self.current_playlist_index = int(p_idx)
            if p_cnt:
                self.current_playlist_total = int(p_cnt)

            if info_dict.get("title"):
                self.current_track_title = str(info_dict.get("title"))

            ratio: float = 0.0
            if total_bytes and total_bytes > 0:
                ratio = max(0.0, min(1.0, downloaded_bytes / total_bytes))

            speed_text: str = "-- KB/s"
            if speed:
                if speed >= 1024 * 1024:
                    speed_text = f"{speed / (1024 * 1024):.2f} MB/s"
                elif speed >= 1024:
                    speed_text = f"{speed / 1024:.1f} KB/s"
                else:
                    speed_text = f"{speed:.0f} B/s"

            eta_text: str = "--:--"
            if eta_seconds is not None:
                minutes, seconds = divmod(int(eta_seconds), 60)
                hours, minutes = divmod(minutes, 60)
                if hours > 0:
                    eta_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    eta_text = f"{minutes:02d}:{seconds:02d}"

            track_name = self.current_track_title or filename
            self.on_progress(
                ratio,
                speed_text,
                eta_text,
                track_name,
                self.current_playlist_index,
                self.current_playlist_total
            )

        elif status == "finished":
            filename = os.path.basename(payload.get("filename", ""))
            self.completed_tracks_count += 1
            if self.current_playlist_index and self.current_playlist_total:
                self.on_phase_change(
                    f"[{self.current_playlist_index}/{self.current_playlist_total}] Аудіопотік отримано. Обробка..."
                )
            else:
                self.on_phase_change(f"Аудіопотік отримано ({filename}). Обробка...")

    def _postprocessor_hook(self, payload: Dict[str, Any]) -> None:
        if self._cancellation_requested.is_set():
            raise yt_dlp.utils.DownloadCancelled("Завантаження зупинено користувачем.")

        status: Optional[str] = payload.get("status")
        pp_name: str = payload.get("postprocessor", "PostProcessor")
        info_dict: Dict[str, Any] = payload.get("info_dict") or {}

        p_idx = (
            payload.get("playlist_index") or
            info_dict.get("playlist_index") or
            self.current_playlist_index
        )
        p_cnt = (
            payload.get("n_entries") or
            payload.get("playlist_count") or
            info_dict.get("n_entries") or
            self.current_playlist_total
        )
        prefix = f"[{p_idx}/{p_cnt}] " if (p_idx and p_cnt) else ""

        if status == "started":
            if pp_name == "ExtractAudio":
                self.on_phase_change(f"{prefix}Перетворення звуку (FFmpeg)...")
            elif pp_name == "EmbedThumbnail":
                self.on_phase_change(f"{prefix}Збереження обкладинки треку...")
            elif pp_name == "Metadata":
                self.on_phase_change(f"{prefix}Запис автора та назви пісні...")
            else:
                self.on_phase_change(f"{prefix}Обробка: {pp_name}...")
        elif status == "finished":
            item_key = f"{pp_name}_{info_dict.get('id', '')}"
            if item_key not in self._logged_postprocessors:
                self._logged_postprocessors.add(item_key)
                if pp_name == "ExtractAudio":
                    self.on_log(f"{prefix}Перетворення звуку завершено.", "INFO")
                elif pp_name == "EmbedThumbnail":
                    self.on_log(f"{prefix}Обкладинку треку успішно збережено.", "INFO")
                elif pp_name == "Metadata":
                    self.on_log(f"{prefix}Дані автора та назву пісні записано.", "INFO")

    def run(self) -> None:
        self.on_log(f"Початок обробки: {self.options.url}", "INFO")
        self.on_phase_change("Отримання інформації про аудіо...")

        try:
            os.makedirs(self.options.output_directory, exist_ok=True)
        except OSError as folder_err:
            error_message = f"Не вдалося створити папку для збереження: {folder_err}"
            self.on_log(error_message, "ERROR")
            self.on_complete(False, error_message, False, None, None, 0)
            return

        if self.options.is_playlist:
            output_template: str = os.path.join(
                self.options.output_directory,
                "%(playlist_title,playlist)s",
                "%(playlist_index&{:02d} - |)s%(title)s.%(ext)s"
            )
        else:
            output_template = os.path.join(
                self.options.output_directory,
                "%(title)s.%(ext)s"
            )

        codec: str = self.options.audio_format.lower()
        bitrate_value: str = self.options.audio_bitrate

        postprocessors: List[Dict[str, Any]] = []

        extract_audio_step: Dict[str, Any] = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": codec,
            "nopostoverwrites": False,
        }
        if codec in ("mp3", "m4a") and bitrate_value:
            extract_audio_step["preferredquality"] = str(bitrate_value)

        postprocessors.append(extract_audio_step)

        if self.options.embed_metadata:
            postprocessors.append({
                "key": "FFmpegMetadata",
                "add_metadata": True,
                "add_chapters": True,
            })

        if self.options.embed_thumbnail:
            postprocessors.append({
                "key": "EmbedThumbnail",
                "already_have_thumbnail": False,
            })

        # Archive file ensures already downloaded songs are skipped immediately without re-downloading
        archive_file: str = os.path.join(self.options.output_directory, ".trackpull_archive.txt")

        ydl_opts: Dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "noplaylist": not self.options.is_playlist,
            "ignoreerrors": True if self.options.is_playlist else False,
            "download_archive": archive_file,
            "concurrent_fragment_downloads": 8,
            "buffersize": 1024 * 64,
            "http_chunk_size": 10485760,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "skip": ["translated_subs"],
                }
            },
            "postprocessors": postprocessors,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "logger": YTDLPMessageLogger(
                self.on_log,
                on_playlist_step=self._on_playlist_step_detected,
                on_track_error=self._on_track_error_detected,
            ),
            "quiet": False,
            "no_warnings": False,
            "updatetime": False,
        }

        if self.options.playlist_start_index > 1:
            ydl_opts["playliststart"] = self.options.playlist_start_index
            self.on_log(
                f"Продовження завантаження з пісні {self.options.playlist_start_index}...",
                "INFO"
            )

        if self.options.embed_thumbnail:
            ydl_opts["writethumbnail"] = True

        if self.ffmpeg_location:
            ydl_opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_location)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                exit_code: int = ydl.download([self.options.url])
                if exit_code == 0:
                    if self.options.is_playlist and self.current_playlist_total:
                        success_msg: str = (
                            f"Усі {self.current_playlist_total} пісень плейлиста успішно збережено!"
                        )
                    else:
                        success_msg = "Усі аудіотреки успішно завантажено та збережено!"
                    self.on_log(success_msg, "SUCCESS")
                    self.on_complete(
                        True,
                        success_msg,
                        False,
                        None,
                        self.current_playlist_total,
                        self.completed_tracks_count or (self.current_playlist_total or 1)
                    )
                else:
                    if self.failed_tracks:
                        failed_count = len(self.failed_tracks)
                        summary_msg = (
                            f"Завершено: завантажено {self.completed_tracks_count} пісень. "
                            f"Пропущено {failed_count} через недоступність джерела."
                        )
                        self.on_log(summary_msg, "WARNING")
                        self.on_complete(
                            True,
                            summary_msg,
                            False,
                            None,
                            self.current_playlist_total,
                            self.completed_tracks_count
                        )
                    else:
                        partial_msg: str = f"Завантаження завершилося з попередженням (код {exit_code})."
                        self.on_log(partial_msg, "WARNING")
                        self.on_complete(
                            True,
                            partial_msg,
                            False,
                            None,
                            self.current_playlist_total,
                            self.completed_tracks_count
                        )

        except yt_dlp.utils.DownloadCancelled:
            cancel_msg: str = "Завантаження зупинено користувачем."
            self.on_log(cancel_msg, "WARNING")
            self.on_complete(
                False,
                cancel_msg,
                True,
                self.current_playlist_index,
                self.current_playlist_total,
                self.completed_tracks_count
            )

        except yt_dlp.utils.DownloadError as download_err:
            raw_err: str = str(download_err)
            failed_idx = self.last_failed_index or self.current_playlist_index
            if "ffmpeg" in raw_err.lower():
                friendly_err: str = (
                    "Не знайдено FFmpeg для конвертації звуку або запису тегів. "
                    "Будь ласка, перевірте наявність FFmpeg."
                )
            elif "unsupported url" in raw_err.lower():
                friendly_err = "Непідтримуване або некоректне посилання на пісню чи плейлист."
            elif "private video" in raw_err.lower() or "sign in" in raw_err.lower():
                friendly_err = (
                    f"Пісня #{failed_idx} є приватною або недоступною. "
                    "Натисніть «ПРОДОВЖИТИ», щоб завантажити наступні пісні."
                    if failed_idx else "Цей трек є приватним чи вимагає авторизації в акаунті."
                )
            else:
                friendly_err = f"Помилка завантаження: {raw_err}"

            self.on_log(friendly_err, "ERROR")
            self.on_complete(
                False,
                friendly_err,
                False,
                failed_idx,
                self.current_playlist_total,
                self.completed_tracks_count
            )

        except Exception as unexpected_err:
            error_msg: str = f"Непередбачена помилка: {unexpected_err}"
            failed_idx = self.last_failed_index or self.current_playlist_index
            self.on_log(error_msg, "ERROR")
            self.on_complete(
                False,
                error_msg,
                False,
                failed_idx,
                self.current_playlist_total,
                self.completed_tracks_count
            )


# ============================================================================
# MAIN APPLICATION INTERFACE (v1.0.1 BILINGUAL PRO STUDIO)
# ============================================================================

class TrackPullApp(ctk.CTk):
    """Studio-grade bilingual Windows downloader interface."""

    APP_TITLE: str = "TrackPull"
    APP_VERSION: str = "v1.0.1"
    DEFAULT_WINDOW_SIZE: str = "960x720"
    MIN_WINDOW_WIDTH: int = 860
    MIN_WINDOW_HEIGHT: int = 660

    # Color tokens for solid surfaces
    BG_ROOT_COLOR = ("#F1F3F9", "#0C0D11")
    BG_CARD_COLOR = ("#FFFFFF", "#16171E")
    BORDER_CARD_COLOR = ("#E2E6EF", "#232530")
    TEXT_PRIMARY = ("#0F172A", "#F8FAFC")
    TEXT_SECONDARY = ("#64748B", "#94A3B8")
    ACCENT_PRIMARY = ("#2563EB", "#3B82F6")
    ACCENT_HOVER = ("#1D4ED8", "#2563EB")
    ACCENT_DANGER = ("#DC2626", "#EF4444")
    ACCENT_DANGER_HOVER = ("#B91C1C", "#DC2626")

    FORMAT_OPTIONS: List[str] = ["MP3", "M4A", "FLAC", "WAV"]

    def __init__(self) -> None:
        SystemDependencyChecker.initialize_runtime_environment()

        super().__init__()

        # Current language state: "UA" by default
        self.current_lang: str = "UA"

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=self.BG_ROOT_COLOR)

        self.title(f"{self.APP_TITLE} {self.APP_VERSION}")
        self.geometry(self.DEFAULT_WINDOW_SIZE)
        self.minsize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)

        self.download_directory_var: ctk.StringVar = ctk.StringVar(
            value=SystemDependencyChecker.get_default_download_directory()
        )
        self.audio_format_var: ctk.StringVar = ctk.StringVar(value="MP3")
        self.audio_quality_var: ctk.StringVar = ctk.StringVar()
        self.playlist_var: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self.metadata_var: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self.thumbnail_var: ctk.BooleanVar = ctk.BooleanVar(value=True)

        self._active_worker: Optional[AudioDownloadWorker] = None
        self._ffmpeg_available: bool = False
        self._ffmpeg_location: str = ""
        self._deno_available: bool = False
        self._deno_location: str = ""
        self.resumable_info: Optional[Dict[str, Any]] = None

        # Set taskbar icon
        self._set_application_icon()

        # Enable universal keyboard shortcuts across all layouts (Ukrainian, English, etc.)
        self._enable_universal_clipboard_shortcuts()

        # Build solid dual-column studio layout
        self._build_interface()

        # Initialize text in default language
        self._apply_language(self.current_lang)

        # Evaluate system dependencies after window maps
        self.after(200, self._evaluate_system_dependencies)

    def _t(self, key: str) -> str:
        """Retrieves translated string for the current active language."""
        return TRANSLATIONS.get(self.current_lang, {}).get(key, key)

    def dispatch_to_ui(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self.after(0, lambda: function(*args, **kwargs))

    def _enable_universal_clipboard_shortcuts(self) -> None:
        """Fixes Windows/Tkinter bug where Ctrl+V, Ctrl+C, Ctrl+X, Ctrl+A only work on English keyboard layout."""
        # 1. Map Cyrillic keysyms to virtual Tkinter clipboard events
        cyrillic_mappings = [
            ("<<Paste>>", ["Cyrillic_em", "Cyrillic_EM"]),
            ("<<Copy>>", ["Cyrillic_es", "Cyrillic_ES"]),
            ("<<Cut>>", ["Cyrillic_che", "Cyrillic_CHE"]),
            ("<<SelectAll>>", ["Cyrillic_ef", "Cyrillic_EF"]),
            ("<<Undo>>", ["Cyrillic_ya", "Cyrillic_YA"]),
        ]
        for event_name, keysyms in cyrillic_mappings:
            for sym in keysyms:
                try:
                    self.event_add(event_name, f"<Control-Key-{sym}>")
                except Exception:
                    pass

        # 2. Global keycode-level handler (Windows VK codes: V=86, C=67, X=88, A=65, Z=90)
        def _on_control_keypress(event: Any) -> Optional[str]:
            if not (event.state & 4):
                return None

            raw_widget = event.widget
            target = getattr(raw_widget, "_entry", getattr(raw_widget, "_textbox", raw_widget))

            # VK_V = 86: Paste (Ctrl+V)
            if event.keycode == 86 and event.keysym not in ("v", "V"):
                try:
                    target.event_generate("<<Paste>>")
                    self.after(50, self._on_url_modified)
                    return "break"
                except Exception:
                    pass

            # VK_C = 67: Copy (Ctrl+C)
            elif event.keycode == 67 and event.keysym not in ("c", "C"):
                try:
                    target.event_generate("<<Copy>>")
                    return "break"
                except Exception:
                    pass

            # VK_X = 88: Cut (Ctrl+X)
            elif event.keycode == 88 and event.keysym not in ("x", "X"):
                try:
                    target.event_generate("<<Cut>>")
                    self.after(50, self._on_url_modified)
                    return "break"
                except Exception:
                    pass

            # VK_A = 65: Select All (Ctrl+A)
            elif event.keycode == 65 and event.keysym not in ("a", "A"):
                try:
                    import tkinter as tk
                    if isinstance(target, tk.Entry):
                        target.select_range(0, "end")
                        target.icursor("end")
                        return "break"
                    elif isinstance(target, tk.Text):
                        target.tag_add("sel", "1.0", "end")
                        return "break"
                except Exception:
                    pass

            # VK_Z = 90: Undo (Ctrl+Z)
            elif event.keycode == 90 and event.keysym not in ("z", "Z"):
                try:
                    target.event_generate("<<Undo>>")
                    return "break"
                except Exception:
                    pass

            return None

        self.bind_all("<Control-KeyPress>", _on_control_keypress, add="+")

    def _set_application_icon(self) -> None:
        try:
            base_dir = SystemDependencyChecker.get_application_root()
            meipass_dir = getattr(sys, "_MEIPASS", base_dir)

            ico_candidates = [
                os.path.join(base_dir, "assets", "icon.ico"),
                os.path.join(meipass_dir, "assets", "icon.ico"),
                os.path.join(base_dir, "icon.ico"),
            ]
            for ico_path in ico_candidates:
                if os.path.isfile(ico_path):
                    self.iconbitmap(ico_path)
                    break

            png_candidates = [
                os.path.join(base_dir, "assets", "icon.png"),
                os.path.join(meipass_dir, "assets", "icon.png"),
            ]
            for png_path in png_candidates:
                if os.path.isfile(png_path):
                    from PIL import ImageTk, Image
                    pil_img = Image.open(png_path)
                    self._taskbar_icon = ImageTk.PhotoImage(pil_img)
                    self.iconphoto(False, self._taskbar_icon)
                    break
        except Exception:
            pass

    # ------------------------------------------------------------------------
    # STUDIO DUAL-COLUMN INTERFACE ARCHITECTURE
    # ------------------------------------------------------------------------

    def _build_interface(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Top Bar
        self.grid_rowconfigure(1, weight=1)  # Content

        # 1. Header Bar
        self._create_header_bar(self)

        # 2. Main Studio Body
        self.studio_body = ctk.CTkFrame(self, fg_color=self.BG_ROOT_COLOR)
        self.studio_body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self.studio_body.grid_columnconfigure(0, weight=0, minsize=350)
        self.studio_body.grid_columnconfigure(1, weight=1)
        self.studio_body.grid_rowconfigure(0, weight=1)

        # Left Column: User Settings & Options
        self.left_sidebar = ctk.CTkFrame(self.studio_body, fg_color=self.BG_ROOT_COLOR)
        self.left_sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.left_sidebar.grid_columnconfigure(0, weight=1)

        self._create_format_card(self.left_sidebar)
        self._create_options_card(self.left_sidebar)
        self._create_directory_card(self.left_sidebar)

        # Right Column: Studio Dashboard (Hero URL, Action, Metrics, Terminal)
        self.right_panel = ctk.CTkFrame(self.studio_body, fg_color=self.BG_ROOT_COLOR)
        self.right_panel.grid(row=0, column=1, sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(2, weight=1)

        self._create_url_card(self.right_panel)
        self._create_action_monitor_card(self.right_panel)
        self._create_terminal_card(self.right_panel)

    def _create_header_bar(self, parent: ctk.CTkBaseClass) -> None:
        header = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=self.BG_CARD_COLOR,
            border_width=1,
            border_color=self.BORDER_CARD_COLOR
        )
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 12), ipady=4)
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        # Left Branding
        brand_box = ctk.CTkFrame(header, fg_color="transparent")
        brand_box.grid(row=0, column=0, sticky="w", padx=16, pady=6)

        base_dir = SystemDependencyChecker.get_application_root()
        meipass_dir = getattr(sys, "_MEIPASS", base_dir)
        for d in (base_dir, meipass_dir):
            icon_png = os.path.join(d, "assets", "icon.png")
            if os.path.isfile(icon_png):
                try:
                    from PIL import Image
                    self._header_logo = ctk.CTkImage(
                        light_image=Image.open(icon_png),
                        dark_image=Image.open(icon_png),
                        size=(36, 36)
                    )
                    logo_lbl = ctk.CTkLabel(brand_box, image=self._header_logo, text="")
                    logo_lbl.pack(side="left", padx=(0, 12))
                    break
                except Exception:
                    pass

        titles = ctk.CTkFrame(brand_box, fg_color="transparent")
        titles.pack(side="left")

        title_row = ctk.CTkFrame(titles, fg_color="transparent")
        title_row.pack(anchor="w")

        self.title_label = ctk.CTkLabel(
            title_row,
            text=self.APP_TITLE,
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self.TEXT_PRIMARY
        )
        self.title_label.pack(side="left")

        self.version_pill = ctk.CTkLabel(
            title_row,
            text=self.APP_VERSION,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#EEF2FF", "#1E2235"),
            text_color=("#4F46E5", "#818CF8"),
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.version_pill.pack(side="left", padx=8)

        self.subtitle_label = ctk.CTkLabel(
            titles,
            text=self._t("app_subtitle"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.TEXT_SECONDARY
        )
        self.subtitle_label.pack(anchor="w")

        # Right Controls: FFmpeg Badge, Language Selector & Theme Switcher
        nav_controls = ctk.CTkFrame(header, fg_color="transparent")
        nav_controls.grid(row=0, column=1, sticky="e", padx=16, pady=6)

        self.ffmpeg_status_badge = ctk.CTkLabel(
            nav_controls,
            text=self._t("ffmpeg_ready"),
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#ECFDF5", "#064E3B"),
            text_color=("#059669", "#34D399"),
            corner_radius=6,
            padx=10,
            pady=4,
            cursor="hand2"
        )
        self.ffmpeg_status_badge.pack(side="left", padx=(0, 10))
        self.ffmpeg_status_badge.bind("<Button-1>", lambda e: self._show_ffmpeg_instruction_dialog())

        # Language Switcher
        self.lang_lbl = ctk.CTkLabel(
            nav_controls,
            text=self._t("lang_label"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.TEXT_SECONDARY
        )
        self.lang_lbl.pack(side="left", padx=(0, 4))

        self.lang_menu = ctk.CTkOptionMenu(
            nav_controls,
            values=["Українська", "English"],
            command=self._on_language_changed,
            width=110,
            height=28
        )
        self.lang_menu.set("Українська")
        self.lang_menu.pack(side="left", padx=(0, 10))

        # Theme Switcher
        self.theme_lbl = ctk.CTkLabel(
            nav_controls,
            text=self._t("theme_label"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.TEXT_SECONDARY
        )
        self.theme_lbl.pack(side="left", padx=(0, 4))

        self.theme_menu = ctk.CTkOptionMenu(
            nav_controls,
            values=[self._t("theme_dark"), self._t("theme_light"), self._t("theme_system")],
            command=self._on_theme_changed,
            width=100,
            height=28
        )
        self.theme_menu.set(self._t("theme_dark"))
        self.theme_menu.pack(side="left")

    # ------------------------------------------------------------------------
    # LEFT COLUMN: CONFIGURATION CARDS
    # ------------------------------------------------------------------------

    def _create_format_card(self, parent: ctk.CTkBaseClass) -> None:
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=self.BG_CARD_COLOR,
            border_width=1,
            border_color=self.BORDER_CARD_COLOR
        )
        card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        self.format_card_title = ctk.CTkLabel(
            card,
            text=self._t("card_format"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.TEXT_PRIMARY
        )
        self.format_card_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))

        self.format_segmented = ctk.CTkSegmentedButton(
            card,
            values=self.FORMAT_OPTIONS,
            command=self._on_format_changed,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.format_segmented.set("MP3")
        self.format_segmented.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        self.quality_title = ctk.CTkLabel(
            card,
            text=self._t("quality_title"),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.TEXT_SECONDARY
        )
        self.quality_title.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 4))

        self.quality_menu = ctk.CTkOptionMenu(
            card,
            values=[
                self._t("bitrate_320"),
                self._t("bitrate_256"),
                self._t("bitrate_192"),
                self._t("bitrate_128")
            ],
            variable=self.audio_quality_var,
            height=32
        )
        self.quality_menu.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))

    def _create_options_card(self, parent: ctk.CTkBaseClass) -> None:
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=self.BG_CARD_COLOR,
            border_width=1,
            border_color=self.BORDER_CARD_COLOR
        )
        card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        self.options_card_title = ctk.CTkLabel(
            card,
            text=self._t("card_options"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.TEXT_PRIMARY
        )
        self.options_card_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        switches_box = ctk.CTkFrame(card, fg_color="transparent")
        switches_box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))

        self.playlist_switch = ctk.CTkSwitch(
            switches_box,
            text=self._t("switch_playlist"),
            variable=self.playlist_var,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.playlist_switch.pack(anchor="w", pady=(0, 8))

        self.metadata_switch = ctk.CTkSwitch(
            switches_box,
            text=self._t("switch_metadata"),
            variable=self.metadata_var,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.metadata_switch.pack(anchor="w", pady=(0, 8))

        self.thumbnail_switch = ctk.CTkSwitch(
            switches_box,
            text=self._t("switch_thumbnail"),
            variable=self.thumbnail_var,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.thumbnail_switch.pack(anchor="w")

    def _create_directory_card(self, parent: ctk.CTkBaseClass) -> None:
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=self.BG_CARD_COLOR,
            border_width=1,
            border_color=self.BORDER_CARD_COLOR
        )
        card.grid(row=2, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        self.dir_card_title = ctk.CTkLabel(
            card,
            text=self._t("card_directory"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.TEXT_PRIMARY
        )
        self.dir_card_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))

        self.dir_entry = ctk.CTkEntry(
            card,
            textvariable=self.download_directory_var,
            height=34,
            font=ctk.CTkFont(size=11)
        )
        self.dir_entry.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        self.browse_btn = ctk.CTkButton(
            btn_row,
            text=self._t("btn_browse"),
            height=32,
            font=ctk.CTkFont(size=12),
            command=self._browse_directory
        )
        self.browse_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.open_btn = ctk.CTkButton(
            btn_row,
            text=self._t("btn_open_folder"),
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._open_directory_in_explorer
        )
        self.open_btn.grid(row=0, column=1, sticky="ew")

    # ------------------------------------------------------------------------
    # RIGHT COLUMN: ACTION STUDIO, MONITOR & TERMINAL
    # ------------------------------------------------------------------------

    def _create_url_card(self, parent: ctk.CTkBaseClass) -> None:
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=self.BG_CARD_COLOR,
            border_width=1,
            border_color=self.BORDER_CARD_COLOR
        )
        card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        self.url_card_title = ctk.CTkLabel(
            card,
            text=self._t("url_title"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.TEXT_PRIMARY
        )
        self.url_card_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))

        input_box = ctk.CTkFrame(card, fg_color="transparent")
        input_box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
        input_box.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_box,
            placeholder_text=self._t("url_placeholder"),
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<KeyRelease>", lambda e: self._on_url_modified())

        self.paste_btn = ctk.CTkButton(
            input_box,
            text=self._t("btn_paste"),
            width=90,
            height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._paste_clipboard_url
        )
        self.paste_btn.grid(row=0, column=1, padx=(0, 6))

        self.clear_btn = ctk.CTkButton(
            input_box,
            text=self._t("btn_clear"),
            width=42,
            height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._clear_url_entry
        )
        self.clear_btn.grid(row=0, column=2)

    def _create_action_monitor_card(self, parent: ctk.CTkBaseClass) -> None:
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=self.BG_CARD_COLOR,
            border_width=1,
            border_color=self.BORDER_CARD_COLOR
        )
        card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        btn_row.grid_columnconfigure(0, weight=4)
        btn_row.grid_columnconfigure(1, weight=1)

        self.download_button = ctk.CTkButton(
            btn_row,
            text=self._t("btn_download"),
            font=ctk.CTkFont(size=15, weight="bold"),
            height=46,
            corner_radius=8,
            fg_color=self.ACCENT_PRIMARY,
            hover_color=self.ACCENT_HOVER,
            command=self._on_download_button_clicked
        )
        self.download_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.cancel_button = ctk.CTkButton(
            btn_row,
            text=self._t("btn_cancel"),
            font=ctk.CTkFont(size=13, weight="bold"),
            height=46,
            corner_radius=8,
            fg_color=self.ACCENT_DANGER,
            hover_color=self.ACCENT_DANGER_HOVER,
            state="disabled",
            command=self._on_cancel_button_clicked
        )
        self.cancel_button.grid(row=0, column=1, sticky="ew")

        # Row 1: Status Phase & Dedicated Playlist Progress Pill
        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        status_row.grid_columnconfigure(0, weight=1)
        status_row.grid_columnconfigure(1, weight=0)

        self.status_phase_label = ctk.CTkLabel(
            status_row,
            text=self._t("status_ready"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.TEXT_PRIMARY,
            anchor="w"
        )
        self.status_phase_label.grid(row=0, column=0, sticky="w")

        self.playlist_badge = ctk.CTkLabel(
            status_row,
            text=self._t("playlist_badge_idle"),
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#EEF2FF", "#1E2235"),
            text_color=("#4F46E5", "#818CF8"),
            corner_radius=6,
            padx=10,
            pady=3,
        )
        self.playlist_badge.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(card, height=10, corner_radius=5)
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.progress_bar.set(0.0)

        metrics_box = ctk.CTkFrame(card, fg_color="transparent")
        metrics_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        metrics_box.grid_columnconfigure(0, weight=2)
        metrics_box.grid_columnconfigure(1, weight=1)
        metrics_box.grid_columnconfigure(2, weight=1)

        self.current_track_label = ctk.CTkLabel(
            metrics_box,
            text="--",
            font=ctk.CTkFont(size=11),
            text_color=self.TEXT_SECONDARY,
            anchor="w"
        )
        self.current_track_label.grid(row=0, column=0, sticky="w")

        self.speed_badge = ctk.CTkLabel(
            metrics_box,
            text=f"{self._t('speed_label')}--",
            font=ctk.CTkFont(size=11),
            text_color=self.TEXT_SECONDARY,
            anchor="e"
        )
        self.speed_badge.grid(row=0, column=1, sticky="e", padx=(0, 12))

        self.eta_badge = ctk.CTkLabel(
            metrics_box,
            text=f"0.0%  |  {self._t('eta_label')}--:--",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.TEXT_PRIMARY,
            anchor="e"
        )
        self.eta_badge.grid(row=0, column=2, sticky="e")

    def _create_terminal_card(self, parent: ctk.CTkBaseClass) -> None:
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=self.BG_CARD_COLOR,
            border_width=1,
            border_color=self.BORDER_CARD_COLOR
        )
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        header_box = ctk.CTkFrame(card, fg_color="transparent")
        header_box.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))
        header_box.grid_columnconfigure(0, weight=1)

        self.terminal_title = ctk.CTkLabel(
            header_box,
            text=self._t("card_terminal"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.TEXT_PRIMARY
        )
        self.terminal_title.grid(row=0, column=0, sticky="w")

        self.clear_log_btn = ctk.CTkButton(
            header_box,
            text=self._t("btn_clear_log"),
            width=85,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            command=self._clear_console_log
        )
        self.clear_log_btn.grid(row=0, column=1, sticky="e")

        self.console_textbox = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
            activate_scrollbars=True
        )
        self.console_textbox.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        self._append_log_message(self._t("log_started"), "INFO")

    # ------------------------------------------------------------------------
    # REAL-TIME BILINGUAL LANGUAGE SWITCHER
    # ------------------------------------------------------------------------

    def _on_language_changed(self, selected_lang_text: str) -> None:
        if "English" in selected_lang_text:
            self.current_lang = "EN"
        else:
            self.current_lang = "UA"
        self._apply_language(self.current_lang)

    def _apply_language(self, lang: str) -> None:
        """Dynamically re-translates all interface elements instantly."""
        self.title(f"{self.APP_TITLE} {self.APP_VERSION}")
        self.subtitle_label.configure(text=self._t("app_subtitle"))
        self.lang_lbl.configure(text=self._t("lang_label"))
        self.theme_lbl.configure(text=self._t("theme_label"))

        # Re-populate theme menu strings
        current_theme_selection = self.theme_menu.get()
        self.theme_menu.configure(
            values=[self._t("theme_dark"), self._t("theme_light"), self._t("theme_system")]
        )
        if lang == "EN":
            if current_theme_selection == "Темна":
                self.theme_menu.set("Dark")
            elif current_theme_selection == "Світла":
                self.theme_menu.set("Light")
            elif current_theme_selection == "Системна":
                self.theme_menu.set("System")
        else:
            if current_theme_selection == "Dark":
                self.theme_menu.set("Темна")
            elif current_theme_selection == "Light":
                self.theme_menu.set("Світла")
            elif current_theme_selection == "System":
                self.theme_menu.set("Системна")

        # Update FFmpeg status badge
        if self._ffmpeg_available:
            self.ffmpeg_status_badge.configure(text=self._t("ffmpeg_ready"))
        else:
            self.ffmpeg_status_badge.configure(text=self._t("ffmpeg_missing"))

        # Left Column Cards
        self.format_card_title.configure(text=self._t("card_format"))
        self.quality_title.configure(text=self._t("quality_title"))

        # Bitrate dropdown items
        quality_values = [
            self._t("bitrate_320"),
            self._t("bitrate_256"),
            self._t("bitrate_192"),
            self._t("bitrate_128")
        ]
        self.quality_menu.configure(values=quality_values)
        if self.audio_format_var.get().upper() in ("FLAC", "WAV"):
            self.quality_title.configure(text=self._t("quality_lossless"))
            self.quality_menu.set(self._t("quality_lossless"))
        else:
            self.quality_menu.set(quality_values[0])

        self.options_card_title.configure(text=self._t("card_options"))
        self.playlist_switch.configure(text=self._t("switch_playlist"))
        self.metadata_switch.configure(text=self._t("switch_metadata"))
        self.thumbnail_switch.configure(text=self._t("switch_thumbnail"))

        self.dir_card_title.configure(text=self._t("card_directory"))
        self.browse_btn.configure(text=self._t("btn_browse"))
        self.open_btn.configure(text=self._t("btn_open_folder"))

        # Right Column Cards
        self.url_card_title.configure(text=self._t("url_title"))
        self.url_entry.configure(placeholder_text=self._t("url_placeholder"))
        self.paste_btn.configure(text=self._t("btn_paste"))

        if not self._active_worker:
            if self.resumable_info:
                next_idx = self.resumable_info.get("next_index", 1)
                total = self.resumable_info.get("total_count", "?")
                self.download_button.configure(
                    text=f"{self._t('btn_resume')} ({next_idx}/{total})",
                    fg_color=("#059669", "#10B981"),
                    hover_color=("#047857", "#059669")
                )
            else:
                self.download_button.configure(
                    text=self._t("btn_download"),
                    fg_color=self.ACCENT_PRIMARY,
                    hover_color=self.ACCENT_HOVER
                )
            self.cancel_button.configure(text=self._t("btn_cancel"))
            self.status_phase_label.configure(text=self._t("status_ready"))
            self.playlist_badge.configure(text=self._t("playlist_badge_idle"))
        else:
            self.download_button.configure(text=self._t("btn_downloading"))
            self.cancel_button.configure(text=self._t("btn_cancel"))

        self.speed_badge.configure(text=f"{self._t('speed_label')}--")
        self.eta_badge.configure(text=f"0.0%  |  {self._t('eta_label')}--:--")

        self.terminal_title.configure(text=self._t("card_terminal"))
        self.clear_log_btn.configure(text=self._t("btn_clear_log"))

    # ------------------------------------------------------------------------
    # EVENT HANDLERS AND LOGIC
    # ------------------------------------------------------------------------

    def _on_theme_changed(self, selected_theme: str) -> None:
        if selected_theme in ("Темна", "Dark"):
            ctk.set_appearance_mode("Dark")
        elif selected_theme in ("Світла", "Light"):
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("System")

    def _on_format_changed(self, selected_format: str) -> None:
        self.audio_format_var.set(selected_format)
        if selected_format.upper() in ("FLAC", "WAV"):
            self.quality_menu.configure(state="disabled")
            self.quality_title.configure(text=self._t("quality_lossless"))
            self.quality_menu.set(self._t("quality_lossless"))
        else:
            self.quality_menu.configure(state="normal")
            self.quality_title.configure(text=self._t("quality_title"))
            self.quality_menu.set(self._t("bitrate_320"))

    def _on_url_modified(self) -> None:
        if self.resumable_info:
            self.resumable_info = None
            self.download_button.configure(
                text=self._t("btn_download"),
                fg_color=self.ACCENT_PRIMARY,
                hover_color=self.ACCENT_HOVER
            )
            self.playlist_badge.configure(text=self._t("playlist_badge_idle"))

    def _paste_clipboard_url(self) -> None:
        try:
            content: str = self.clipboard_get().strip()
            if content:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, content)
                self._on_url_modified()
                self._append_log_message(f"Вставлено: {content}", "INFO")
        except Exception as clip_err:
            self._append_log_message(f"Буфер обміну недоступний: {clip_err}", "WARNING")

    def _clear_url_entry(self) -> None:
        self.url_entry.delete(0, "end")
        self._on_url_modified()

    def _browse_directory(self) -> None:
        selected: str = filedialog.askdirectory(
            initialdir=self.download_directory_var.get(),
            title=self._t("btn_browse")
        )
        if selected:
            self.download_directory_var.set(selected)
            self._append_log_message(f"Папку змінено: {selected}", "INFO")

    def _open_directory_in_explorer(self) -> None:
        folder_path: str = self.download_directory_var.get()
        if os.path.isdir(folder_path):
            try:
                os.startfile(folder_path)
            except Exception as explorer_err:
                self._append_log_message(f"Помилка відкриття провідника: {explorer_err}", "ERROR")
        else:
            messagebox.showwarning(
                self._t("msg_folder_not_found_title"),
                f"{self._t('msg_folder_not_found_body')}{folder_path}"
            )

    def _clear_console_log(self) -> None:
        self.console_textbox.delete("1.0", "end")

    def _append_log_message(self, message: str, level: str = "INFO") -> None:
        import datetime
        timestamp: str = datetime.datetime.now().strftime("%H:%M:%S")
        prefix: str = {
            "INFO": "[INFO]",
            "WARNING": "[УВАГА]" if self.current_lang == "UA" else "[WARN]",
            "ERROR": "[ПОМИЛКА]" if self.current_lang == "UA" else "[ERROR]",
            "SUCCESS": "[УСПІХ]" if self.current_lang == "UA" else "[OK]",
        }.get(level, "[LOG]")

        formatted: str = f"[{timestamp}] {prefix} {message}\n"
        self.console_textbox.insert("end", formatted)
        self.console_textbox.see("end")

    def _evaluate_system_dependencies(self) -> None:
        is_ffmpeg_available, ffmpeg_loc = SystemDependencyChecker.locate_ffmpeg()
        self._ffmpeg_available = is_ffmpeg_available
        self._ffmpeg_location = ffmpeg_loc

        is_deno_available, deno_loc = SystemDependencyChecker.locate_deno()
        self._deno_available = is_deno_available
        self._deno_location = deno_loc

        if is_ffmpeg_available:
            self.ffmpeg_status_badge.configure(
                text=self._t("ffmpeg_ready"),
                fg_color=("#ECFDF5", "#064E3B"),
                text_color=("#059669", "#34D399")
            )
            self._append_log_message(f"{self._t('log_ffmpeg_found')} ({ffmpeg_loc})", "SUCCESS")
        else:
            self.ffmpeg_status_badge.configure(
                text=self._t("ffmpeg_missing"),
                fg_color=("#FEF2F2", "#7F1D1D"),
                text_color=("#DC2626", "#F87171")
            )

        if is_deno_available:
            self._append_log_message(f"{self._t('log_deno_active')} ({deno_loc})", "SUCCESS")

    def _show_ffmpeg_instruction_dialog(self) -> None:
        """Explains in simple human terms what FFmpeg is and why it is ready."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(self._t("dialog_ffmpeg_title"))
        dialog.geometry("640x440")
        dialog.minsize(580, 400)
        dialog.grab_set()

        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)

        title_lbl = ctk.CTkLabel(
            dialog,
            text=self._t("dialog_ffmpeg_header"),
            font=ctk.CTkFont(size=15, weight="bold")
        )
        title_lbl.grid(row=0, column=0, padx=20, pady=(18, 10), sticky="w")

        info_box = ctk.CTkTextbox(dialog, font=ctk.CTkFont(size=12), wrap="word")
        info_box.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")

        info_box.insert("1.0", self._t("dialog_ffmpeg_content"))
        info_box.configure(state="disabled")

        close_btn = ctk.CTkButton(
            dialog,
            text=self._t("btn_close"),
            width=140,
            height=34,
            command=dialog.destroy
        )
        close_btn.grid(row=2, column=0, padx=20, pady=(10, 18), sticky="e")

    # ------------------------------------------------------------------------
    # DOWNLOAD ORCHESTRATION AND THREAD DELEGATION
    # ------------------------------------------------------------------------

    def _validate_inputs(self) -> Optional[DownloadOptions]:
        raw_url: str = self.url_entry.get().strip()
        if not raw_url:
            messagebox.showwarning(
                self._t("msg_empty_url_title"),
                self._t("msg_empty_url_body")
            )
            self.url_entry.focus()
            return None

        parsed_url = urllib.parse.urlparse(raw_url)
        if not (parsed_url.scheme in ("http", "https") and parsed_url.netloc):
            messagebox.showwarning(
                self._t("msg_invalid_url_title"),
                self._t("msg_invalid_url_body")
            )
            self.url_entry.focus()
            return None

        output_dir: str = self.download_directory_var.get().strip()
        if not output_dir:
            output_dir = SystemDependencyChecker.get_default_download_directory()
            self.download_directory_var.set(output_dir)

        selected_format: str = self.audio_format_var.get().strip()
        raw_quality: str = self.audio_quality_var.get().strip()
        bitrate_kbps: str = "320"
        if "256" in raw_quality:
            bitrate_kbps = "256"
        elif "192" in raw_quality:
            bitrate_kbps = "192"
        elif "128" in raw_quality:
            bitrate_kbps = "128"

        return DownloadOptions(
            url=raw_url,
            output_directory=output_dir,
            audio_format=selected_format,
            audio_bitrate=bitrate_kbps,
            is_playlist=self.playlist_var.get(),
            embed_metadata=self.metadata_var.get(),
            embed_thumbnail=self.thumbnail_var.get(),
        )

    def _on_download_button_clicked(self) -> None:
        options: Optional[DownloadOptions] = self._validate_inputs()
        if not options:
            return

        if not self._ffmpeg_available:
            proceed = messagebox.askyesno(
                self._t("msg_ffmpeg_missing_title"),
                self._t("msg_ffmpeg_missing_body")
            )
            if not proceed:
                return

        start_index: int = 1
        if self.resumable_info and self.resumable_info.get("url") == options.url:
            start_index = self.resumable_info.get("next_index", 1)
            total = self.resumable_info.get("total_count", "?")
            self._append_log_message(
                self._t("log_resuming_from").format(index=start_index, total=total),
                "INFO"
            )
            self.resumable_info = None

        options = DownloadOptions(
            url=options.url,
            output_directory=options.output_directory,
            audio_format=options.audio_format,
            audio_bitrate=options.audio_bitrate,
            is_playlist=options.is_playlist,
            embed_metadata=options.embed_metadata,
            embed_thumbnail=options.embed_thumbnail,
            playlist_start_index=start_index,
        )

        self._set_ui_busy_state(True)
        self.progress_bar.set(0.0)
        self.speed_badge.configure(text=f"{self._t('speed_label')}--")
        self.eta_badge.configure(text=f"0.0%  |  {self._t('eta_label')}--:--")
        self.status_phase_label.configure(text=self._t("status_preparing"))

        self._active_worker = AudioDownloadWorker(
            options=options,
            ffmpeg_location=self._ffmpeg_location,
            deno_location=self._deno_location,
            on_progress=lambda r, s, e, f, p_idx, p_cnt: self.dispatch_to_ui(
                self._update_progress, r, s, e, f, p_idx, p_cnt
            ),
            on_phase_change=lambda phase: self.dispatch_to_ui(self._update_phase, phase),
            on_log=lambda msg, lvl: self.dispatch_to_ui(self._append_log_message, msg, lvl),
            on_complete=lambda ok, res, canc, f_idx, t_cnt, c_cnt: self.dispatch_to_ui(
                self._on_download_completed, ok, res, canc, f_idx, t_cnt, c_cnt
            ),
        )
        self._active_worker.start()

    def _on_cancel_button_clicked(self) -> None:
        if self._active_worker and self._active_worker.is_alive():
            self.cancel_button.configure(state="disabled", text=self._t("btn_stopping"))
            self.status_phase_label.configure(text=self._t("status_cancelled"))
            self._append_log_message("Запит на зупинку завантаження...", "WARNING")
            self._active_worker.request_cancellation()

    def _set_ui_busy_state(self, is_busy: bool) -> None:
        if is_busy:
            self.download_button.configure(state="disabled", text=self._t("btn_downloading"))
            self.cancel_button.configure(state="normal", text=self._t("btn_cancel"))
            self.url_entry.configure(state="disabled")
            self.format_segmented.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.playlist_switch.configure(state="disabled")
            self.metadata_switch.configure(state="disabled")
            self.thumbnail_switch.configure(state="disabled")
        else:
            if self.resumable_info:
                next_idx = self.resumable_info.get("next_index", 1)
                total = self.resumable_info.get("total_count", "?")
                self.download_button.configure(
                    state="normal",
                    text=f"{self._t('btn_resume')} ({next_idx}/{total})",
                    fg_color=("#059669", "#10B981"),
                    hover_color=("#047857", "#059669")
                )
            else:
                self.download_button.configure(
                    state="normal",
                    text=self._t("btn_download"),
                    fg_color=self.ACCENT_PRIMARY,
                    hover_color=self.ACCENT_HOVER
                )
            self.cancel_button.configure(state="disabled", text=self._t("btn_cancel"))
            self.url_entry.configure(state="normal")
            self.format_segmented.configure(state="normal")
            if self.audio_format_var.get().upper() not in ("FLAC", "WAV"):
                self.quality_menu.configure(state="normal")
            self.playlist_switch.configure(state="normal")
            self.metadata_switch.configure(state="normal")
            self.thumbnail_switch.configure(state="normal")

    def _update_progress(
        self,
        ratio: float,
        speed_text: str,
        eta_text: str,
        filename: str,
        playlist_index: Optional[int] = None,
        playlist_count: Optional[int] = None,
    ) -> None:
        self.progress_bar.set(ratio)
        percent_value: float = ratio * 100.0
        self.speed_badge.configure(text=f"{self._t('speed_label')}{speed_text}")
        self.eta_badge.configure(text=f"{percent_value:.1f}%  |  {self._t('eta_label')}{eta_text}")

        if playlist_index and playlist_count:
            badge_text = self._t("playlist_badge_format").format(index=playlist_index, total=playlist_count)
            self.playlist_badge.configure(
                text=badge_text,
                fg_color=("#EEF2FF", "#1E2235"),
                text_color=("#4F46E5", "#818CF8")
            )
        else:
            self.playlist_badge.configure(
                text=self._t("playlist_badge_single"),
                fg_color=("gray90", "#1E2235"),
                text_color=self.TEXT_SECONDARY
            )

        if filename:
            short_name = (filename[:36] + "...") if len(filename) > 38 else filename
            self.current_track_label.configure(
                text=f"{'Трек: ' if self.current_lang == 'UA' else 'Track: '}{short_name}"
            )

    def _update_phase(self, phase_description: str) -> None:
        self.status_phase_label.configure(text=f"Статус: {phase_description}")

    def _on_download_completed(
        self,
        is_success: bool,
        summary_message: str,
        was_cancelled: bool,
        failed_index: Optional[int] = None,
        total_count: Optional[int] = None,
        completed_count: int = 0
    ) -> None:
        self._active_worker = None

        if was_cancelled:
            self.status_phase_label.configure(text=self._t("status_cancelled"))
            self._set_ui_busy_state(False)
            messagebox.showinfo(self._t("status_cancelled"), self._t("status_cancelled"))
        elif is_success:
            self.resumable_info = None
            self.progress_bar.set(1.0)
            self.status_phase_label.configure(text=self._t("status_completed"))
            self.speed_badge.configure(text=f"{self._t('speed_label')}--")
            self.eta_badge.configure(text=f"100.0%  |  {self._t('eta_label')}00:00")
            if total_count and total_count > 1:
                self.playlist_badge.configure(
                    text=self._t("playlist_completed_summary").format(
                        completed=completed_count or total_count,
                        total=total_count
                    ),
                    fg_color=("#ECFDF5", "#064E3B"),
                    text_color=("#059669", "#34D399")
                )
            self._set_ui_busy_state(False)
            messagebox.showinfo(self._t("msg_success_title"), summary_message or self._t("msg_success_body"))
        else:
            if failed_index and total_count and (failed_index < total_count):
                next_track = failed_index + 1
                self.resumable_info = {
                    "url": self.url_entry.get().strip(),
                    "next_index": next_track,
                    "total_count": total_count,
                    "failed_index": failed_index,
                }
                resume_btn_text = f"{self._t('btn_resume')} ({next_track}/{total_count})"
                self.download_button.configure(
                    state="normal",
                    text=resume_btn_text,
                    fg_color=("#059669", "#10B981"),
                    hover_color=("#047857", "#059669"),
                )
                error_status = self._t("status_playlist_error").format(
                    index=failed_index,
                    total=total_count,
                    next_index=next_track
                )
                self.status_phase_label.configure(text=error_status)
                self.playlist_badge.configure(
                    text=f"{'Помилка: ' if self.current_lang == 'UA' else 'Error: '}{failed_index}/{total_count}",
                    fg_color=("#FEF2F2", "#7F1D1D"),
                    text_color=("#DC2626", "#F87171")
                )
                self._set_ui_busy_state(False)
                messagebox.showwarning(
                    self._t("msg_resume_title"),
                    self._t("msg_resume_body").format(
                        failed_index=failed_index,
                        total=total_count,
                        next_index=next_track
                    )
                )
            else:
                self.resumable_info = None
                self.status_phase_label.configure(text=self._t("status_error"))
                self._set_ui_busy_state(False)
                messagebox.showerror(self._t("status_error"), summary_message)


# ============================================================================
# APPLICATION ENTRYPOINT
# ============================================================================

def main() -> None:
    try:
        app = TrackPullApp()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as runtime_fatal_error:
        logging.critical(f"Fatal application startup exception: {runtime_fatal_error}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
