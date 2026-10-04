"""Window mixin: URL box, metadata fetching, playlist and thumbnail windows."""
import json
import subprocess
import threading
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gio, Gtk  # noqa: E402

from .config import log
from .errors import explain_error, needs_credentials
from .formats import COLUMNS, WIDTHS, format_rows
from .playlists import entry_thumb, entry_url, is_playlist, new_state
from .security import MAX_PLAYLIST_ENTRIES, MAX_TEXT_FILE, read_limited, valid_url
from .tools import child_env, download_image, js_runtime_args, ytdlp


class UrlMixin:
    """Methods of the main window (urls)."""

    def build_thumbs_page(self):
        self.thumbs_head = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        all_b = Gtk.Button(label="All", css_classes=["flat"], tooltip_text="Download the thumbnail of every listed video")
        none_b = Gtk.Button(label="None", css_classes=["flat"], tooltip_text="Download no thumbnails from this playlist")
        all_b.connect("clicked", lambda *_: self.thumbs_select(True))
        none_b.connect("clicked", lambda *_: self.thumbs_select(False))
        top = Gtk.Box(spacing=4)
        for w in (self.thumbs_head, all_b, none_b):
            top.append(w)
        self.thumb_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                      min_children_per_line=2, max_children_per_line=8,
                                      valign=Gtk.Align.START, row_spacing=6, column_spacing=6)
        self.thumb_flow.set_filter_func(
            lambda child: child.get_child().get_name() not in
            self.pl_state.get(self.pl_url, new_state())["off"])
        scroll = Gtk.ScrolledWindow(child=self.thumb_flow, min_content_height=190, vexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER, css_classes=["card"])
        grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        grid.append(top)
        grid.append(scroll)
        self.thumbs_hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, vexpand=True,
                                     css_classes=["dim-label"], margin_start=12, margin_end=12)
        self.thumbs_stack = Gtk.Stack(vexpand=True)
        self.thumbs_stack.add_named(self.thumbs_hint, "hint")
        self.thumbs_stack.add_named(grid, "grid")
        return self.thumbs_stack

    def on_thumb_tab(self, _nb, _page, num):
        self.thumbs_active = num == 1
        if self.thumbs_active:
            GLib.idle_add(self.load_pl_thumbs)

    def pl_entries(self, url=None):
        hit = self.cache.get(url or self.pl_url)
        info = hit[0] if hit else None
        return [{"url": entry_url(e), "title": e.get("title") or entry_url(e), "thumb": entry_thumb(e)}
                for e in (info or {}).get("entries", [])[:MAX_PLAYLIST_ENTRIES] if e and entry_url(e)]

    def pl_counts(self):
        off = self.pl_state.get(self.pl_url, new_state())["off"]
        urls = [e["url"] for e in self.pl_entries()]
        return sum(1 for u in urls if u not in off), len(urls)

    def pl_update_head(self):
        sel, total = self.pl_counts()
        hit = self.cache.get(self.pl_url)
        name = ((hit[0] if hit else None) or {}).get("title") or "Playlist"
        self.pl_head.set_label(f"{name} · {sel} of {total} selected")
        self.pl_head.set_tooltip_text(self.pl_head.get_label())
        st = self.pl_state.get(self.pl_url, new_state())
        n = len(st["thumbs"] - st["off"])
        self.thumbs_head.set_label(f"{n} thumbnail{'' if n == 1 else 's'} selected")
        self.thumb_flow.invalidate_filter()       # unticked videos disappear from the thumbnail grid
        self.refresh_summary()
        self.schedule_save()

    def show_playlist(self, url, info):
        whole_mode = self.sel["playlist"] == "all"
        if whole_mode and url and is_playlist(info):
            self.pl_stack.set_visible_child_name("list")
            self.thumbs_stack.set_visible_child_name("grid")
            if self.pl_url == url:
                return
            self.pl_url = url
            self.rebuild_playlist(url)
            return
        self.pl_url = None
        if is_playlist(info):
            hint = (f"This link is a playlist of {len(info['entries'])} videos; all of them will download.\n\n"
                    "Turn on Whole playlist (Options tab, Playlists) to choose which ones.")
        elif not whole_mode:
            hint = ("Turn on Whole playlist (Options tab, Playlists) to view a playlist here "
                    "and choose which videos to download.")
        else:
            hint = "Put the cursor on a playlist link to see its videos here."
        self.pl_hint.set_label(hint)
        self.thumbs_hint.set_label(hint)
        self.pl_stack.set_visible_child_name("hint")
        self.thumbs_stack.set_visible_child_name("hint")

    def rebuild_playlist(self, url):
        for box in (self.pl_list, self.thumb_flow):
            child = box.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                box.remove(child)
                child = nxt
        self.pl_checks, self.pl_pics, self.pl_thumb_checks = [], {}, {}
        st = self.pl_state.setdefault(url, new_state())
        for e in self.pl_entries(url):
            eurl, title = e["url"], e["title"]
            chk = Gtk.CheckButton(active=eurl not in st["off"], hexpand=True, margin_top=2, margin_bottom=2,
                                  margin_start=6, tooltip_text=f"{title}\n{eurl}")
            chk.set_child(Gtk.Label(label=title, xalign=0, ellipsize=3))
            chk.connect("toggled", self.pl_toggled, eurl)
            self.pl_checks.append(chk)
            self.pl_list.append(chk)
            # thumbnail grid item
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, width_request=150)
            item.set_name(eurl)
            pic = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, height_request=84, width_request=150,
                              can_shrink=True, css_classes=["card"], tooltip_text=title)
            tchk = Gtk.CheckButton(active=eurl in st["thumbs"])
            tchk.set_child(Gtk.Label(label=title, xalign=0, ellipsize=3, max_width_chars=16))
            tchk.connect("toggled", self.thumb_toggled, eurl)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, c=tchk: c.set_active(not c.get_active()))
            pic.add_controller(click)
            item.append(pic)
            item.append(tchk)
            self.thumb_flow.append(item)
            self.pl_pics[eurl] = (pic, e["thumb"])
            self.pl_thumb_checks[eurl] = tchk
        self.pl_update_head()
        if self.thumbs_active:
            GLib.idle_add(self.load_pl_thumbs)

    def load_pl_thumbs(self):
        """Fetch the grid's thumbnails (4 at a time); only once the tab has been opened."""
        if not hasattr(self, "thumb_pool"):
            from concurrent.futures import ThreadPoolExecutor
            self.thumb_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="thumbs")
        for eurl, (pic, turl) in self.pl_pics.items():
            if not turl or pic.get_paintable() is not None:
                continue
            if turl in self.thumb_cache:
                pic.set_paintable(self.thumb_cache[turl])
            elif turl not in self.thumb_requested:
                self.thumb_requested.add(turl)
                self.thumb_pool.submit(self._load_thumb, turl)
        return False

    def _load_thumb(self, turl):
        try:
            tex = download_image(turl)
        except Exception:
            log.debug("Playlist thumbnail failed: %s", turl, exc_info=True)
            self.thumb_requested.discard(turl)
            return
        GLib.idle_add(self._thumb_ready, turl, tex)

    def _thumb_ready(self, turl, tex):
        self.thumb_cache[turl] = tex
        for pic, u in self.pl_pics.values():
            if u == turl:
                pic.set_paintable(tex)
        return False

    def pl_toggled(self, chk, eurl):
        st = self.pl_state[self.pl_url]
        (st["off"].discard if chk.get_active() else st["off"].add)(eurl)
        self.pl_update_head()

    def thumb_toggled(self, chk, eurl):
        st = self.pl_state[self.pl_url]
        (st["thumbs"].add if chk.get_active() else st["thumbs"].discard)(eurl)
        self.pl_update_head()

    def pl_select(self, on):
        for chk in list(self.pl_checks):
            chk.set_active(on)           # fires pl_toggled for each row

    def thumbs_select(self, on):
        off = self.pl_state.get(self.pl_url, new_state())["off"]
        for eurl, chk in self.pl_thumb_checks.items():
            if eurl not in off:
                chk.set_active(on)

    def text(self):
        return self.url_buf.get_text(self.url_buf.get_start_iter(), self.url_buf.get_end_iter(), False)

    def get_urls(self):
        """The distinct, valid http(s) links in the box (anything else is ignored, never run)."""
        seen, out = set(), []
        for l in self.text().splitlines():
            url = valid_url(l)
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def current_url(self):
        """The link on the cursor's line; on an empty line, the nearest link above it."""
        it = self.url_buf.get_iter_at_mark(self.url_buf.get_insert())
        for line in range(it.get_line(), -1, -1):
            start = self.url_buf.get_iter_at_line(line)[1]
            end = start.copy()
            if not end.ends_line():
                end.forward_to_line_end()
            text = self.url_buf.get_text(start, end, False).strip()
            if text and not text.startswith("#"):
                return text
        return ""

    def clear_urls(self, *_):
        self.url_buf.set_text("")

    def import_file(self, *_):
        dialog = Gtk.FileDialog(title="Import URLs from text file")
        if self.last_import and Path(self.last_import).exists():
            dialog.set_initial_file(Gio.File.new_for_path(self.last_import))

        def done(d, res):
            try:
                path = d.open_finish(res).get_path()
            except GLib.Error as e:
                log.debug("Import dialog dismissed: %s", e.message)
                return
            self.load_url_file(path)

        dialog.open(self, None, done)

    def load_url_file(self, path):
        """Append the http(s) links of a text file to the URL box (import button or drag and drop)."""
        try:
            lines = read_limited(path, MAX_TEXT_FILE).splitlines()
        except Exception as e:
            log.exception("Import failed")
            self.append(f"[import failed — {e}]\n")
            return
        urls = [u for u in (valid_url(l) for l in lines) if u]
        log.info("Imported %d URLs from %s", len(urls), path)
        if not urls:
            self.append(f"[import failed — no links found in {path}]\n")
            return
        self.last_import = path
        existing = self.text().rstrip("\n")
        self.url_buf.set_text((existing + "\n" if existing else "") + "\n".join(urls))
        self.append(f"[imported {len(urls)} URLs from {path}]\n")
        self.save_settings()

    def on_file_drop(self, _target, value, _x, _y):
        for f in value.get_files():
            if f.get_path():
                self.load_url_file(f.get_path())
        return True

    def on_text_drop(self, _target, value, _x, _y):
        links = [u for u in (valid_url(l) for l in value.splitlines()) if u]
        if not links:
            return False
        existing = self.text().rstrip("\n")
        self.url_buf.set_text((existing + "\n" if existing else "") + "\n".join(links))
        return True

    def choose_folder(self, *_):
        dialog = Gtk.FileDialog(title="Select download folder")
        dialog.set_initial_folder(Gio.File.new_for_path(str(self.folder)))

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
            except GLib.Error as e:
                log.debug("Folder dialog dismissed: %s", e.message)
                return
            self.folder = Path(f.get_path())
            log.info("Download folder: %s", self.folder)
            self.refresh_summary()
            self.save_settings()

        dialog.select_folder(self, None, done)

    def on_urls_changed(self, *_):
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(700, self.scan_urls)
        self.show_current()
        self.schedule_save()

    def scan_urls(self):
        self._debounce = 0
        for url in self.get_urls():
            if url not in self.cache and url not in self.inflight:
                self.inflight.add(url)
                threading.Thread(target=self._fetch, args=(url,), daemon=True, name="fetch").start()
        self.show_current()
        return False

    def _fetch(self, url):
        cmd = [ytdlp(), "-J", "--flat-playlist",
               "--yes-playlist" if self.sel["playlist"] == "all" else "--no-playlist",
               *self.cookie_args(), *js_runtime_args(), "--", url]
        log.info("Fetch: %s", cmd)
        with self.fetch_slots:
            try:
                with self.vault.resolve(cmd) as real_cmd:        # cookies exist as a private RAM file only for this call
                    out = subprocess.run(real_cmd, capture_output=True, text=True, timeout=90, env=child_env())
                if out.returncode:
                    log.error("Fetch failed (%s): %s", out.returncode, out.stderr.strip())
                    GLib.idle_add(self.fetch_done, url, None, None, out.stderr.strip())
                    return
                info = json.loads(out.stdout)
            except Exception:
                log.exception("Fetch error")
                GLib.idle_add(self.fetch_done, url, None, None)
                return
        log.info("Fetched: %s", info.get("title"))
        texture = None
        src = info.get("thumbnails") or next((e.get("thumbnails") for e in info.get("entries") or []
                                              if e and e.get("thumbnails")), None)
        thumbs = [t["url"] for t in reversed(src or [])
                  if t.get("url", "").split("?")[0].lower().endswith((".jpg", ".jpeg", ".png"))]
        for turl in thumbs[:1] or ([info["thumbnail"]] if info.get("thumbnail") else []):
            try:
                texture = download_image(turl)
            except Exception:
                log.exception("Thumbnail load failed: %s", turl)
        GLib.idle_add(self.fetch_done, url, info, texture)

    def fetch_done(self, url, info, texture, err=None):
        self.inflight.discard(url)
        self.cache[url] = (info, texture) if info else None
        if info:
            self.fetch_errors.pop(url, None)
        else:
            self.fetch_errors[url] = err or ""
            if needs_credentials(err):
                self.prompt_credentials(url)
        self.show_current()
        return False

    def fetch_failure_note(self, url):
        err = self.fetch_errors.get(url, "")
        if needs_credentials(err):
            return "needs you to be signed in (see Options, Cookies)"
        why = explain_error(err, 1)[0] if err else ""
        return f"could not fetch: {why}" if why and not why.startswith("yt-dlp stopped") \
            else "could not fetch (see the Debug log tab)"

    def show_current(self):
        """Show the metadata of the URL on the cursor's line in the sections below."""
        url = self.current_url()
        hit = self.cache.get(url)
        self.show_playlist(url, hit[0] if hit else None)
        self.set_info(hit[0] if hit else None, hit[1] if hit else None,
                      note="fetching…" if url in self.inflight else
                      self.fetch_failure_note(url) if url in self.cache and not hit else None)

    def build_formats_page(self):
        """The Formats tab: a titled table of what the selected video offers; click a row to choose it."""
        self.fmt_hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, vexpand=True,
                                  css_classes=["dim-label"], margin_start=12, margin_end=12)
        header = Gtk.Box(spacing=6, margin_start=8, margin_end=8, margin_top=8)
        header.append(Gtk.Box(width_request=22))                  # space above the radio buttons
        for title, width in zip(COLUMNS, WIDTHS):
            header.append(Gtk.Label(label=title, xalign=0, width_chars=width, css_classes=["heading"]))
        self.fmt_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.fmt_list.connect("row-activated", lambda _lb, row: self.fmt_checks[row.get_index()].set_active(True))
        scroll = Gtk.ScrolledWindow(child=self.fmt_list, min_content_height=230, vexpand=True,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        table.append(header)
        table.append(Gtk.Separator())
        table.append(scroll)
        self.fmt_checks = []
        self.fmt_stack = Gtk.Stack(vexpand=True)
        self.fmt_stack.add_named(self.fmt_hint, "hint")
        self.fmt_stack.add_named(table, "list")
        return self.fmt_stack

    def update_formats(self, url, info):
        rows = format_rows(info) if info and not is_playlist(info) else []
        if not rows:
            self.fmt_url = None
            self.fmt_hint.set_label("Formats are listed for a single video. Put the cursor on a video link."
                                    if not is_playlist(info) else
                                    "Playlist entries use the Audio and Video tab settings.")
            self.fmt_stack.set_visible_child_name("hint")
            return
        self.fmt_stack.set_visible_child_name("list")
        if self.fmt_url == url:
            return
        self.fmt_url = url
        child = self.fmt_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.fmt_list.remove(child)
            child = nxt
        self.fmt_checks = []
        chosen = self.format_choice.get(url, {}).get("id")
        first = None
        auto = {"id": "", "cells": ("Automatic", "", "", "", ""), "video": True, "audio": True,
                "label": "Automatic: use the Audio and Video tab settings"}
        for row in [auto] + rows:
            line = Gtk.Box(spacing=6, margin_top=3, margin_bottom=3, margin_start=8, margin_end=8,
                           tooltip_text=row["label"])
            chk = Gtk.CheckButton()
            if first is None:
                first = chk
            else:
                chk.set_group(first)
            chk.set_active(row["id"] == (chosen or ""))
            chk.connect("toggled", self.on_format_toggled, url, row)
            line.append(chk)
            for text, width in zip(row["cells"], WIDTHS):
                line.append(Gtk.Label(label=text, xalign=0, width_chars=width, max_width_chars=width,
                                      ellipsize=3))
            self.fmt_checks.append(chk)
            self.fmt_list.append(line)

    def on_format_toggled(self, chk, url, row):
        if not chk.get_active():
            return
        if row["id"]:
            self.format_choice[url] = {"id": row["id"], "video": row["video"], "audio": row["audio"]}
        else:
            self.format_choice.pop(url, None)
        log.debug("Format for %s: %s", url, row["id"] or "automatic")
        self.refresh_summary()

    def set_info(self, info, texture, note=None):
        self.info = info
        self.fetch_note = note
        self.update_formats(self.current_url(), info)
        self.thumb.set_paintable(texture)
        self.update_sub_flags()
        self.refresh_summary()
        return False

    def update_sub_flags(self):
        """Grey out subtitle languages the selected video doesn't offer."""
        i = self.info
        have = set((i.get("subtitles") or {}) | (i.get("automatic_captions") or {})) if i else None
        for key, btn in self.sub_buttons.items():
            btn.set_sensitive(have is None or key == "all" or
                              any(h == key or h.startswith(key + "-") for h in have))
