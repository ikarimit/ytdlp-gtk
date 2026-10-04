"""Window mixin: option widgets, settings, summary, about, behaviour."""
import json
import re
import shutil
import shlex
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, GLib, Gdk, Gtk  # noqa: E402

from .browsers import DEFAULT_DOMAINS, parse_domains
from .config import APP_NAME, AUTHOR, CREATED, GITHUB_URL, ICON, LOG_FILE, SETTINGS_FILE, VERSION, log
from .formatting import fmt_duration
from .options import AUDIO_FORMAT, AUDIO_QUALITY, EXTRA_OPTIONS, MODES, SUB_LANGS, SUB_NAMES, TITLE_TIPS, VIDEO_CONTAINER, VIDEO_RES
from .playlists import is_playlist
from .security import MAX_TEXT_FILE, validate_cmd, valid_url, write_private
from .tools import ytdlp
from .updater import installed_version
from .vault import runtime_dir


class CoreMixin:
    """Methods of the main window (core)."""

    def add_radios(self, box, group, options, default):
        first = None
        self.sel[group] = default
        if group == "subs":                 # multi-select flags
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6,
                               min_children_per_line=3, homogeneous=True)
            box.append(flow)
            for key, label, tip in options:
                cb = Gtk.CheckButton(label=label, tooltip_text=tip)
                cb.connect("toggled", self.on_sub_toggled, key)
                self.sub_buttons[key] = cb
                flow.insert(cb, -1)
            return
        add = box.append
        for key, label, tip in options:
            rb = Gtk.CheckButton(label=label, tooltip_text=tip)
            if first is None:
                first = rb
            else:
                rb.set_group(first)
            rb.set_active(key == default)
            rb.connect("toggled", self.on_radio, group, key)
            self.buttons[(group, key)] = rb
            add(rb)

    def make_tab(self, groups, columns=False):
        """One page of radio groups: stacked, or side by side (columns=True) to save height."""
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if columns else Gtk.Orientation.VERTICAL,
                       spacing=28 if columns else 6, width_request=250,
                       margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        for group, title, options, default in groups:
            holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.START) \
                if columns else page
            holder.append(Gtk.Label(label=title, xalign=0, css_classes=["heading"],
                                    tooltip_text=TITLE_TIPS.get(group)))
            self.add_radios(holder, group, options, default)
            if columns:
                page.append(holder)
            if group == "cookies":
                row = Gtk.Box(spacing=6)
                setup = Gtk.Button(label="Set up…", tooltip_text="Import or refresh cookies for the selected browser")
                setup.connect("clicked", lambda *_: self.show_cookie_setup(
                    preselect=self.sel["cookies"] if self.sel["cookies"] != "none" else None))
                forget = Gtk.Button(label="Forget", tooltip_text="Delete the saved cookies and stop using them")
                forget.connect("clicked", self.forget_cookies)
                row.append(setup)
                row.append(forget)
                page.append(row)
        return page

    def on_radio(self, btn, group, key):
        if btn.get_active():
            self.sel[group] = key
            if group == "cookies" and not self._loading and not self._cookie_quiet:
                if key == "none":
                    self.cookie_prev = "none"
                else:
                    self.show_cookie_setup(preselect=key)          # changing browser restarts setup
            log.debug("Option %s=%s", group, key)
            if group == "playlist" and not self._loading:     # playlist handling changes what a link is
                self.cache.clear()
                self.pl_url = None
                self.scan_urls()
            self.refresh_summary()
            self.save_settings()

    def on_sub_toggled(self, btn, key):
        if self._syncing:
            return
        self._syncing = True
        if btn.get_active():                # "all" and individual languages are exclusive
            for k, b in self.sub_buttons.items():
                if (key == "all") != (k == "all") and b.get_active():
                    b.set_active(False)
        self._syncing = False
        on = [c for c, _f, _n in SUB_LANGS if self.sub_buttons[c].get_active()]
        self.sel["subs"] = "all" if self.sub_buttons["all"].get_active() else ",".join(on) or "off"
        log.debug("Subtitles=%s", self.sel["subs"])
        self.refresh_summary()
        self.save_settings()

    def show_about(self, *_):
        version = installed_version(ytdlp()) or "not found"
        dialog = Adw.AboutDialog(
            application_name=APP_NAME, application_icon=ICON, version=VERSION,
            developer_name=AUTHOR, copyright=f"© 2026 {AUTHOR}",
            comments=("A simple GTK front-end for yt-dlp.\n\n"
                      f"Created: {CREATED}\n"
                      "GitHub: coming soon\n\n"
                      "Created with help from AI (Claude, by Anthropic)."),
            debug_info=f"{APP_NAME} {VERSION}\nyt-dlp {version} ({ytdlp()})\nGTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}, "
                       f"libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}\nDebug log: {LOG_FILE}",
            debug_info_filename="yt-dlp-gtk-info.txt")
        if GITHUB_URL:
            dialog.set_website(GITHUB_URL)
        dialog.present(self)

    @staticmethod
    def pretty(path):
        home = str(Path.home())
        return "~" + path[len(home):] if path.startswith(home) else path

    def rebuild_move_model(self):
        self._syncing_move = True
        items = ["Don't move"] + [self.pretty(p) for p in self.recent_moves] + ["Choose folder…"]
        self.move_model.splice(0, self.move_model.get_n_items(), items)
        self.move_drop.set_selected(1 + self.recent_moves.index(self.move_to) if self.move_to in self.recent_moves else 0)
        self._syncing_move = False

    def on_move_selected(self, drop, _p):
        if self._syncing_move:
            return
        idx = drop.get_selected()
        if idx == 0:
            self.move_to = ""
        elif idx == len(self.recent_moves) + 1:
            dialog = Gtk.FileDialog(title="Move finished files to…")

            def done(d, res):
                try:
                    path = d.select_folder_finish(res).get_path()
                except GLib.Error:
                    self.rebuild_move_model()          # cancelled: restore previous choice
                    return
                self.move_to = path
                self.recent_moves = ([path] + [p for p in self.recent_moves if p != path])[:5]
                self.rebuild_move_model()
                self.save_settings()

            dialog.select_folder(self, None, done)
            return
        else:
            self.move_to = self.recent_moves[idx - 1]
        log.info("Move finished files to: %r", self.move_to)
        self.save_settings()

    def toggle_fullscreen(self, *_):
        self.unfullscreen() if self.is_fullscreen() else self.fullscreen()

    def on_key(self, _c, keyval, *_):
        if keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        return False

    def on_signal(self):
        self.shutdown()
        self.get_application().quit()
        return GLib.SOURCE_REMOVE

    def shutdown(self):
        """Window closed (or SIGINT/SIGTERM): remember the queue as it is, stop the yt-dlp
        children; unfinished items resume on the next launch."""
        if self.closing:
            return
        self.save_settings()
        self.closing = True
        with self.lock:
            procs = [j.get("proc") for j in self.active.values()]
        for proc in procs:
            if proc:
                proc.terminate()
        log.info("Shutdown; %d running download(s) paused for next launch", len(procs))
        shutil.rmtree(runtime_dir(), ignore_errors=True)         # RAM scratch (cookie copies)

    def on_parallel(self, spin):
        self.max_parallel = int(spin.get_value())
        log.info("Simultaneous downloads: %d", self.max_parallel)
        self.save_settings()
        self.schedule()

    def schedule_save(self):
        """Debounced save for noisy events (column drags, typing)."""
        if self._loading:
            return
        if self._save_timer:
            GLib.source_remove(self._save_timer)
        self._save_timer = GLib.timeout_add(600, lambda: (self.save_settings(), False)[1])

    def save_settings(self):
        if self._loading:
            return
        if self._save_timer:
            GLib.source_remove(self._save_timer)
            self._save_timer = 0
        try:
            w, h = self.get_default_size()
            cols = [{"title": c.get_title(), "width": c.get_width()} for c in self.tv.get_columns()]
            queue = [{"title": r[0], "size": r[1], "progress": r[2], "status": r[3], "url": r[6],
                      "cmd": json.loads(r[7] or "[]"), "move_to": r[8], "path": r[9]} for r in self.store]
            write_private(SETTINGS_FILE, json.dumps({
                "sel": self.sel, "folder": str(self.folder),
                "thumb": self.thumb_check.get_active(), "size": [w, h],
                "urls": self.text(), "last_import": self.last_import,
                "columns": cols, "panes": self.pane_heights, "queue": queue,
                "cookies_asked": self.cookies_asked, "cookie_profiles": self.cookie_profiles,
                "cookie_domains": self.cookie_domains,
                "ytdlp_last_check": self.last_update_check, "parallel": self.max_parallel, "move_to": self.move_to, "recent_moves": self.recent_moves,
                "playlists": {u: {"off": sorted(v["off"]), "thumbs": sorted(v["thumbs"])}
                              for u, v in self.pl_state.items() if v["off"] or v["thumbs"]}}, indent=2))
        except Exception:
            log.exception("Saving settings failed")

    def load_settings(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text())
        except Exception:
            log.info("No saved settings (%s)", SETTINGS_FILE)
            return
        self._loading = True
        try:
            for group, key in data.get("sel", {}).items():
                if group == "subs":
                    for code in key.split(","):
                        if code in self.sub_buttons:
                            self.sub_buttons[code].set_active(True)
                    self.sel["subs"] = key if key == "off" or all(
                        c in self.sub_buttons for c in key.split(",")) else "off"
                elif (group, key) in self.buttons:
                    self.buttons[(group, key)].set_active(True)
            folder = data.get("folder")
            if isinstance(folder, str) and folder.startswith("/") and Path(folder).is_dir():
                self.folder = Path(folder)
            self.thumb_check.set_active(bool(data.get("thumb")))
            w, h = data.get("size", (900, 1000))
            self.set_default_size(int(w), int(h))
            self.url_buf.set_text(str(data.get("urls", ""))[:MAX_TEXT_FILE])
            self.last_import = data.get("last_import", "")
            self.cookies_asked = bool(data.get("cookies_asked", False))
            self.cookie_domains = parse_domains(" ".join(data.get("cookie_domains", []))) or list(DEFAULT_DOMAINS)
            self.last_update_check = float(data.get("ytdlp_last_check", 0) or 0)
            self.cookie_profiles = {k: v for k, v in data.get("cookie_profiles", {}).items() if isinstance(v, str)}
            self.pl_state = {u: {"off": set(v.get("off", [])) | set(v.get("removed", [])),
                                 "thumbs": set(v.get("thumbs", []))}
                             for u, v in data.get("playlists", {}).items()}
            self.recent_moves = [p for p in data.get("recent_moves", []) if isinstance(p, str)][:5]
            self.move_to = data.get("move_to", "") if data.get("move_to", "") in self.recent_moves else ""
            self.parallel_spin.set_value(max(1, min(8, int(data.get("parallel", 1)))))
            self.max_parallel = int(self.parallel_spin.get_value())
            for key, height in data.get("panes", {}).items():     # user-resized areas
                if key in self.panes:
                    self.pane_heights[key] = int(height)
                    self.panes[key].set_vexpand(False)
                    self.panes[key].set_size_request(-1, int(height))
            by_title = {c.get_title(): c for c in self.tv.get_columns()}
            prev = None
            for c in data.get("columns", []):                     # column order + widths
                col = by_title.get(c.get("title"))
                if col:
                    self.tv.move_column_after(col, prev)
                    prev = col
                    if col.get_title() != "Title" and c.get("width", 0) > 20:
                        col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                        col.set_fixed_width(max(int(c["width"]), col.get_min_width()))
            for q in data.get("queue", [])[:2000]:                # queue reappears
                cmd = q.get("cmd") if isinstance(q, dict) else None
                if isinstance(cmd, list) and cmd and "--" not in cmd:       # saved by an earlier version
                    q["cmd"] = cmd = cmd[:-1] + ["--", cmd[-1]]
                if isinstance(cmd, list):                                    # cookie files became vault entries
                    for i, tok in enumerate(cmd[:-1]):
                        m = tok == "--cookies" and re.fullmatch(r".*/cookies-([a-z]{2,10})\.txt", str(cmd[i + 1]))
                        if m:
                            cmd[i + 1] = f"vault:{m[1]}"
                if not (isinstance(q, dict) and valid_url(q.get("url")) and validate_cmd(q.get("cmd"))):
                    log.warning("Dropped a saved queue row that failed validation")
                    continue
                status = q.get("status", "Queued")
                if status not in ("Queued", "Downloading", "Processing", "Moving", "Done", "Failed", "Stopped"):
                    status = "Queued"
                if status in ("Downloading", "Processing", "Moving"):       # interrupted last time
                    status = "Queued"
                dest = q.get("move_to", "")
                self.store.append([str(q.get("title", ""))[:300], str(q.get("size", "—"))[:20],
                                   max(0, min(100, int(q.get("progress", 0)))), status, "", "",
                                   q["url"], json.dumps(q["cmd"]),
                                   dest if isinstance(dest, str) and dest.startswith("/") else "",
                                   q["path"] if isinstance(q.get("path"), str) and q["path"].startswith("/") else ""])
            log.info("Loaded settings from %s", SETTINGS_FILE)
        except Exception:
            log.exception("Loading settings failed")
        finally:
            self._loading = False

    @staticmethod
    def label_of(options, key):
        return next(l for k, l, _ in options if k == key)

    def changed_extras(self):
        out = []
        for key, title, options, default in EXTRA_OPTIONS:
            if self.sel[key] != default:
                shown = (", ".join(SUB_NAMES[c] for c in self.sel[key].split(",")) if key == "subs"
                         else self.label_of(options, self.sel[key]))
                out.append(f"{title.split(' (')[0]}: {shown}")
        return out

    def refresh_summary(self):
        s, i = self.sel, self.info or {}
        mode = s["mode"]
        vals = {
            "Title": i.get("title") or getattr(self, "fetch_note", None) or "—",
            "Uploader": i.get("uploader") or i.get("channel") or "—",
            "Duration": fmt_duration(i.get("duration")),
            "Mode": self.label_of(MODES, mode),
            "Audio": (f"{self.label_of(AUDIO_FORMAT, s['audio_format'])}, "
                      f"{self.label_of(AUDIO_QUALITY, s['audio_quality'])} quality"
                      if mode == "audio" else "best available" if mode == "both" else "not downloaded"),
            "Video": (f"{self.label_of(VIDEO_RES, s['video_res'])}, "
                      f"{self.label_of(VIDEO_CONTAINER, s['video_container'])} container"
                      if mode != "audio" else "not downloaded"),
            "Options": "; ".join(self.changed_extras()) or "defaults",
            "Thumbnail": "Yes (JPG)" if self.thumb_check.get_active() else "No",
            "Playlist": (f"{self.pl_counts()[0]} of {self.pl_counts()[1]} selected" if self.pl_url
                         else f"{len(self.info['entries'])} videos; turn on Whole playlist to choose"
                         if is_playlist(self.info) else "No"),
            "Command": self.command_text(),
        }
        fc = self.format_choice.get(self.current_url())
        if fc:                                  # a format picked in the Formats tab replaces the tab settings
            if mode == "audio":
                vals["Audio"] = f"format {fc['id']}, then converted as set in the Audio tab"
            else:
                vals["Video"] = f"format {fc['id']}" + ("" if fc["audio"] else " plus the best audio")
        for k, v in vals.items():
            self.summary[k].set_label(str(v))
        self.folder_label.set_text(str(self.folder))

    def command_text(self):
        """The yt-dlp command for the line under the cursor (progress-report flags hidden)."""
        url = self.current_url()
        hit = self.cache.get(url)
        target = "<each selected video>" if is_playlist(hit[0] if hit else None) else (url or "<URL>")
        out, skip = [], False
        for a in self.build_cmd(target):
            if skip:
                skip = False
            elif a == "--progress-template":
                skip = True
            elif a != "--newline":
                out.append("<saved cookies>" if a.startswith("vault:") else a)
        out[0] = "yt-dlp"
        return " ".join(shlex.quote(a) for a in out)
