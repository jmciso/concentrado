"""Dependency-free top-bar icon: StatusNotifierItem + com.canonical.dbusmenu over Gio D-Bus.

GNOME shows these through the AppIndicator extension (enabled by default on Ubuntu);
KDE and most other desktops support them natively.
"""

import itertools
import os

from gi.repository import Gio, GLib

SNI_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
WATCHER = "org.kde.StatusNotifierWatcher"

_ACTIVATE_ARGS = '<arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/>'
SNI_XML = f"""
<node><interface name="org.kde.StatusNotifierItem">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="WindowId" type="i" access="read"/>
  <property name="IconThemePath" type="s" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconPixmap" type="a(iiay)" access="read"/>
  <property name="AttentionIconName" type="s" access="read"/>
  <property name="OverlayIconName" type="s" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <property name="Menu" type="o" access="read"/>
  <property name="XAyatanaLabel" type="s" access="read"/>
  <property name="XAyatanaLabelGuide" type="s" access="read"/>
  <method name="ContextMenu">{_ACTIVATE_ARGS}</method>
  <method name="Activate">{_ACTIVATE_ARGS}</method>
  <method name="SecondaryActivate">{_ACTIVATE_ARGS}</method>
  <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
  <signal name="NewTitle"/>
  <signal name="NewIcon"/>
  <signal name="NewAttentionIcon"/>
  <signal name="NewOverlayIcon"/>
  <signal name="NewToolTip"/>
  <signal name="NewStatus"><arg name="status" type="s"/></signal>
  <signal name="XAyatanaNewLabel"><arg name="label" type="s"/><arg name="guide" type="s"/></signal>
</interface></node>"""

MENU_XML = """
<node><interface name="com.canonical.dbusmenu">
  <property name="Version" type="u" access="read"/>
  <property name="TextDirection" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconThemePath" type="as" access="read"/>
  <method name="GetLayout">
    <arg name="parentId" type="i" direction="in"/><arg name="recursionDepth" type="i" direction="in"/>
    <arg name="propertyNames" type="as" direction="in"/>
    <arg name="revision" type="u" direction="out"/><arg name="layout" type="(ia{sv}av)" direction="out"/>
  </method>
  <method name="GetGroupProperties">
    <arg name="ids" type="ai" direction="in"/><arg name="propertyNames" type="as" direction="in"/>
    <arg name="properties" type="a(ia{sv})" direction="out"/>
  </method>
  <method name="GetProperty">
    <arg name="id" type="i" direction="in"/><arg name="name" type="s" direction="in"/>
    <arg name="value" type="v" direction="out"/>
  </method>
  <method name="Event">
    <arg name="id" type="i" direction="in"/><arg name="eventId" type="s" direction="in"/>
    <arg name="data" type="v" direction="in"/><arg name="timestamp" type="u" direction="in"/>
  </method>
  <method name="EventGroup">
    <arg name="events" type="a(isvu)" direction="in"/><arg name="idErrors" type="ai" direction="out"/>
  </method>
  <method name="AboutToShow">
    <arg name="id" type="i" direction="in"/><arg name="needUpdate" type="b" direction="out"/>
  </method>
  <method name="AboutToShowGroup">
    <arg name="ids" type="ai" direction="in"/>
    <arg name="updatesNeeded" type="ai" direction="out"/><arg name="idErrors" type="ai" direction="out"/>
  </method>
  <signal name="ItemsPropertiesUpdated">
    <arg name="updatedProps" type="a(ia{sv})"/><arg name="removedProps" type="a(ias)"/>
  </signal>
  <signal name="LayoutUpdated"><arg name="revision" type="u"/><arg name="parent" type="i"/></signal>
  <signal name="ItemActivationRequested"><arg name="id" type="i"/><arg name="timestamp" type="u"/></signal>
</interface></node>"""

_ids = itertools.count(1)


class MenuItem:
    def __init__(self, label="", callback=None, enabled=True, separator=False):
        self.id = next(_ids)
        self.label = label
        self.callback = callback
        self.enabled = enabled
        self.visible = True
        self.separator = separator
        self.menu = None

    def props(self):
        if self.separator:
            return {"type": GLib.Variant("s", "separator"), "visible": GLib.Variant("b", self.visible)}
        return {
            "label": GLib.Variant("s", self.label.replace("_", "__")),
            "enabled": GLib.Variant("b", self.enabled),
            "visible": GLib.Variant("b", self.visible),
        }

    def set_label(self, label):
        if label != self.label:
            self.label = label
            self.menu and self.menu._props_changed(self)

    def set_enabled(self, enabled):
        if enabled != self.enabled:
            self.enabled = enabled
            self.menu and self.menu._props_changed(self)

    def set_visible(self, visible):
        if visible != self.visible:
            self.visible = visible
            self.menu and self.menu._layout_changed()


def separator():
    return MenuItem(separator=True)


class StatusIcon:
    """A top-bar icon with an optional text label and a menu.

    `on_availability(bool)` is called when a tray host (e.g. GNOME's AppIndicator
    extension) accepts or drops the icon, so callers know if hiding the window is safe.
    """

    def __init__(self, item_id, title, icon, items, on_activate=None, on_secondary=None, on_availability=None):
        self.item_id = item_id
        self.title = title
        self.icon = icon
        self.label = ""
        self.label_guide = ""
        self.tooltip = ""
        self.items = items
        self.on_activate = on_activate
        self.on_secondary = on_secondary
        self.on_availability = on_availability
        self.available = False
        self.revision = 1
        for it in items:
            it.menu = self

        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        sni_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self._regs = [
            self.conn.register_object(SNI_PATH, sni_info, self._sni_call, self._sni_prop, None),
            self.conn.register_object(MENU_PATH, menu_info, self._menu_call, self._menu_prop, None),
        ]
        self.bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._own = Gio.bus_own_name_on_connection(self.conn, self.bus_name, Gio.BusNameOwnerFlags.NONE, None, None)
        self._watch = Gio.bus_watch_name_on_connection(
            self.conn, WATCHER, Gio.BusNameWatcherFlags.NONE, self._watcher_appeared, self._watcher_vanished)

    # ------------------------------------------------------------ public API
    def set_icon(self, icon):
        if icon != self.icon:
            self.icon = icon
            self._emit_sni("NewIcon")

    def set_label(self, label, guide=""):
        if label != self.label:
            self.label, self.label_guide = label, guide
            self._emit_sni("XAyatanaNewLabel", GLib.Variant("(ss)", (label, guide)))

    def set_tooltip(self, text):
        if text != self.tooltip:
            self.tooltip = text
            self._emit_sni("NewToolTip")

    # ------------------------------------------------------------ registration
    def _watcher_appeared(self, conn, name, owner):
        conn.call(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                  GLib.Variant("(s)", (self.bus_name,)), None, Gio.DBusCallFlags.NONE, -1, None,
                  self._registered)

    def _registered(self, conn, result):
        try:
            conn.call_finish(result)
            self._set_available(True)
        except GLib.Error:
            self._set_available(False)

    def _watcher_vanished(self, *_):
        self._set_available(False)

    def _set_available(self, value):
        if value != self.available:
            self.available = value
            if self.on_availability:
                self.on_availability(value)

    # ------------------------------------------------------------ StatusNotifierItem
    def _sni_prop(self, conn, sender, path, iface, prop):
        values = {
            "Category": ("s", "ApplicationStatus"),
            "Id": ("s", self.item_id),
            "Title": ("s", self.title),
            "Status": ("s", "Active"),
            "WindowId": ("i", 0),
            "IconThemePath": ("s", os.path.dirname(self.icon)),
            "IconName": ("s", self.icon),
            "IconPixmap": ("a(iiay)", []),
            "AttentionIconName": ("s", ""),
            "OverlayIconName": ("s", ""),
            "ToolTip": ("(sa(iiay)ss)", ("", [], self.title, self.tooltip)),
            "ItemIsMenu": ("b", True),
            "Menu": ("o", MENU_PATH),
            "XAyatanaLabel": ("s", self.label),
            "XAyatanaLabelGuide": ("s", self.label_guide),
        }
        sig, val = values[prop]
        return GLib.Variant(sig, val)

    def _sni_call(self, conn, sender, path, iface, method, params, invocation):
        if method == "Activate" and self.on_activate:
            GLib.idle_add(lambda: self.on_activate() and False)
        elif method == "SecondaryActivate" and self.on_secondary:
            GLib.idle_add(lambda: self.on_secondary() and False)
        invocation.return_value(None)

    def _emit_sni(self, signal, params=None):
        try:
            self.conn.emit_signal(None, SNI_PATH, "org.kde.StatusNotifierItem", signal, params)
        except GLib.Error:
            pass

    # ------------------------------------------------------------ dbusmenu
    def _by_id(self, item_id):
        return next((it for it in self.items if it.id == item_id), None)

    def _root_props(self):
        return {"children-display": GLib.Variant("s", "submenu")}

    def _node(self, item):
        return GLib.Variant("(ia{sv}av)", (item.id, item.props(), []))

    def _menu_prop(self, conn, sender, path, iface, prop):
        return {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }[prop]

    def _menu_call(self, conn, sender, path, iface, method, params, invocation):
        args = params.unpack()
        if method == "GetLayout":
            parent = args[0]
            item = self._by_id(parent)
            if parent == 0 or item is None:
                layout = (0, self._root_props(), [self._node(it) for it in self.items])
            else:
                layout = (item.id, item.props(), [])
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, layout)))
        elif method == "GetGroupProperties":
            ids = args[0] or [it.id for it in self.items]
            out = [(0, self._root_props())] if 0 in ids else []
            out += [(it.id, it.props()) for it in self.items if it.id in ids]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (out,)))
        elif method == "GetProperty":
            item = self._by_id(args[0])
            props = item.props() if item else self._root_props()
            value = props.get(args[1], GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant("(v)", (value,)))
        elif method == "Event":
            self._dispatch(args[0], args[1])
            invocation.return_value(None)
        elif method == "EventGroup":
            for item_id, event_id, _data, _ts in args[0]:
                self._dispatch(item_id, event_id)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)

    def _dispatch(self, item_id, event_id):
        item = self._by_id(item_id)
        if event_id == "clicked" and item and item.callback and item.enabled:
            GLib.idle_add(lambda: item.callback() and False)

    def _props_changed(self, item):
        try:
            self.conn.emit_signal(None, MENU_PATH, "com.canonical.dbusmenu", "ItemsPropertiesUpdated",
                                  GLib.Variant("(a(ia{sv})a(ias))", ([(item.id, item.props())], [])))
        except GLib.Error:
            pass

    def _layout_changed(self):
        self.revision += 1
        try:
            self.conn.emit_signal(None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                                  GLib.Variant("(ui)", (self.revision, 0)))
        except GLib.Error:
            pass
