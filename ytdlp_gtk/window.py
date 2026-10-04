"""The main window: builds the interface from the mixins."""
import signal
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, GLib, Gdk, Gio, Gtk, Pango  # noqa: E402

from .config import ICON, LOG_FILE, log
from .browsers import DEFAULT_DOMAINS
from .options import AUDIO_FORMAT, AUDIO_QUALITY, EXTRA_OPTIONS, MODES, VIDEO_CONTAINER, VIDEO_RES
from .tools import ytdlp
from .vault import Vault
from .widgets import autoscroll, resize_handle, style_scrollbars, titled
from .win_cookies import CookieMixin
from .win_core import CoreMixin
from .win_logs import LogMixin
from .win_queue import QueueMixin
from .win_updates import UpdateMixin
from .win_urls import UrlMixin

CSS = (".logscroll scrollbar.vertical { min-width: 14px; background-color: alpha(currentColor, 0.10); } "
       ".logscroll scrollbar.vertical slider { min-width: 9px; min-height: 44px; border-radius: 8px; "
       "background-color: alpha(currentColor, 0.60); } "
       ".logscroll scrollbar.vertical slider:hover { background-color: alpha(currentColor, 0.85); }")


def dim_label(text):
    return Gtk.Label(label=text, xalign=1, css_classes=["dim-label"])


class Window(CoreMixin, UrlMixin, QueueMixin, CookieMixin, LogMixin, UpdateMixin, Adw.ApplicationWindow):
    """The main window."""

    def __init__(self, app):
        super().__init__(application=app, title="yt-dlp GTK", default_width=900, default_height=1000)
        self._setup_theme()
        self._init_state()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        root.append(self._build_urls())
        root.append(self._build_settings())
        root.append(self._build_download_controls())
        root.append(self._build_tabs())
        root.append(self._build_bottom_bar())

        view = Adw.ToolbarView()
        view.add_top_bar(self._build_header())
        view.set_content(Gtk.ScrolledWindow(child=root, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                            vscrollbar_policy=Gtk.PolicyType.ALWAYS))   # keeps the scrollbar inside the minimum width
        self.toasts = Adw.ToastOverlay(child=view)
        self.set_content(self.toasts)
        self._wire_window()
        self._finish_startup()

    # --- setup ------------------------------------------------------------------------
    def _setup_theme(self):
        css = Gtk.CssProvider()
        try:
            css.load_from_string(CSS)
        except AttributeError:
            css.load_from_data(CSS.encode())
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.IconTheme.get_for_display(display).add_search_path(str(Path(__file__).resolve().parent.parent / "icons"))
        Gtk.Window.set_default_icon_name(ICON)
        self.set_icon_name(ICON)

    def _init_state(self):
        self.info = None                   # metadata of the selected URL
        self.sel = {}                      # group name -> selected key
        self.folder = Path.home() / "Downloads"
        self.fetch_slots = threading.Semaphore(3)
        self.cache = {}                    # url -> (info, texture) or None on failure
        self.inflight = set()
        self._debounce = 0
        self.sub_buttons = {}
        self.panes, self.pane_heights = {}, {}
        self._save_timer = 0
        self.last_import = ""
        self.buttons = {}                  # (group, key) -> radio button
        self._syncing = self._loading = False
        self.jobs, self.active = [], {}      # waiting jobs; id(job) -> running job
        self.max_parallel, self.closing = 1, False
        self.batch = {"done": 0, "failed": 0, "last": ""}
        self.alerts, self.alert_open = [], False
        self.cookie_dialog, self.cookies_asked, self.cookie_profiles = None, False, {}
        self.vault, self.vault_keys, self.cookie_domains = Vault(), set(), list(DEFAULT_DOMAINS)
        self._spec_cache = {}                 # browser -> `chromium:/profile` (probing the disk is not free)
        self.cookie_prev, self._cookie_quiet, self._cookie_ok = "none", False, False
        self.fetch_errors, self.cred_prompted = {}, set()
        self._dbg_size, self._dbg_timer = -1, 0
        self.format_choice, self.fmt_url = {}, None       # url -> specific format picked in the Formats tab
        self.update_dialog, self.last_update_check = None, 0.0
        self.move_to, self.recent_moves, self._syncing_move = "", [], False
        self.pl_url, self.pl_state, self.pl_checks = None, {}, []
        self.pl_pics, self.thumb_cache, self.thumb_requested = {}, {}, set()
        self.pl_thumb_checks, self.thumbs_active = {}, False
        self.lock = threading.Lock()

    # --- top row: URLs and the playlist window ----------------------------------------------
    def _build_urls(self):
        self.url_view = Gtk.TextView(monospace=True, wrap_mode=Gtk.WrapMode.NONE, top_margin=4,
                                     bottom_margin=4, left_margin=6, right_margin=6,
                                     tooltip_text="One URL per line. Just type or paste; press Enter for the next line.")
        self.url_buf = self.url_view.get_buffer()
        self.url_buf.connect("changed", self.on_urls_changed)
        self.url_buf.connect("notify::cursor-position", lambda *_: self.show_current())
        url_scroll = Gtk.ScrolledWindow(child=self.url_view, min_content_height=70, vexpand=True,
                                        css_classes=["card"])
        btns = Gtk.Box(spacing=8)
        imp = Gtk.Button(label="Import from file…", icon_name="document-open-symbolic",
                         tooltip_text="Load URLs from a text file (one per line; # lines are ignored)")
        imp.connect("clicked", self.import_file)
        clear = Gtk.Button(label="Clear all", tooltip_text="Remove every URL")
        clear.connect("clicked", self.clear_urls)
        for b in (imp, clear):
            btns.append(b)
        url_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        url_box.append(url_scroll)
        url_box.append(resize_handle(self, url_scroll, "urls"))
        url_box.append(btns)
        self.url_frame = titled("Video URLs", url_box,
                                "One URL per line. The details of the line your cursor is on appear in the "
                                "Metadata tab. You can also drop a text file of URLs anywhere on this window.")
        self.url_frame.set_hexpand(True)

        # playlist window: always there; a hint until Whole playlist is on and the cursor is on a playlist link
        self.pl_head = Gtk.Label(xalign=0, ellipsize=3, hexpand=True)
        all_b = Gtk.Button(label="All", css_classes=["flat"], tooltip_text="Tick every video")
        none_b = Gtk.Button(label="None", css_classes=["flat"], tooltip_text="Untick every video")
        all_b.connect("clicked", lambda *_: self.pl_select(True))
        none_b.connect("clicked", lambda *_: self.pl_select(False))
        pl_top = Gtk.Box(spacing=4)
        for w in (self.pl_head, all_b, none_b):
            pl_top.append(w)
        self.pl_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        pl_scroll = Gtk.ScrolledWindow(child=self.pl_list, min_content_height=70, vexpand=True,
                                       hscrollbar_policy=Gtk.PolicyType.NEVER, css_classes=["card"])
        pl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pl_box.append(pl_top)
        pl_box.append(pl_scroll)
        self.pl_hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, vexpand=True,
                                 css_classes=["dim-label"], margin_start=12, margin_end=12)
        self.pl_stack = Gtk.Stack(vexpand=True)
        self.pl_stack.add_named(self.pl_hint, "hint")
        self.pl_stack.add_named(pl_box, "list")
        self.pl_frame = titled("Playlist", self.pl_stack,
                               "Only ticked videos are downloaded. Turn on Whole playlist "
                               "(Options tab, Playlists) to view a playlist in this window.")
        self.pl_frame.set_size_request(360, -1)
        row = Gtk.Box(spacing=12)
        row.append(self.url_frame)
        row.append(self.pl_frame)
        return row

    # --- settings notebook + thumbnails ----------------------------------------------------------
    def _build_settings(self):
        middle = Gtk.Box(spacing=12)
        notebook = self.settings_nb = Gtk.Notebook(valign=Gtk.Align.START)
        notebook.append_page(self.make_tab([
            ("audio_format", "Format", AUDIO_FORMAT, "best"),
            ("audio_quality", "Quality", AUDIO_QUALITY, "0"),
        ], columns=True), Gtk.Label(label="Audio"))
        notebook.append_page(self.make_tab([
            ("video_res", "Resolution", VIDEO_RES, "best"),
            ("video_container", "Container", VIDEO_CONTAINER, "best"),
        ], columns=True), Gtk.Label(label="Video"))
        notebook.append_page(self.build_formats_page(), Gtk.Label(label="Formats"))
        extra = self.make_tab([(k, t, o, d) for k, t, o, d in EXTRA_OPTIONS])
        notebook.append_page(Gtk.ScrolledWindow(child=extra, min_content_height=260,
                                                hscrollbar_policy=Gtk.PolicyType.NEVER),
                             Gtk.Label(label="Options"))
        middle.append(titled("Settings", notebook))

        thumb_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        self.thumb = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, height_request=120, vexpand=True,
                                 css_classes=["card"])
        self.thumb_check = Gtk.CheckButton(label="Download thumbnail")
        self.thumb_check.set_tooltip_text("Also save the video's thumbnail as a JPG next to the download.")
        self.thumb_check.connect("toggled", lambda *_: (self.refresh_summary(), self.save_settings()))
        thumb_col.append(self.thumb)
        thumb_col.append(self.thumb_check)
        thumb_nb = Gtk.Notebook(hexpand=True, valign=Gtk.Align.START)
        thumb_nb.append_page(thumb_col, Gtk.Label(label="Thumbnail"))
        thumb_nb.append_page(self.build_thumbs_page(),
                             Gtk.Label(label="Playlist", tooltip_text="Thumbnails of the videos in a playlist"))
        thumb_nb.connect("switch-page", self.on_thumb_tab)
        middle.append(titled("Thumbnails", thumb_nb))
        return middle

    # --- type, folder and move-to in one compact block -----------------------------------------------
    def _build_download_controls(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        mode_box = Gtk.Box(spacing=16)
        self.add_radios(mode_box, "mode", MODES, "both")
        grid.attach(dim_label("Type"), 0, 0, 1, 1)
        grid.attach(mode_box, 1, 0, 1, 1)

        self.folder_label = Gtk.Entry(editable=False, hexpand=True)
        folder_btn = Gtk.Button(icon_name="folder-open-symbolic", tooltip_text="Choose download folder")
        folder_btn.connect("clicked", self.choose_folder)
        folder_box = Gtk.Box(spacing=8)
        folder_box.append(self.folder_label)
        folder_box.append(folder_btn)
        grid.attach(dim_label("Folder"), 0, 1, 1, 1)
        grid.attach(folder_box, 1, 1, 1, 1)

        self.move_model = Gtk.StringList()
        self.move_drop = Gtk.DropDown(model=self.move_model, hexpand=True,
                                      tooltip_text="After a download completes, its files are moved to this "
                                                   "folder. Your last 5 choices are remembered.")
        self.move_drop.connect("notify::selected", self.on_move_selected)
        grid.attach(dim_label("Move to"), 0, 2, 1, 1)
        grid.attach(self.move_drop, 1, 2, 1, 1)
        return titled("Download", grid)

    # --- tabs: Metadata | Queue | Logs | Debug ---------------------------------------------------------
    def _build_tabs(self):
        self.tabs = Gtk.Notebook(vexpand=True)
        self.tabs.append_page(self._build_metadata_tab(), Gtk.Label(label="Metadata"))
        self.tabs.append_page(self._build_queue_tab(), Gtk.Label(label="Queue"))
        self.tabs.append_page(self._build_logs_tab(), Gtk.Label(label="Logs"))
        self.tabs.append_page(self._build_debug_tab(), Gtk.Label(label="Debug"))
        self.tabs.connect("switch-page", self.on_log_tab)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.tabs)
        box.append(resize_handle(self, self.tabs, "tabs"))
        return box

    def _build_metadata_tab(self):
        self.summary = {}
        grid = Gtk.Grid(column_spacing=12, row_spacing=3, margin_top=8, margin_bottom=8,
                        margin_start=10, margin_end=10)
        for i, key in enumerate(["Title", "Uploader", "Duration", "Playlist", "Mode", "Audio", "Video",
                                 "Options", "Thumbnail", "Command"]):
            k = Gtk.Label(label=key, xalign=1, yalign=0, css_classes=["dim-label"])
            if key == "Command":
                k.set_tooltip_text("The yt-dlp command used for each video. Flags the app adds only to "
                                   "report progress are hidden.")
            v = Gtk.Label(label="—", xalign=0, hexpand=True, wrap=True, selectable=True,
                          wrap_mode=Pango.WrapMode.WORD_CHAR)
            if key == "Command":
                v.add_css_class("monospace")
            grid.attach(k, 0, i, 1, 1)
            grid.attach(v, 1, i, 1, 1)
            self.summary[key] = v
        return Gtk.ScrolledWindow(child=grid, min_content_height=150, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _build_queue_tab(self):
        self.store = Gtk.ListStore(str, str, int, str, str, str, str, str, str, str)   # + url, cmd (json), move_to, file path
        tv = self.tv = Gtk.TreeView(model=self.store, reorderable=False)
        tv.set_tooltip_text("Double-click a finished row to open its file. Select rows and press Delete to remove them.")
        tv.connect("columns-changed", lambda *_: self.schedule_save())
        tv.connect("row-activated", self.on_row_activated)
        tv.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, keyval, *_a: (self.remove_selected(), True)[1]
                     if keyval == Gdk.KEY_Delete else False)
        tv.add_controller(keys)
        for i, name in enumerate(["Title", "Size", "Progress", "Status", "Speed", "ETA"]):
            if name == "Progress":
                col = Gtk.TreeViewColumn(name, Gtk.CellRendererProgress(), value=2)
                col.set_min_width(110)
            else:
                cell = Gtk.CellRendererText(ellipsize=3)
                col = Gtk.TreeViewColumn(name, cell, text=i)
                col.set_min_width({"Size": 80, "Status": 90, "Speed": 90, "ETA": 70}.get(name, 60))
                if name == "Title":
                    col.set_expand(True)
                    col.set_min_width(180)
            col.set_resizable(True)
            col.set_reorderable(True)
            col.connect("notify::width", lambda *_: self.schedule_save())
            tv.append_column(col)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6,
                      margin_start=8, margin_end=8)
        box.append(Gtk.ScrolledWindow(child=tv, min_content_height=140, vexpand=True))
        buttons = Gtk.Box(spacing=8)
        start = Gtk.Button(label="Start", tooltip_text="Run everything still waiting in the queue")
        start.connect("clicked", self.start_queue)
        stop = Gtk.Button(label="Stop", tooltip_text="Stop the current download and drop queued items")
        stop.connect("clicked", self.stop_queue)
        menu = Gio.Menu()
        for label, name in (("Completed", "clear-done"), ("Failed", "clear-failed"), ("Stopped", "clear-stopped")):
            menu.append(label, f"win.{name}")
        for name, statuses in (("clear-done", ("Done",)), ("clear-failed", ("Failed",)),
                               ("clear-stopped", ("Stopped",))):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_a, st=statuses: self.clear_status(st))
            self.add_action(action)
        clear = Gtk.MenuButton(label="Clear", menu_model=menu,
                               tooltip_text="Remove every completed, failed or stopped row from the queue")
        for b in (start, stop, clear):
            buttons.append(b)
        par_tip = ("How many videos download at the same time. yt-dlp has no fixed limit; what really caps it "
                   "is your internet speed (parallel downloads share it), your CPU and disk (ffmpeg merging), "
                   "and the site itself, which may throttle or block you when many requests come at once. "
                   "2 to 4 is a good range.")
        buttons.append(Gtk.Label(label="Simultaneous downloads", hexpand=True, halign=Gtk.Align.END,
                                 tooltip_text=par_tip))
        self.parallel_spin = Gtk.SpinButton.new_with_range(1, 8, 1)
        self.parallel_spin.set_tooltip_text(par_tip)
        self.parallel_spin.connect("value-changed", self.on_parallel)
        buttons.append(self.parallel_spin)
        box.append(buttons)
        return box

    def _log_view(self, tag_attr, view_attr):
        view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        setattr(self, view_attr, view)
        setattr(self, tag_attr, view.get_buffer().create_tag("bad", foreground="#e5484d"))
        scroll = Gtk.ScrolledWindow(child=view, min_content_height=110, vexpand=True, css_classes=["logscroll"],
                                    hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    vscrollbar_policy=Gtk.PolicyType.ALWAYS, overlay_scrolling=False)
        return scroll, autoscroll(scroll)

    def _log_page(self, scroll, debug):
        export = Gtk.Button(icon_name="document-save-symbolic", css_classes=["flat"], halign=Gtk.Align.END,
                            tooltip_text="Export this log to a text file")
        export.connect("clicked", lambda *_: self.export_log(debug=debug))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(scroll)
        box.append(export)
        return box

    def _build_logs_tab(self):
        scroll, self.log_follow = self._log_view("bad_tag", "log_view")
        return self._log_page(scroll, False)

    def _build_debug_tab(self):
        scroll, self.dbg_follow = self._log_view("dbg_bad", "dbg_view")
        return self._log_page(scroll, True)

    # --- header and bottom bar -----------------------------------------------------------------------
    def _build_header(self):
        header = Adw.HeaderBar()
        update = Gtk.Button(icon_name="software-update-available-symbolic",
                            tooltip_text="Check for a newer yt-dlp and install it")
        update.connect("clicked", self.show_update_dialog)
        header.pack_end(update)
        return header

    def _build_bottom_bar(self):
        self.button = Gtk.Button(label="Download", css_classes=["suggested-action", "pill"],
                                 halign=Gtk.Align.CENTER)
        self.button.connect("clicked", self.on_download)
        about = Gtk.Button(icon_name="dialog-information-symbolic", css_classes=["flat", "circular"],
                           halign=Gtk.Align.END, tooltip_text="About")
        about.connect("clicked", self.show_about)
        return Gtk.CenterBox(center_widget=self.button, end_widget=about)

    # --- window-level wiring and start-up ---------------------------------------------------------------
    def _wire_window(self):
        file_drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        file_drop.connect("drop", self.on_file_drop)
        self.add_controller(file_drop)
        text_drop = Gtk.DropTarget.new(str, Gdk.DragAction.COPY)
        text_drop.connect("drop", self.on_text_drop)
        self.add_controller(text_drop)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self.on_key)
        self.add_controller(key)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self.on_signal)
        self.connect("close-request", lambda *_: (self.shutdown(), False)[1])

    def _finish_startup(self):
        self.load_settings()
        self.refresh_vault_keys()
        self.rebuild_move_model()
        self.refresh_summary()
        self.cookie_prev = self.sel["cookies"]
        style_scrollbars(self.get_content())
        if not Path(ytdlp()).is_absolute():
            self.enqueue_alert("yt-dlp not found",
                               "This app needs yt-dlp to download.\n\nInstall it with:\n"
                               "sudo apt install yt-dlp\n\nthen restart the app.", [("close", "Close", True)],
                               lambda _r: None)
        self.show_current()
        GLib.idle_add(lambda: (self.start_queue(stopped=False), False)[1])      # resume interrupted work
        GLib.timeout_add(8000, self.check_updates_quietly)                      # at most once a day
        if not self.cookies_asked:                # first launch: offer the cookie setup
            GLib.timeout_add(900, lambda: (self.show_cookie_setup(first=True), False)[1])
        log.info("Window ready; log at %s", LOG_FILE)
