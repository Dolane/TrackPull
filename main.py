"""
TrackPull - Modern Music & Playlist Downloader for Windows.

This application provides a graphical interface built with CustomTkinter
for downloading high-quality audio tracks and playlists using yt-dlp.
All processing runs asynchronously in background worker threads to keep
the user interface fluid, ultra-fast, and responsive.

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


class SystemDependencyChecker:
    """
    Utility class for inspecting, discovering, and configuring external binaries
    (FFmpeg, FFprobe, Deno JS runtime) for accelerated extraction and conversion.
    """

    @staticmethod
    def get_application_root() -> str:
        """
        Determines the base application root directory.
        Handles both standard Python execution and PyInstaller frozen executable contexts.
        """
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def initialize_runtime_environment(cls) -> None:
        """
        Prepend local application bin directory and WinGet package folders to PATH.
        Ensures yt-dlp automatically detects FFmpeg and Deno without system restarts.
        """
        base_dir: str = cls.get_application_root()
        candidate_paths: List[str] = [
            os.path.join(base_dir, "bin"),
            base_dir,
        ]

        # Scan user WinGet package directories for installed FFmpeg and Deno
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
                            # Also search one level deeper for bin subfolders
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
        """
        Locates the FFmpeg binary in system PATH or local application directories.

        Returns:
            tuple[bool, str]: (is_available, executable_path_or_empty_string)
        """
        # 1. Inspect current PATH (which now includes runtime-injected paths)
        system_path: Optional[str] = shutil.which("ffmpeg")
        if system_path:
            return True, system_path

        # 2. Inspect application directory and local ./bin directory explicitly
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
        """
        Locates the Deno JavaScript runtime binary for accelerated YouTube signature solving.

        Returns:
            tuple[bool, str]: (is_available, executable_path_or_empty_string)
        """
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
        """
        Determines the most appropriate default destination directory on Windows.
        Prioritizes the user's standard Music folder, falling back to Downloads or Home.
        """
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
    """
    Custom logger redirecting yt-dlp internal messages to thread-safe
    callbacks for real-time visualization in the user interface.
    """

    def __init__(self, dispatch_log: Callable[[str, str], None]) -> None:
        """
        Initialize the logger.

        Args:
            dispatch_log: Thread-safe callable accepting (message: str, level: str).
        """
        self._dispatch_log: Callable[[str, str], None] = dispatch_log

    def debug(self, message: str) -> None:
        """Handle debug messages, filtering out repetitive percentage lines."""
        clean_msg: str = message.strip()
        if not clean_msg:
            return

        # Suppress noisy percentage lines handled by the animated progress bar
        if "[download]" in clean_msg and "%" in clean_msg:
            return

        # Suppress redundant postprocessor notices handled by postprocessor hook
        if clean_msg.startswith(("[ExtractAudio] Destination:", "[Metadata] Adding metadata", "[Thumbnails]")):
            self._dispatch_log(clean_msg, "INFO")
        elif clean_msg.startswith("[download] Destination:"):
            dest_name = clean_msg.replace("[download] Destination:", "").strip()
            self._dispatch_log(f"Завантаження файлу: {os.path.basename(dest_name)}", "INFO")

    def info(self, message: str) -> None:
        """Handle standard informational messages."""
        clean_msg: str = message.strip()
        if clean_msg and not ("%" in clean_msg and "[download]" in clean_msg):
            self._dispatch_log(clean_msg, "INFO")

    def warning(self, message: str) -> None:
        """Handle non-fatal warning messages."""
        clean_msg: str = message.strip()
        if clean_msg:
            # Clean up JS runtime warning if deno is active or suppress harmless deprecations
            if "No supported JavaScript runtime could be found" in clean_msg:
                self._dispatch_log(
                    "Попередження: Відсутній рушій JavaScript (Deno/Node). "
                    "Встановлення Deno прискорює аналіз плейлистів.",
                    "WARNING"
                )
            else:
                self._dispatch_log(f"Увага: {clean_msg}", "WARNING")

    def error(self, message: str) -> None:
        """Handle fatal error messages."""
        clean_msg: str = message.strip()
        if clean_msg:
            self._dispatch_log(f"Помилка: {clean_msg}", "ERROR")


# ============================================================================
# ASYNCHRONOUS DOWNLOAD WORKER
# ============================================================================

class AudioDownloadWorker(threading.Thread):
    """
    Dedicated worker thread responsible for executing yt-dlp operations
    with parallel fragment streaming and hardware-optimized postprocessing.
    """

    def __init__(
        self,
        options: DownloadOptions,
        ffmpeg_location: str,
        deno_location: str,
        on_progress: Callable[[float, str, str, str, Optional[int], Optional[int]], None],
        on_phase_change: Callable[[str], None],
        on_log: Callable[[str, str], None],
        on_complete: Callable[[bool, str, bool], None],
    ) -> None:
        """Initialize worker thread with performance configurations."""
        super().__init__(name="AudioDownloadWorkerThread", daemon=True)
        self.options: DownloadOptions = options
        self.ffmpeg_location: str = ffmpeg_location
        self.deno_location: str = deno_location
        self.on_progress: Callable[[float, str, str, str, Optional[int], Optional[int]], None] = on_progress
        self.on_phase_change: Callable[[str], None] = on_phase_change
        self.on_log: Callable[[str, str], None] = on_log
        self.on_complete: Callable[[bool, str, bool], None] = on_complete

        self._cancellation_requested: threading.Event = threading.Event()
        self._logged_postprocessors: Set[str] = set()

    def request_cancellation(self) -> None:
        """Signals the worker to abort active downloads cleanly."""
        self._cancellation_requested.set()

    def _progress_hook(self, payload: Dict[str, Any]) -> None:
        """Internal hook invoked periodically by yt-dlp during media transmission."""
        if self._cancellation_requested.is_set():
            raise yt_dlp.utils.DownloadCancelled("Завантаження зупинено користувачем.")

        status: Optional[str] = payload.get("status")

        if status == "downloading":
            downloaded_bytes: int = payload.get("downloaded_bytes") or 0
            total_bytes: Optional[int] = payload.get("total_bytes") or payload.get("total_bytes_estimate")
            speed: Optional[float] = payload.get("speed")
            eta_seconds: Optional[int] = payload.get("eta")
            filename: str = os.path.basename(payload.get("filename", ""))

            playlist_index: Optional[int] = payload.get("playlist_index")
            playlist_count: Optional[int] = payload.get("n_entries") or payload.get("playlist_count")

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

            self.on_progress(ratio, speed_text, eta_text, filename, playlist_index, playlist_count)

        elif status == "finished":
            filename = os.path.basename(payload.get("filename", ""))
            self.on_phase_change(f"Аудіопотік отримано ({filename}). Конвертація...")

    def _postprocessor_hook(self, payload: Dict[str, Any]) -> None:
        """Hook triggered during FFmpeg conversion and tag/thumbnail embedding."""
        if self._cancellation_requested.is_set():
            raise yt_dlp.utils.DownloadCancelled("Завантаження зупинено користувачем.")

        status: Optional[str] = payload.get("status")
        pp_name: str = payload.get("postprocessor", "PostProcessor")

        if status == "started":
            if pp_name == "ExtractAudio":
                self.on_phase_change("Конвертація аудіо (FFmpeg)...")
            elif pp_name == "EmbedThumbnail":
                self.on_phase_change("Вбудовування обкладинки...")
            elif pp_name == "Metadata":
                self.on_phase_change("Запис ID3-тегів...")
            else:
                self.on_phase_change(f"Обробка: {pp_name}...")
        elif status == "finished":
            # Avoid duplicate log outputs per track
            item_key = f"{pp_name}_{payload.get('info_dict', {}).get('id', '')}"
            if item_key not in self._logged_postprocessors:
                self._logged_postprocessors.add(item_key)
                if pp_name == "ExtractAudio":
                    self.on_log("Конвертацію аудіо у вибраний формат завершено.", "INFO")
                elif pp_name == "EmbedThumbnail":
                    self.on_log("Обкладинку треку успішно вбудовано.", "INFO")
                elif pp_name == "Metadata":
                    self.on_log("Метадані треку успішно записано.", "INFO")

    def run(self) -> None:
        """Main execution loop for downloading and converting media."""
        self.on_log(f"Початок аналізу URL: {self.options.url}", "INFO")
        self.on_phase_change("Отримання списку треків та аудіопотоків...")

        try:
            os.makedirs(self.options.output_directory, exist_ok=True)
        except OSError as folder_err:
            error_message = f"Не вдалося створити робочу папку: {folder_err}"
            self.on_log(error_message, "ERROR")
            self.on_complete(False, error_message, False)
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

        # High-performance yt-dlp configurations
        ydl_opts: Dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "noplaylist": not self.options.is_playlist,
            "ignoreerrors": self.options.is_playlist,
            # Acceleration options:
            "concurrent_fragment_downloads": 8,  # Download DASH/HLS segments in 8 parallel streams
            "buffersize": 1024 * 64,             # 64 KB network stream buffer
            "http_chunk_size": 10485760,         # 10 MB chunk size for maximum throughput
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],  # Use fast direct streams, avoiding throttling
                    "skip": ["translated_subs"],
                }
            },
            "postprocessors": postprocessors,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "logger": YTDLPMessageLogger(self.on_log),
            "quiet": False,
            "no_warnings": False,
            "updatetime": False,
        }

        if self.options.embed_thumbnail:
            ydl_opts["writethumbnail"] = True

        if self.ffmpeg_location:
            ydl_opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_location)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                exit_code: int = ydl.download([self.options.url])
                if exit_code == 0:
                    success_msg: str = "Усі аудіотреки успішно завантажено та збережено!"
                    self.on_log(success_msg, "SUCCESS")
                    self.on_complete(True, success_msg, False)
                else:
                    partial_msg: str = f"Завантаження завершилося з кодом {exit_code}."
                    self.on_log(partial_msg, "WARNING")
                    self.on_complete(True, partial_msg, False)

        except yt_dlp.utils.DownloadCancelled:
            cancel_msg: str = "Завантаження зупинено користувачем."
            self.on_log(cancel_msg, "WARNING")
            self.on_complete(False, cancel_msg, True)

        except yt_dlp.utils.DownloadError as download_err:
            raw_err: str = str(download_err)
            if "ffmpeg" in raw_err.lower():
                friendly_err: str = (
                    "Помилка FFmpeg: Не знайдено FFmpeg для конвертації аудіо або запису тегів. "
                    "Будь ласка, встановіть FFmpeg."
                )
            elif "unsupported url" in raw_err.lower():
                friendly_err = "Непідтримуване або некоректне URL-посилання на трек чи плейлист."
            elif "private video" in raw_err.lower() or "sign in" in raw_err.lower():
                friendly_err = "Цей трек або плейлист є приватним чи вимагає авторизації в акаунті."
            else:
                friendly_err = f"Помилка завантаження yt-dlp: {raw_err}"

            self.on_log(friendly_err, "ERROR")
            self.on_complete(False, friendly_err, False)

        except Exception as unexpected_err:
            error_msg: str = f"Непередбачена помилка виконання: {unexpected_err}"
            self.on_log(error_msg, "ERROR")
            self.on_complete(False, error_msg, False)


# ============================================================================
# MAIN APPLICATION INTERFACE
# ============================================================================

class TrackPullApp(ctk.CTk):
    """
    Main application window implementing an adaptive, centered grid architecture.
    Provides instant resize performance and symmetrical aesthetics in all screen modes.
    """

    APP_TITLE: str = "TrackPull"
    APP_VERSION: str = "1.1.0"
    DEFAULT_WINDOW_SIZE: str = "760x840"
    MIN_WINDOW_WIDTH: int = 720
    MIN_WINDOW_HEIGHT: int = 760

    FORMAT_OPTIONS: List[str] = ["MP3", "M4A", "FLAC", "WAV"]
    BITRATE_MAPPING: Dict[str, str] = {
        "320 kbps (Найвища якість)": "320",
        "256 kbps (Висока якість)": "256",
        "192 kbps (Середня якість)": "192",
        "128 kbps (Стандартна якість)": "128",
    }

    def __init__(self) -> None:
        """Initialize the primary application state and graphical components."""
        # Prepend binaries to PATH before launching any engine
        SystemDependencyChecker.initialize_runtime_environment()

        super().__init__()

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title(f"{self.APP_TITLE} v{self.APP_VERSION} — Завантажувач музики")
        self.geometry(self.DEFAULT_WINDOW_SIZE)
        self.minsize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)

        self.download_directory_var: ctk.StringVar = ctk.StringVar(
            value=SystemDependencyChecker.get_default_download_directory()
        )
        self.audio_format_var: ctk.StringVar = ctk.StringVar(value="MP3")
        self.audio_quality_var: ctk.StringVar = ctk.StringVar(
            value="320 kbps (Найвища якість)"
        )
        self.playlist_var: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self.metadata_var: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self.thumbnail_var: ctk.BooleanVar = ctk.BooleanVar(value=True)

        self._active_worker: Optional[AudioDownloadWorker] = None
        self._ffmpeg_available: bool = False
        self._ffmpeg_location: str = ""
        self._deno_available: bool = False
        self._deno_location: str = ""

        # Configure application icon for window titlebar and taskbar
        self._set_application_icon()

        # Construct UI layout with centered responsive frame
        self._build_interface()

        # Check external dependencies after initial render
        self.after(200, self._evaluate_system_dependencies)

    # ------------------------------------------------------------------------
    # THREAD-SAFE UI DISPATCHERS
    # ------------------------------------------------------------------------

    def dispatch_to_ui(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Safely schedules a function execution onto the main Tkinter UI thread."""
        self.after(0, lambda: function(*args, **kwargs))

    def _set_application_icon(self) -> None:
        """Configures the titlebar and taskbar icon for Windows."""
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
        except Exception as icon_err:
            logging.debug(f"Non-critical: could not load window icon: {icon_err}")

    # ------------------------------------------------------------------------
    # UI CONSTRUCTION METHODS (OPTIMIZED NON-SCROLLABLE NATIVE GRID)
    # ------------------------------------------------------------------------

    def _build_interface(self) -> None:
        """
        Builds the graphical interface using a 3-column centered architecture.
        Guarantees instant resizing between windowed and fullscreen with zero lag.
        """
        # Outer root grid: Columns 0 & 2 are flexible spacers; Column 1 houses content
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=10, minsize=700)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Main content card centered horizontally and expanding vertically
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)

        # Configure container rows
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(6, weight=1)  # Log console row expands

        # 1. Header Section
        self._create_header_frame(self.main_container)

        # 2. Dependency Warning Banner (Hidden by default, displayed if FFmpeg missing)
        self._create_dependency_banner(self.main_container)

        # 3. URL Input Card
        self._create_url_card(self.main_container)

        # 4. Parameters Card (Format, Quality, Metadata, Playlist)
        self._create_parameters_card(self.main_container)

        # 5. Output Directory Card
        self._create_directory_card(self.main_container)

        # 6. Action and Progress Card
        self._create_action_progress_card(self.main_container)

        # 7. Log Console Card (Expands cleanly on fullscreen)
        self._create_console_card(self.main_container)

    def _create_header_frame(self, parent: ctk.CTkBaseClass) -> None:
        """Constructs the application header with branding and theme switcher."""
        header_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray90", "gray14"))
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=0, ipady=4)
        header_frame.grid_columnconfigure(0, weight=1)
        header_frame.grid_columnconfigure(1, weight=0)

        branding_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        branding_box.grid(row=0, column=0, sticky="w", padx=16, pady=6)

        # Display custom minimalist icon if available
        base_dir = SystemDependencyChecker.get_application_root()
        meipass_dir = getattr(sys, "_MEIPASS", base_dir)
        for img_dir in (base_dir, meipass_dir):
            icon_png_path = os.path.join(img_dir, "assets", "icon.png")
            if os.path.isfile(icon_png_path):
                try:
                    from PIL import Image
                    pil_icon = Image.open(icon_png_path)
                    self._header_logo = ctk.CTkImage(
                        light_image=pil_icon,
                        dark_image=pil_icon,
                        size=(38, 38)
                    )
                    logo_label = ctk.CTkLabel(branding_box, image=self._header_logo, text="")
                    logo_label.pack(side="left", padx=(0, 10))
                    break
                except Exception:
                    pass

        titles_box = ctk.CTkFrame(branding_box, fg_color="transparent")
        titles_box.pack(side="left")

        app_title = ctk.CTkLabel(
            titles_box,
            text="TrackPull",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=("gray10", "#4da6ff")
        )
        app_title.pack(anchor="w")

        app_subtitle = ctk.CTkLabel(
            titles_box,
            text="Швидкий та надійний завантажувач аудіотреків і плейлистів",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray40", "gray70")
        )
        app_subtitle.pack(anchor="w")

        theme_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        theme_box.grid(row=0, column=1, sticky="e", padx=16, pady=6)

        theme_label = ctk.CTkLabel(
            theme_box,
            text="Тема:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        theme_label.pack(side="left", padx=(0, 8))

        self.theme_menu = ctk.CTkOptionMenu(
            theme_box,
            values=["Темна", "Світла", "Системна"],
            command=self._on_theme_changed,
            width=110,
            height=28
        )
        self.theme_menu.set("Темна")
        self.theme_menu.pack(side="left")

    def _create_dependency_banner(self, parent: ctk.CTkBaseClass) -> None:
        """Constructs a dismissible alert banner displayed when FFmpeg is not found."""
        self.dependency_banner = ctk.CTkFrame(
            parent,
            corner_radius=10,
            fg_color=("#fff3cd", "#332701"),
            border_width=1,
            border_color=("#ffeeba", "#664d03")
        )
        self.dependency_banner.grid_columnconfigure(1, weight=1)

        warning_icon = ctk.CTkLabel(
            self.dependency_banner,
            text="⚠️",
            font=ctk.CTkFont(size=20)
        )
        warning_icon.grid(row=0, column=0, padx=(14, 8), pady=8, sticky="w")

        self.dependency_text = ctk.CTkLabel(
            self.dependency_banner,
            text=(
                "Увага: FFmpeg не знайдено в системі! Для конвертації у MP3/FLAC, "
                "запису ID3-тегів та вбудовування обкладинок потрібен FFmpeg."
            ),
            font=ctk.CTkFont(size=12),
            text_color=("#856404", "#ffda6a"),
            justify="left"
        )
        self.dependency_text.grid(row=0, column=1, padx=4, pady=8, sticky="ew")

        btn_box = ctk.CTkFrame(self.dependency_banner, fg_color="transparent")
        btn_box.grid(row=0, column=2, padx=(8, 14), pady=8, sticky="e")

        help_btn = ctk.CTkButton(
            btn_box,
            text="Як встановити?",
            width=110,
            height=28,
            fg_color=("#d39e00", "#ffc107"),
            text_color=("black", "black"),
            hover_color=("#b58500", "#e0a800"),
            command=self._show_ffmpeg_instruction_dialog
        )
        help_btn.pack(side="left", padx=4)

        recheck_btn = ctk.CTkButton(
            btn_box,
            text="Перевірити",
            width=90,
            height=28,
            fg_color=("gray60", "gray30"),
            command=self._evaluate_system_dependencies
        )
        recheck_btn.pack(side="left", padx=4)

    def _create_url_card(self, parent: ctk.CTkBaseClass) -> None:
        """Constructs the URL input card with clipboard and clear action buttons."""
        url_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray95", "gray17"))
        url_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10), padx=0)
        url_frame.grid_columnconfigure(0, weight=1)

        card_title = ctk.CTkLabel(
            url_frame,
            text="🔗 Посилання на аудіотрек або плейлист:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        card_title.grid(row=0, column=0, sticky="w", padx=16, pady=(10, 6))

        input_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        input_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        input_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Вставте URL з YouTube, SoundCloud, YouTube Music...",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        paste_button = ctk.CTkButton(
            input_row,
            text="📋 Вставити",
            width=95,
            height=38,
            command=self._paste_clipboard_url
        )
        paste_button.grid(row=0, column=1, padx=(0, 6))

        clear_button = ctk.CTkButton(
            input_row,
            text="✖ Очистити",
            width=85,
            height=38,
            fg_color=("gray60", "gray28"),
            hover_color=("gray50", "gray38"),
            command=self._clear_url_entry
        )
        clear_button.grid(row=0, column=2)

    def _create_parameters_card(self, parent: ctk.CTkBaseClass) -> None:
        """Constructs the format, bitrate, and post-processing flags configuration card."""
        params_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray95", "gray17"))
        params_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10), padx=0)
        params_frame.grid_columnconfigure(0, weight=1)
        params_frame.grid_columnconfigure(1, weight=1)

        card_title = ctk.CTkLabel(
            params_frame,
            text="⚙️ Параметри конвертації та завантаження:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        card_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(10, 8))

        # Left Column: Format & Bitrate
        left_col = ctk.CTkFrame(params_frame, fg_color="transparent")
        left_col.grid(row=1, column=0, sticky="nsew", padx=(16, 12), pady=(0, 12))

        format_label = ctk.CTkLabel(
            left_col,
            text="Аудіоформат:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        format_label.pack(anchor="w", pady=(0, 4))

        self.format_menu = ctk.CTkOptionMenu(
            left_col,
            values=self.FORMAT_OPTIONS,
            variable=self.audio_format_var,
            command=self._on_format_changed,
            height=32
        )
        self.format_menu.pack(fill="x", pady=(0, 8))

        self.quality_label = ctk.CTkLabel(
            left_col,
            text="Бітрейт (швидкість потоку):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.quality_label.pack(anchor="w", pady=(0, 4))

        self.quality_menu = ctk.CTkOptionMenu(
            left_col,
            values=list(self.BITRATE_MAPPING.keys()),
            variable=self.audio_quality_var,
            height=32
        )
        self.quality_menu.pack(fill="x")

        # Right Column: Flags & Options
        right_col = ctk.CTkFrame(params_frame, fg_color="transparent")
        right_col.grid(row=1, column=1, sticky="nsew", padx=(12, 16), pady=(0, 12))

        options_label = ctk.CTkLabel(
            right_col,
            text="Додаткові опції:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        options_label.pack(anchor="w", pady=(0, 6))

        self.playlist_checkbox = ctk.CTkCheckBox(
            right_col,
            text="Завантажити весь плейлист",
            variable=self.playlist_var,
            font=ctk.CTkFont(size=12)
        )
        self.playlist_checkbox.pack(anchor="w", pady=4)

        self.metadata_checkbox = ctk.CTkCheckBox(
            right_col,
            text="Вбудувати метадані (виконавець, назва)",
            variable=self.metadata_var,
            font=ctk.CTkFont(size=12)
        )
        self.metadata_checkbox.pack(anchor="w", pady=4)

        self.thumbnail_checkbox = ctk.CTkCheckBox(
            right_col,
            text="Вбудувати обкладинку (cover art)",
            variable=self.thumbnail_var,
            font=ctk.CTkFont(size=12)
        )
        self.thumbnail_checkbox.pack(anchor="w", pady=4)

    def _create_directory_card(self, parent: ctk.CTkBaseClass) -> None:
        """Constructs the output destination directory selection card."""
        dir_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray95", "gray17"))
        dir_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10), padx=0)
        dir_frame.grid_columnconfigure(0, weight=1)

        card_title = ctk.CTkLabel(
            dir_frame,
            text="📁 Папка для збереження треків:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        card_title.grid(row=0, column=0, sticky="w", padx=16, pady=(10, 6))

        dir_row = ctk.CTkFrame(dir_frame, fg_color="transparent")
        dir_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        dir_row.grid_columnconfigure(0, weight=1)

        self.dir_entry = ctk.CTkEntry(
            dir_row,
            textvariable=self.download_directory_var,
            height=36,
            font=ctk.CTkFont(size=12)
        )
        self.dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        browse_btn = ctk.CTkButton(
            dir_row,
            text="📂 Огляд...",
            width=95,
            height=36,
            command=self._browse_directory
        )
        browse_btn.grid(row=0, column=1, padx=(0, 6))

        open_btn = ctk.CTkButton(
            dir_row,
            text="↗ Відкрити",
            width=90,
            height=36,
            fg_color=("gray60", "gray28"),
            hover_color=("gray50", "gray38"),
            command=self._open_directory_in_explorer
        )
        open_btn.grid(row=0, column=2)

    def _create_action_progress_card(self, parent: ctk.CTkBaseClass) -> None:
        """Constructs the primary action trigger button, progress bar, and real-time statistics."""
        action_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray95", "gray17"))
        action_frame.grid(row=5, column=0, sticky="ew", pady=(0, 10), padx=0)
        action_frame.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        btn_row.grid_columnconfigure(0, weight=4)
        btn_row.grid_columnconfigure(1, weight=1)

        self.download_button = ctk.CTkButton(
            btn_row,
            text="⬇ ЗАВАНТАЖИТИ МУЗИКУ",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            corner_radius=8,
            fg_color=("#1f6aa5", "#2979ff"),
            hover_color=("#144d75", "#1c54b2"),
            command=self._on_download_button_clicked
        )
        self.download_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.cancel_button = ctk.CTkButton(
            btn_row,
            text="Зупинити",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=44,
            corner_radius=8,
            fg_color=("firebrick2", "#c62828"),
            hover_color=("firebrick3", "#8e0000"),
            state="disabled",
            command=self._on_cancel_button_clicked
        )
        self.cancel_button.grid(row=0, column=1, sticky="ew")

        # Smooth Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            action_frame,
            height=14,
            corner_radius=7
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        self.progress_bar.set(0.0)

        stats_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        stats_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        stats_frame.grid_columnconfigure(0, weight=2)
        stats_frame.grid_columnconfigure(1, weight=1)

        self.status_phase_label = ctk.CTkLabel(
            stats_frame,
            text="Статус: Готовий до роботи",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.status_phase_label.grid(row=0, column=0, sticky="w")

        self.metrics_label = ctk.CTkLabel(
            stats_frame,
            text="Швидкість: -- | Залишилось: -- | 0.0%",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
            anchor="e"
        )
        self.metrics_label.grid(row=0, column=1, sticky="e")

    def _create_console_card(self, parent: ctk.CTkBaseClass) -> None:
        """Constructs the expandable activity console for detailed operational logs."""
        console_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray95", "gray17"))
        console_frame.grid(row=6, column=0, sticky="nsew", pady=(0, 0), padx=0)
        console_frame.grid_columnconfigure(0, weight=1)
        console_frame.grid_rowconfigure(1, weight=1)

        header_box = ctk.CTkFrame(console_frame, fg_color="transparent")
        header_box.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 4))
        header_box.grid_columnconfigure(0, weight=1)

        console_title = ctk.CTkLabel(
            header_box,
            text="📋 Детальний журнал подій:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        console_title.grid(row=0, column=0, sticky="w")

        clear_log_btn = ctk.CTkButton(
            header_box,
            text="Очистити журнал",
            width=110,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color=("gray65", "gray28"),
            hover_color=("gray50", "gray38"),
            command=self._clear_console_log
        )
        clear_log_btn.grid(row=0, column=1, sticky="e")

        self.console_textbox = ctk.CTkTextbox(
            console_frame,
            height=130,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
            activate_scrollbars=True
        )
        self.console_textbox.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))

        self._append_log_message(
            f"=== TrackPull v{self.APP_VERSION} успішно запущено. Готовий до роботи. ===",
            "INFO"
        )

    # ------------------------------------------------------------------------
    # EVENT HANDLERS AND LOGIC
    # ------------------------------------------------------------------------

    def _on_theme_changed(self, selected_theme: str) -> None:
        """Handles appearance theme alterations (Dark, Light, System)."""
        mapping: Dict[str, str] = {
            "Темна": "Dark",
            "Світла": "Light",
            "Системна": "System",
        }
        target_mode: str = mapping.get(selected_theme, "Dark")
        ctk.set_appearance_mode(target_mode)

    def _on_format_changed(self, selected_format: str) -> None:
        """Dynamically adapts bitrate options based on whether codec is lossy or lossless."""
        if selected_format.upper() in ("FLAC", "WAV"):
            self.quality_menu.configure(state="disabled")
            self.quality_label.configure(
                text="Бітрейт: Авто (Без втрат якості / Lossless)"
            )
        else:
            self.quality_menu.configure(state="normal")
            self.quality_label.configure(text="Бітрейт (швидкість потоку):")

    def _paste_clipboard_url(self) -> None:
        """Pastes the textual contents of the Windows clipboard into the URL field."""
        try:
            content: str = self.clipboard_get().strip()
            if content:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, content)
                self._append_log_message(f"Вставлено посилання: {content}", "INFO")
        except Exception as clip_err:
            self._append_log_message(f"Не вдалося зчитати буфер обміну: {clip_err}", "WARNING")

    def _clear_url_entry(self) -> None:
        """Clears the URL entry field."""
        self.url_entry.delete(0, "end")

    def _browse_directory(self) -> None:
        """Opens a Windows native folder selection dialog."""
        selected: str = filedialog.askdirectory(
            initialdir=self.download_directory_var.get(),
            title="Оберіть папку для збереження аудіотреків"
        )
        if selected:
            self.download_directory_var.set(selected)
            self._append_log_message(f"Папку для збереження змінено: {selected}", "INFO")

    def _open_directory_in_explorer(self) -> None:
        """Reveals the chosen download destination directory in Windows File Explorer."""
        folder_path: str = self.download_directory_var.get()
        if os.path.isdir(folder_path):
            try:
                os.startfile(folder_path)
            except Exception as explorer_err:
                self._append_log_message(
                    f"Не вдалося відкрити папку в Explorer: {explorer_err}",
                    "ERROR"
                )
        else:
            messagebox.showwarning(
                "Папка не існує",
                f"Вказана папка не знайдена на диску:\n{folder_path}\n\nСтворіть її або виберіть іншу."
            )

    def _clear_console_log(self) -> None:
        """Clears all text within the activity console box."""
        self.console_textbox.delete("1.0", "end")

    def _append_log_message(self, message: str, level: str = "INFO") -> None:
        """Appends a timestamped message into the read-only console textbox."""
        import datetime
        timestamp: str = datetime.datetime.now().strftime("%H:%M:%S")
        prefix: str = {
            "INFO": "[INFO]",
            "WARNING": "[УВАГА]",
            "ERROR": "[ПОМИЛКА]",
            "SUCCESS": "[УСПІХ]",
        }.get(level, "[LOG]")

        formatted: str = f"[{timestamp}] {prefix} {message}\n"
        self.console_textbox.insert("end", formatted)
        self.console_textbox.see("end")

    # ------------------------------------------------------------------------
    # DEPENDENCY EVALUATION AND INSTRUCTION MODAL
    # ------------------------------------------------------------------------

    def _evaluate_system_dependencies(self) -> None:
        """Inspects whether FFmpeg and Deno are available and toggles UI alerts."""
        is_ffmpeg_available, ffmpeg_loc = SystemDependencyChecker.locate_ffmpeg()
        self._ffmpeg_available = is_ffmpeg_available
        self._ffmpeg_location = ffmpeg_loc

        is_deno_available, deno_loc = SystemDependencyChecker.locate_deno()
        self._deno_available = is_deno_available
        self._deno_location = deno_loc

        if is_ffmpeg_available:
            self.dependency_banner.grid_remove()
            self._append_log_message(f"FFmpeg готовий: {ffmpeg_loc}", "SUCCESS")
        else:
            self.dependency_banner.grid(
                row=1, column=0, sticky="ew", pady=(0, 10), padx=0
            )
            self._append_log_message(
                "FFmpeg не знайдено в системі. Потрібне встановлення для повного функціоналу.",
                "WARNING"
            )

        if is_deno_available:
            self._append_log_message(f"JavaScript runtime (Deno) активний: {deno_loc}", "SUCCESS")

    def _show_ffmpeg_instruction_dialog(self) -> None:
        """Displays an informative modal dialog explaining how to easily install FFmpeg on Windows."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Встановлення FFmpeg на Windows")
        dialog.geometry("620x460")
        dialog.minsize(580, 420)
        dialog.grab_set()

        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)

        title_lbl = ctk.CTkLabel(
            dialog,
            text="🛠 Як встановити FFmpeg для TrackPull:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_lbl.grid(row=0, column=0, padx=20, pady=(18, 10), sticky="w")

        info_box = ctk.CTkTextbox(
            dialog,
            font=ctk.CTkFont(size=12),
            wrap="word"
        )
        info_box.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")

        instructions: str = (
            "FFmpeg — це обов'язковий системний інструмент для перекодування аудіо (у формати MP3, "
            "FLAC, WAV тощо), а також для збереження обкладинок треків та ID3-тегів.\n\n"
            "Виберіть один із простих способів встановлення:\n\n"
            "Спосіб 1: Через Windows Terminal / PowerShell (Швидко й просто):\n"
            "1. Натисніть правою кнопкою миші на меню 'Пуск' та відкрийте 'Термінал' або 'PowerShell'.\n"
            "2. Введіть команду:\n"
            "       winget install Gyan.FFmpeg\n"
            "3. Дочекайтеся завершення завантаження та перезапустіть TrackPull.\n\n"
            "Спосіб 2: Портативний варіант (Без встановлення в систему):\n"
            "1. Завантажте архів FFmpeg з офіційного сайту: https://www.gyan.dev/ffmpeg/builds/\n"
            "2. Розпакуйте файл 'ffmpeg.exe' безпосередньо у папку з програмою TrackPull (або у папку bin/).\n"
            "3. Натисніть кнопку 'Перевірити' у верхньому банері головного вікна.\n\n"
            "Спосіб 3: Через пакетний менеджер Chocolatey:\n"
            "       choco install ffmpeg\n"
        )
        info_box.insert("1.0", instructions)
        info_box.configure(state="disabled")

        close_btn = ctk.CTkButton(
            dialog,
            text="Зрозуміло, закрити",
            width=140,
            height=34,
            command=dialog.destroy
        )
        close_btn.grid(row=2, column=0, padx=20, pady=(10, 18), sticky="e")

    # ------------------------------------------------------------------------
    # DOWNLOAD ORCHESTRATION AND THREAD DELEGATION
    # ------------------------------------------------------------------------

    def _validate_inputs(self) -> Optional[DownloadOptions]:
        """Validates the user's configured fields before starting download."""
        raw_url: str = self.url_entry.get().strip()
        if not raw_url:
            messagebox.showwarning(
                "Порожнє посилання",
                "Будь ласка, вставте URL-посилання на аудіотрек або плейлист у поле вводу."
            )
            self.url_entry.focus()
            return None

        parsed_url = urllib.parse.urlparse(raw_url)
        if not (parsed_url.scheme in ("http", "https") and parsed_url.netloc):
            messagebox.showwarning(
                "Некоректний URL",
                "Введене посилання має неправильний формат. Переконайтеся, що воно починається з http:// або https://"
            )
            self.url_entry.focus()
            return None

        output_dir: str = self.download_directory_var.get().strip()
        if not output_dir:
            output_dir = SystemDependencyChecker.get_default_download_directory()
            self.download_directory_var.set(output_dir)

        selected_format: str = self.audio_format_var.get().strip()
        raw_quality: str = self.audio_quality_var.get().strip()
        bitrate_kbps: str = self.BITRATE_MAPPING.get(raw_quality, "320")

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
        """Triggered when the user presses the primary 'ЗАВАНТАЖИТИ' button."""
        options: Optional[DownloadOptions] = self._validate_inputs()
        if not options:
            return

        if not self._ffmpeg_available:
            proceed = messagebox.askyesno(
                "FFmpeg відсутній",
                "FFmpeg не знайдено в системі. Завантаження вихідного потоку можливе, проте конвертація у "
                f"{options.audio_format} та вбудовування тегів/обкладинок вимагають наявності FFmpeg.\n\n"
                "Бажаєте продовжити без FFmpeg?"
            )
            if not proceed:
                return

        self._set_ui_busy_state(True)
        self.progress_bar.set(0.0)
        self.metrics_label.configure(text="Швидкість: -- | Залишилось: -- | 0.0%")
        self.status_phase_label.configure(text="Статус: Підготовка до завантаження...")

        self._active_worker = AudioDownloadWorker(
            options=options,
            ffmpeg_location=self._ffmpeg_location,
            deno_location=self._deno_location,
            on_progress=lambda r, s, e, f, p_idx, p_cnt: self.dispatch_to_ui(
                self._update_progress, r, s, e, f, p_idx, p_cnt
            ),
            on_phase_change=lambda phase: self.dispatch_to_ui(self._update_phase, phase),
            on_log=lambda msg, lvl: self.dispatch_to_ui(self._append_log_message, msg, lvl),
            on_complete=lambda ok, res, canc: self.dispatch_to_ui(self._on_download_completed, ok, res, canc),
        )
        self._active_worker.start()

    def _on_cancel_button_clicked(self) -> None:
        """Signals active worker thread to safely cancel current job."""
        if self._active_worker and self._active_worker.is_alive():
            self.cancel_button.configure(state="disabled", text="Зупинка...")
            self.status_phase_label.configure(text="Статус: Скасування операції...")
            self._append_log_message("Користувач надіслав запит на зупинку завантаження...", "WARNING")
            self._active_worker.request_cancellation()

    def _set_ui_busy_state(self, is_busy: bool) -> None:
        """Toggles interactive controls between active and busy states."""
        if is_busy:
            self.download_button.configure(state="disabled", text="⏳ ЗАВАНТАЖЕННЯ...")
            self.cancel_button.configure(state="normal", text="Зупинити")
            self.url_entry.configure(state="disabled")
            self.format_menu.configure(state="disabled")
            self.quality_menu.configure(state="disabled")
            self.playlist_checkbox.configure(state="disabled")
            self.metadata_checkbox.configure(state="disabled")
            self.thumbnail_checkbox.configure(state="disabled")
        else:
            self.download_button.configure(state="normal", text="⬇ ЗАВАНТАЖИТИ МУЗИКУ")
            self.cancel_button.configure(state="disabled", text="Зупинити")
            self.url_entry.configure(state="normal")
            self.format_menu.configure(state="normal")
            if self.audio_format_var.get().upper() not in ("FLAC", "WAV"):
                self.quality_menu.configure(state="normal")
            self.playlist_checkbox.configure(state="normal")
            self.metadata_checkbox.configure(state="normal")
            self.thumbnail_checkbox.configure(state="normal")

    # ------------------------------------------------------------------------
    # ASYNCHRONOUS UPDATE RECEIVERS (RUN ON MAIN UI THREAD)
    # ------------------------------------------------------------------------

    def _update_progress(
        self,
        ratio: float,
        speed_text: str,
        eta_text: str,
        filename: str,
        playlist_index: Optional[int] = None,
        playlist_count: Optional[int] = None,
    ) -> None:
        """Receives and renders progress metrics onto the user interface."""
        self.progress_bar.set(ratio)
        percent_value: float = ratio * 100.0
        self.metrics_label.configure(
            text=f"Швидкість: {speed_text} | Залишилось: {eta_text} | {percent_value:.1f}%"
        )
        if filename:
            short_name = (filename[:32] + "...") if len(filename) > 35 else filename
            if playlist_index and playlist_count:
                self.status_phase_label.configure(
                    text=f"Трек [{playlist_index}/{playlist_count}]: {short_name}"
                )
            else:
                self.status_phase_label.configure(text=f"Завантаження: {short_name}")

    def _update_phase(self, phase_description: str) -> None:
        """Updates the descriptive phase label."""
        self.status_phase_label.configure(text=f"Статус: {phase_description}")

    def _on_download_completed(self, is_success: bool, summary_message: str, was_cancelled: bool) -> None:
        """Finalizes the job execution, restores UI, and notifies the user."""
        self._set_ui_busy_state(False)
        self._active_worker = None

        if was_cancelled:
            self.status_phase_label.configure(text="Статус: ⏸ Завантаження зупинено")
            messagebox.showinfo(
                "Операцію зупинено",
                "Завантаження було успішно зупинено користувачем."
            )
        elif is_success:
            self.progress_bar.set(1.0)
            self.status_phase_label.configure(text="Статус: ✅ Завантаження успішно завершено!")
            self.metrics_label.configure(text="Швидкість: -- | Залишилось: 00:00 | 100.0%")
            messagebox.showinfo(
                "Успіх",
                "Аудіотрек або плейлист успішно збережено у вибрану папку!"
            )
        else:
            self.status_phase_label.configure(text="Статус: ❌ Сталася помилка")
            messagebox.showerror(
                "Помилка завантаження",
                f"Не вдалося завершити завантаження:\n\n{summary_message}"
            )


# ============================================================================
# APPLICATION ENTRYPOINT
# ============================================================================

def main() -> None:
    """Configures high-DPI scaling and initializes the application event loop."""
    try:
        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        app = TrackPullApp()
        app.mainloop()

    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as runtime_fatal_error:
        logging.critical(f"Fatal application startup exception: {runtime_fatal_error}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
