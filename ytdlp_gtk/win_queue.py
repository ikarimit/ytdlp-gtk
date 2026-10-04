"""Window mixin: command building, download queue, alerts."""
import json
import os
import re
import subprocess
import threading
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, GLib, Gio, Gtk  # noqa: E402

from .config import CONFIG_DIR, ICON, log
from .errors import explain_error, is_bad, needs_credentials
from .formatting import whole
from .options import EXTRA_ARGS, EXTRA_OPTIONS, NA, PP_PREFIXES, PROGRESS_TEMPLATE
from .playlists import is_playlist, new_state
from .security import read_limited, validate_cmd, write_private
from .tools import child_env, js_runtime_args, move_files, pdeath_prefix, play_sound, ytdlp


class QueueMixin:
    """Methods of the main window (queue)."""

    def build_cmd(self, url, thumb=False):
        s = self.sel
        cmd = [ytdlp(), "--newline", "--progress-template", PROGRESS_TEMPLATE,
               "-o", str(self.folder / "%(title)s.%(ext)s")]
        h = "" if s["video_res"] == "best" else f"[height<={s['video_res']}]"
        cont = s["video_container"]
        fc = self.format_choice.get(url)               # a specific format picked in the Formats tab
        if fc:
            fid = fc["id"]
            if fc["video"] and not fc["audio"] and s["mode"] != "video":
                fid += "+bestaudio"                    # video-only format: add the best audio
            cmd += ["-f", fid]
            if s["mode"] == "audio":
                cmd += ["-x", "--audio-format", s["audio_format"], "--audio-quality", s["audio_quality"]]
            elif cont != "best":
                cmd += ["--remux-video" if s["mode"] == "video" else "--merge-output-format", cont]
        elif s["mode"] == "audio":
            cmd += ["-f", "bestaudio/best", "-x", "--audio-format", s["audio_format"],
                    "--audio-quality", s["audio_quality"]]
        elif s["mode"] == "video":
            cmd += ["-f", f"bestvideo{h}/bestvideo"]
            if cont != "best":
                cmd += ["--remux-video", cont]
        else:
            cmd += ["-f", f"bv*{h}+ba/b{h}/b"]
            if cont != "best":
                cmd += ["--merge-output-format", cont]
        if thumb or self.thumb_check.get_active():
            cmd += ["--write-thumbnail", "--convert-thumbnails", "jpg"]
        for key, _t, _o, _d in EXTRA_OPTIONS:
            cmd += EXTRA_ARGS.get((key, s[key]), [])
        cmd += self.cookie_args() + js_runtime_args()
        if s["subs"] != "off":
            langs = "all,-live_chat" if s["subs"] == "all" else self.resolve_langs(url, s["subs"].split(","))
            # --embed-subs fetches subtitles itself and deletes the files afterwards; adding
            # --write-subs would make yt-dlp keep them.
            cmd += ["--write-auto-subs", "--sub-langs", langs]
            if s["embed_subs"] != "on":
                cmd += ["--write-subs"]
        return cmd + ["--", url]               # `--`: whatever follows is a link, never an option

    def resolve_langs(self, url, codes):
        """One exact subtitle track per picked language (a bare 'en.*' also grabs en-en etc.)."""
        hit = self.cache.get(url)
        info = hit[0] if hit else None
        have = list((info.get("subtitles") or {}) | (info.get("automatic_captions") or {})) if info else []
        out = []
        for c in codes:
            if c in have or not have:
                out.append(c)
            else:
                variants = sorted(h for h in have if h.startswith(c + "-"))
                out.append(variants[0] if variants else c)
        return ",".join(out)

    def job_for(self, it):
        ref = Gtk.TreeRowReference.new(self.store, self.store.get_path(it))
        return {"ref": ref, "cmd": json.loads(self.store[it][7]), "url": self.store[it][6],
                "title": self.store[it][0], "move_to": self.store[it][8]}

    def busy_paths(self):
        with self.lock:
            return {j["ref"].get_path().to_string() for j in [*self.jobs, *self.active.values()]
                    if j["ref"].valid()}

    def reset_row(self, it, cmd=None, move_to=None):
        """Put a row back to Queued in place (no new line)."""
        row = self.store[it]
        row[1], row[2], row[3], row[4], row[5], row[9] = "—", 0, "Queued", "", "", ""
        if cmd is not None:
            row[7] = json.dumps(cmd)
        if move_to is not None:
            row[8] = move_to

    def schedule(self):
        """Start waiting jobs until max_parallel are running (safe from any thread)."""
        with self.lock:
            while self.jobs and len(self.active) < self.max_parallel and not self.closing:
                job = self.jobs.pop(0)
                if not job["ref"].valid():        # row was removed while it waited
                    continue
                self.active[id(job)] = job
                threading.Thread(target=self.run_wrapper, args=(job,), daemon=True,
                                 name="download").start()

    def run_wrapper(self, job):
        try:
            self.run_job(job)
        except Exception:
            log.exception("Job crashed")
            self.ui(self.update_row, job["ref"], status="Failed")
        finally:
            cm = job.pop("cookie_cm", None)
            if cm is not None:
                cm.__exit__(None, None, None)
            with self.lock:
                self.active.pop(id(job), None)
            self.schedule()
            with self.lock:
                idle = not self.jobs and not self.active
            if idle and not self.closing:
                self.ui(self.queue_finished)

    def queue_finished(self):
        with self.lock:
            done, failed, last = self.batch["done"], self.batch["failed"], self.batch["last"]
            self.batch.update(done=0, failed=0, last="")
        if not (done or failed):
            return
        if failed:
            body = f"{done} finished, {failed} failed." if done else f"{failed} failed."
            title = "Downloads finished with errors"
        else:
            body = last if done == 1 else f"{done} downloads finished."
            title = "Download finished" if done == 1 else "Downloads finished"
            play_sound("done")
        self.toasts.add_toast(Adw.Toast(title=f"{title}: {body}", timeout=8))
        note = Gio.Notification.new(title)
        note.set_body(body)
        note.set_icon(Gio.ThemedIcon.new(ICON))
        self.get_application().send_notification("queue-done", note)

    def enqueue_alert(self, heading, body, responses, handler):
        """responses: [(id, label, suggested)]; the first is also the close/escape response."""
        self.alerts.append((heading, body, responses, handler))
        self.next_alert()

    def next_alert(self):
        if self.alert_open or not self.alerts:
            return
        heading, body, responses, handler = self.alerts.pop(0)
        self.alert_open = True
        dialog = Adw.AlertDialog(heading=heading, body=body)
        for rid, label, suggested in responses:
            dialog.add_response(rid, label)
            if suggested:
                dialog.set_response_appearance(rid, Adw.ResponseAppearance.SUGGESTED)
                dialog.set_default_response(rid)
        dialog.set_close_response(responses[0][0])

        def response(_d, resp):
            self.alert_open = False
            handler(resp)
            self.next_alert()

        dialog.connect("response", response)
        dialog.present(self)

    def show_error(self, job, code, errors):
        if self.closing:
            return False
        play_sound("error")
        text = " ".join(errors)
        detail = (errors[-1] if errors else "").strip()[:260]
        why, fix = explain_error(text, code)
        body = f"{job['title']}\n\nWhat happened: {detail or 'no error message from yt-dlp'}\n\nWhy: {why}\n\nFix: {fix}"
        creds = needs_credentials(text)
        responses = [("close", "Close", False)] + ([("cookies", "Set up cookies…", False)] if creds else []) + \
                    [("retry", "Retry", True)]

        def handler(resp):
            if resp == "cookies":
                self.show_cookie_setup(preselect=self.sel["cookies"] if self.sel["cookies"] != "none" else None,
                                       reason="This video needs you to be signed in.")
            elif resp == "retry" and job["ref"].valid():
                it = self.store.get_iter(job["ref"].get_path())
                self.reset_row(it)
                with self.lock:
                    self.jobs.append(self.job_for(it))
                self.schedule()

        self.enqueue_alert("Download failed", body, responses, handler)
        return False

    def prompt_credentials(self, url):
        """A link couldn't be read because it needs a signed-in account."""
        if url in self.cred_prompted or self.closing:
            return
        self.cred_prompted.add(url)
        play_sound("error")
        have = self.sel["cookies"] != "none"
        if have:
            body = (f"{url}\n\nThe cookies didn't unlock this video. Make sure you are signed in to the site in "
                    "that browser (and that the account is allowed to watch it), then check the setup again.")
        else:
            body = (f"{url}\n\nThis video needs you to be signed in (age-restricted, private, members-only, "
                    "or a bot check).\n\nThe app can reuse your browser's login by saving its cookies. Set that up now?")
        self.enqueue_alert("Sign-in needed", body,
                           [("later", "Not now", False),
                            ("setup", "Check cookies…" if have else "Set up cookies…", True)],
                           lambda r: r == "setup" and self.show_cookie_setup(
                               preselect=self.sel["cookies"] if have else None,
                               reason="This video needs you to be signed in."))

    def expand(self, url):
        """A playlist link becomes one (url, title, thumbnail?) per ticked video."""
        hit = self.cache.get(url)
        info = hit[0] if hit else None
        if is_playlist(info):
            st = self.pl_state.get(url, new_state()) if self.sel["playlist"] == "all" else new_state()
            return [(e["url"], e["title"], e["url"] in st["thumbs"]) for e in self.pl_entries(url)
                    if e["url"] and e["url"] not in st["off"]]
        return [(url, (info or {}).get("title") or url, False)]

    def on_download(self, *_):
        added = 0
        for url, title, thumb in [item for u in self.get_urls() for item in self.expand(u)]:
            cmd = self.build_cmd(url, thumb)
            it = next((r.iter for r in self.store if r[6] == url), None)
            if it is None:
                it = self.store.append([title, "—", 0, "Queued", "", "", url, json.dumps(cmd), self.move_to, ""])
            elif self.store[it][3] in ("Downloading", "Processing", "Moving") or \
                    self.store.get_path(it).to_string() in self.busy_paths():
                continue                   # already running or waiting
            else:
                self.reset_row(it, cmd, self.move_to)    # restart in the same line
            with self.lock:
                self.jobs.append(self.job_for(it))
            added += 1
        log.info("Queued %d item(s)", added)
        self.save_settings()
        self.schedule()
        if added:
            self.tabs.set_current_page(1)               # show the Queue tab

    def start_queue(self, *_, stopped=True):
        """Run rows that are waiting (restored from last session); the button also retries
        stopped and failed ones in place."""
        wanted = ("Queued", "Stopped", "Failed") if stopped else ("Queued",)
        busy = self.busy_paths()
        n = 0
        for row in self.store:
            if row[3] in wanted and row[7] and row.path.to_string() not in busy:
                self.reset_row(row.iter)
                with self.lock:
                    self.jobs.append(self.job_for(row.iter))
                n += 1
        log.info("Start: %d waiting item(s)", n)
        if n and not stopped:
            self.append(f"[resuming {n} unfinished item(s) from last time]\n")
        self.schedule()

    @staticmethod
    def ui(fn, *args, **kwargs):
        """Run fn on the GTK main thread (GLib.idle_add takes no kwargs)."""
        GLib.idle_add(lambda: fn(*args, **kwargs) and False)

    def update_row(self, ref, **cols):
        if self.closing or not ref.valid():
            return False
        it = self.store.get_iter(ref.get_path())
        idx = {"title": 0, "size": 1, "progress": 2, "status": 3, "speed": 4, "eta": 5, "path": 9}
        for k, v in cols.items():
            self.store.set_value(it, idx[k], v)
        if "status" in cols or "path" in cols:
            self.schedule_save()
        return False

    def run_job(self, job):
        ref, ui = job["ref"], self.ui
        tag = f"[{job['title'][:24]}] " if self.max_parallel > 1 else ""
        if not validate_cmd(job["cmd"]):   # saved queues are data too: only commands of our own shape run
            log.error("Refused a command that failed the safety check: %s", job["cmd"])
            ui(self.update_row, ref, status="Failed")
            ui(self.show_error, job, 1, ["Refused to run: the command failed the safety check."])
            return
        cmd, errors = [ytdlp(), *job["cmd"][1:]], []
        out_root = Path(cmd[cmd.index("-o") + 1]).parent if "-o" in cmd else Path.home()
        pf = CONFIG_DIR / f".paths-{os.getpid()}-{id(job)}.txt"       # yt-dlp tells us where the file ended up
        write_private(pf, "")
        sep = cmd.index("--")
        cmd[sep:sep] = ["--print-to-file", "after_move:filepath", str(pf)]
        log.info("Download: %s", cmd)                    # (cookies appear only as a vault: placeholder here)
        job["cookie_cm"] = cm = self.vault.resolve(cmd)  # private RAM copy of the cookies, removed when the job ends
        cmd = pdeath_prefix() + cm.__enter__()
        ui(self.update_row, ref, status="Downloading")
        proc = job["proc"] = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=child_env())
        if job.get("stopped") or self.closing:
            proc.terminate()
        for line in proc.stdout:
            line = line.rstrip()
            log.debug("yt-dlp: %s", line)
            if line.startswith("[PROG]"):
                st, pct, tot, est, spd, eta = (p.strip() for p in line[6:].split("|"))
                size = whole(tot) if tot not in NA else (f"~{whole(est)}" if est not in NA else "—")
                try:
                    p = int(float(pct.rstrip("%")))
                except ValueError:
                    p = 0
                ui(self.update_row, ref, progress=p, size=size,
                   speed="" if spd in NA else whole(spd), eta="" if eta in NA else eta)
                continue
            ui(self.append, tag + line + "\n", is_bad(line))
            if line.startswith("ERROR"):
                errors.append(line.split(":", 1)[-1].strip() if ":" in line else line)
            if line.startswith(PP_PREFIXES):
                ui(self.update_row, ref, status="Processing", speed="", eta="")
            elif "Destination:" in line and job["title"] == job["url"]:
                ui(self.update_row, ref, title=re.sub(r"\.f\d+$", "", Path(line.split("Destination:", 1)[1].strip()).stem))
        code = proc.wait()
        log.info("Job exit %s", code)
        if self.closing:                  # app is closing: leave the saved status so it resumes
            return
        if job.get("stopped"):
            ui(self.update_row, ref, status="Stopped", speed="", eta="")
        elif code == 0:
            files = [l for l in (read_limited(pf, 100_000).splitlines() if pf.exists() else []) if l.startswith("/")]
            final_path = files[0] if files else ""
            if job.get("move_to"):
                ui(self.update_row, ref, status="Moving", speed="", eta="")
                try:
                    moved = move_files(files, job["move_to"], out_root)
                    ui(self.append, f"{tag}[moved {len(moved)} file(s) to {job['move_to']}]\n")
                    if moved:
                        final_path = moved[0][1]
                except Exception as e:
                    log.exception("Move failed")
                    errors.append(f"Could not move files: {e}")
                    ui(self.show_error, job, 0, errors)
            pf.unlink(missing_ok=True)
            ui(self.update_row, ref, path=final_path)
            ui(self.update_row, ref, status="Done", progress=100, speed="", eta="")
            with self.lock:
                self.batch["done"] += 1
                self.batch["last"] = job["title"]
        else:
            ui(self.update_row, ref, status="Failed", speed="", eta="")
            with self.lock:
                self.batch["failed"] += 1
            ui(self.show_error, job, code, errors)
            pf.unlink(missing_ok=True)

    def on_row_activated(self, _tv, path, _col):
        """Double-click a finished row: open its file with the default app."""
        row = self.store[path]
        target = row[9]
        if row[3] != "Done" or not target:
            return
        if not os.path.isfile(target):
            self.toasts.add_toast(Adw.Toast(title="That file is no longer there", timeout=4))
            return
        ctype = Gio.content_type_guess(target, None)[0] or ""
        if ctype.split("/")[0] not in ("video", "audio", "image") and ctype not in ("text/vtt", "application/x-subrip"):
            self.toasts.add_toast(Adw.Toast(title=f"Not opening this file type ({ctype})", timeout=4))
            return
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(target).get_uri(), None)
        except GLib.Error as e:
            log.error("Could not open %s: %s", target, e.message)
            self.toasts.add_toast(Adw.Toast(title=f"Could not open the file: {e.message}", timeout=5))

    def stop_queue(self, *_):
        with self.lock:
            dropped, self.jobs = self.jobs, []
            running = list(self.active.values())
        for job in dropped:
            self.update_row(job["ref"], status="Stopped")
        for job in running:
            job["stopped"] = True
            if job.get("proc"):
                job["proc"].terminate()
        log.info("Queue stopped (%d waiting dropped, %d running stopped)", len(dropped), len(running))

    def clear_status(self, statuses):
        n = 0
        for row in [r for r in self.store if r[3] in statuses]:
            self.store.remove(row.iter)
            n += 1
        log.info("Cleared %d row(s) with status %s", n, statuses)
        self.save_settings()

    def clear_finished(self, *_):
        self.clear_status(("Done",))

    def remove_selected(self, *_):
        model, paths = self.tv.get_selection().get_selected_rows()
        refs = [Gtk.TreeRowReference.new(model, p) for p in paths]
        busy, removed = 0, 0
        for ref in refs:
            it = model.get_iter(ref.get_path())
            if model[it][3] in ("Downloading", "Processing", "Moving"):
                busy += 1
            else:
                model.remove(it)
                removed += 1
        if busy:
            self.toasts.add_toast(Adw.Toast(title=f"{busy} running download(s) kept: press Stop first", timeout=4))
        if removed:
            log.info("Removed %d selected row(s)", removed)
            self.save_settings()
