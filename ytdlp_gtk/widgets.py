"""Reusable GTK helpers: autoscroll, scrollbars, resize grips, titled frames."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk  # noqa: E402


def autoscroll(scrolled):
    """Keep a scrolled text view on its newest line, unless the user has scrolled up to read."""
    adj, state = scrolled.get_vadjustment(), {"follow": True}

    def content_changed(a):
        if state["follow"]:
            a.set_value(a.get_upper() - a.get_page_size())

    def user_scrolled(a):
        state["follow"] = a.get_value() >= a.get_upper() - a.get_page_size() - 24

    adj.connect("changed", content_changed)
    adj.connect("value-changed", user_scrolled)
    return state


def style_scrollbars(widget):
    """Classic, always-visible, high-contrast side scrollbars everywhere (no fading overlay ones)."""
    if isinstance(widget, Gtk.ScrolledWindow):
        widget.set_overlay_scrolling(False)
        widget.add_css_class("logscroll")
    child = widget.get_first_child()
    while child:
        style_scrollbars(child)
        child = child.get_next_sibling()


def resize_handle(window, target, key):
    """Thin grip under a scrolled area; drag it up/down to set that area's height."""
    grip = Gtk.Box(height_request=10, css_classes=["toolbar"], tooltip_text="Drag to resize")
    grip.append(Gtk.Separator(hexpand=True, valign=Gtk.Align.CENTER))
    grip.set_cursor_from_name("row-resize")
    drag = Gtk.GestureDrag()
    start = {}

    def begin(_g, _x, _y):
        start["h"] = target.get_height()
        start["wh"] = window.get_height()

    def update(_g, _dx, dy):
        target.set_vexpand(False)
        target.set_size_request(-1, max(40, int(start["h"] + dy)))
        if not (window.is_maximized() or window.is_fullscreen()):      # window follows the grip
            window.set_default_size(window.get_width(), max(300, int(start["wh"] + dy)))

    def end(*_):
        window.pane_heights[key] = target.get_height()
        window.save_settings()

    drag.connect("drag-begin", begin)
    drag.connect("drag-update", update)
    drag.connect("drag-end", end)
    grip.add_controller(drag)
    window.panes[key] = target
    return grip


def titled(title, child, tip=None):
    """Wrap a widget in a titled frame (section); tip pops up on hovering the title."""
    frame = Gtk.Frame(label=title)
    if tip:
        frame.get_label_widget().set_tooltip_text(tip)
    child.set_margin_top(6)
    child.set_margin_bottom(6)
    child.set_margin_start(8)
    child.set_margin_end(8)
    frame.set_child(child)
    return frame
