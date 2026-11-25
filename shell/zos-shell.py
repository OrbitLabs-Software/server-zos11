#!/usr/bin/env python3
"""zOS Oberflaeche: native GTK4-Shell. Laeuft lokal auf dem Server, ohne Browser und ohne Netzwerk."""
import json, math, os, sys, threading, time
from string import Template

import cairo
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

sys.path.insert(0, "/opt/zos/bin")
import zoscore, zossec, zosai

V, H = Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL
CENTER, END = Gtk.Align.CENTER, Gtk.Align.END

APPS = [("overview", "Übersicht", "computer-symbolic"),
        ("services", "Dienste", "preferences-system-symbolic"),
        ("disks", "Speicher", "drive-harddisk-symbolic"),
        ("net", "Netzwerk", "network-wired-symbolic"),
        ("users", "Benutzer", "system-users-symbolic"),
        ("updates", "Updates", "software-update-available-symbolic"),
        ("ai", "AI-Core", "applications-engineering-symbolic"),
        ("security", "Sicherheit", "security-high-symbolic"),
        ("logs", "Protokolle", "text-x-generic-symbolic")]
ACC = ["#2f6bff", "#7c3aed", "#0d9488", "#d9480f", "#db2777"]
PAL = {
    "light": dict(bg="#e9eef9", mica="rgba(248,250,255,.88)", card="rgba(255,255,255,.62)", card2="rgba(255,255,255,.92)",
                  tx="#13171f", dim="#586274", line="rgba(18,28,48,.10)", ok="#0f7b0f", bad="#c42b1c", warn="#9a6700",
                  w=("#9ec0ff", "#d7b8ff", "#8fe8d8")),
    "dark": dict(bg="#080c1a", mica="rgba(30,34,52,.88)", card="rgba(255,255,255,.055)", card2="rgba(255,255,255,.10)",
                 tx="#f2f5fc", dim="#a0abc0", line="rgba(255,255,255,.10)", ok="#6ccb5f", bad="#ff8a95", warn="#fcb900",
                 w=("#2c55e8", "#7a3df0", "#0aa6b8"))}

CSS = Template("""
* { font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif; font-size: ${fs}px; }
window { background: $bg; color: $tx; }
.dim { color: $dim; } .ok { color: $ok; } .bad { color: $bad; } .warn { color: $warn; }
.b { font-weight: 600; } .h1 { font-size: ${h1}px; font-weight: 600; } .h2 { font-size: ${h2}px; font-weight: 600; }
.small { font-size: ${fs2}px; }
.mono { font-family: "Noto Sans Mono", "DejaVu Sans Mono", monospace; font-size: ${fs2}px; }
.mica { background: $mica; border: 1px solid $line; border-radius: 12px; box-shadow: 0 16px 48px rgba(0,0,0,.35); $anim }
.menu { padding: 22px; border-radius: 14px; }
.tb { padding-left: 14px; }
button { background-image: none; box-shadow: none; text-shadow: none; $trans }
.tb button { min-width: 42px; min-height: 38px; padding: 0; border-radius: 0; background: none; border: none; color: $tx; }
.tb button:hover { background: $card2; }
.tb button.x:hover { background: #c42b1c; color: #fff; }
.card { background: $card; border: 1px solid $line; border-radius: 10px; padding: 14px; }
.row { padding: 6px 12px; border-radius: 8px; min-height: 46px; }
.row:hover { background: $card; }
.dot { min-width: 9px; min-height: 9px; border-radius: 99px; background: $dim; }
.dot.ok { background: $ok; } .dot.bad { background: $bad; }
.tag { padding: 1px 8px; border-radius: 6px; background: $card2; font-size: ${fs2}px; }
.btn { background: $card2; border: 1px solid $line; border-radius: 6px; padding: 3px 13px; min-height: 28px; color: $tx; }
.btn.pri { background: $ac; border-color: transparent; color: #fff; }
.ti { min-width: 46px; min-height: 40px; padding: 0 6px; border-radius: 8px; background: none; border: none; color: $tx; }
.ti:hover { background: $card2; }
.ti.on { border-bottom: 3px solid $dim; }
.ti.act { border-bottom: 3px solid $ac; }
.taskbar { background: $mica; border-top: 1px solid $line; padding: 4px 8px; }
.tile { background: none; border: none; border-radius: 10px; padding: 12px 4px; color: $tx; }
.tile:hover { background: $card2; }
.tilei { min-width: 46px; min-height: 46px; border-radius: 12px; background: $ac; color: #fff; }
.av { min-width: 36px; min-height: 36px; border-radius: 99px; background: $ac; color: #fff; font-weight: 600; }
entry { background: $card2; border: 1px solid $line; border-radius: 6px; padding: 0 10px; min-height: 32px; color: $tx; box-shadow: none; }
progressbar trough { background: $line; border-radius: 99px; min-height: 8px; border: none; }
progressbar progress { background: $ac; border-radius: 99px; min-height: 8px; border: none; }
.toast { background: $tx; color: $bg; border-radius: 99px; padding: 9px 18px; }
@keyframes pop { from { opacity: 0; } to { opacity: 1; } }
.lock { background: rgba(0,0,0,.22); }
.clock { font-size: 76px; font-weight: 300; }
.lockdate { font-size: 20px; }
.onscrim { color: #fff; text-shadow: 0 2px 12px rgba(0,0,0,.45); }
scrolledwindow, scrolledwindow > viewport { background: none; }
""")

STATE_FILE = "/var/lib/zos/ui.json"
S = {"t": "dark", "a": ACC[0]}
try:
    S.update(json.load(open(STATE_FILE)))
except Exception:
    pass


# ---------- Hilfsfunktionen ----------
def rgb(h): return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
def gb(n): return "%.2f TB" % (n / 1e12) if n >= 1e12 else "%.*f GB" % (0 if n >= 1e11 else 1, n / 1e9)
def dur(s): d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60; return (f"{d} T " if d else "") + f"{h} Std {m} Min"


def save():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        json.dump(S, open(STATE_FILE, "w"))
    except Exception:
        pass


def clear(box):
    c = box.get_first_child()
    while c:
        n = c.get_next_sibling()
        box.remove(c)
        c = n


def lbl(t, *cls):
    l = Gtk.Label(label=str(t), xalign=0)
    l.set_wrap(True)
    l.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    for c in cls:
        l.add_css_class(c)
    return l


def btn(t, cb, pri=False):
    b = Gtk.Button(label=t)
    b.add_css_class("btn")
    if pri:
        b.add_css_class("pri")
    b.connect("clicked", lambda *_: cb())
    return b


def icon(n, px=20):
    i = Gtk.Image.new_from_icon_name(n)
    i.set_pixel_size(px)
    return i


def dot(cls=""):
    d = Gtk.Box()
    d.add_css_class("dot")
    if cls:
        d.add_css_class(cls)
    d.set_valign(CENTER)
    return d


def bg(fn, cb):
    def run():
        try:
            r = (fn(), None)
        except Exception as e:
            r = (None, e)
        GLib.idle_add(lambda: (cb(*r), False)[1])
    threading.Thread(target=run, daemon=True).start()


def row(title, sub="", right=None, lead=None):
    r = Gtk.Box(spacing=12)
    r.add_css_class("row")
    if lead is not None:
        r.append(lead)
    c = Gtk.Box(orientation=V)
    c.set_hexpand(True)
    c.set_valign(CENTER)
    c.append(lbl(title, "b"))
    if sub:
        c.append(lbl(sub, "dim"))
    r.append(c)
    if right is not None:
        r.append(right)
    return r


def ring(name, pct, sub):
    b = Gtk.Box(orientation=V, spacing=2)
    b.add_css_class("card")
    a = Gtk.DrawingArea()
    a.set_content_width(104)
    a.set_content_height(104)
    a.set_halign(CENTER)

    def draw(_a, cr, w, h, *_):
        p = PAL[S["t"]]
        cr.set_line_width(9)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(*rgb(p["tx"]), .12)
        cr.arc(52, 52, 42, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgb(*rgb(p["bad"] if pct > 90 else S["a"]))
        cr.arc(52, 52, 42, -math.pi / 2, -math.pi / 2 + 2 * math.pi * min(pct, 100) / 100)
        cr.stroke()
        cr.set_source_rgb(*rgb(p["tx"]))
        cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(22)
        t = "%d%%" % round(pct)
        e = cr.text_extents(t)
        cr.move_to(52 - e.width / 2 - e.x_bearing, 59)
        cr.show_text(t)
    a.set_draw_func(draw)
    b.append(a)
    for t, c in ((name, "b"), (sub, "dim")):
        l = lbl(t, c)
        l.set_halign(CENTER)
        b.append(l)
    return b


# ---------- Seiten: (Daten holen im Hintergrund, Widgets bauen) ----------
def b_overview(d, w):
    s, ds = d
    r = next((x for x in ds if x["mount"] == "/"), ds[0] if ds else {"size": 1, "used": 0})
    hr = time.localtime().tm_hour
    hero = Gtk.Box(orientation=V, spacing=2)
    hero.append(lbl("Guten Morgen" if hr < 11 else "Guten Tag" if hr < 18 else "Guten Abend", "dim"))
    hero.append(lbl(s["host"], "h1"))
    ok = Gtk.Box(spacing=8)
    ok.append(dot("ok"))
    ok.append(lbl("System läuft", "ok"))
    hero.append(ok)
    rings = Gtk.Box(spacing=12, homogeneous=True)
    rings.append(ring("Prozessor", s["cpu"], "Last %s" % s["load"][0]))
    rings.append(ring("Arbeitsspeicher", s["mem"]["used"] / s["mem"]["total"] * 100, f'{gb(s["mem"]["used"])} von {gb(s["mem"]["total"])}'))
    rings.append(ring("Speicher", r["used"] / max(r["size"], 1) * 100, f'{gb(r["used"])} von {gb(r["size"])}'))
    g = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
    info = (("Betriebssystem", s["os"]), ("Laufzeit", dur(s["uptime"])), ("IP-Adresse", s["ip"] or "–"),
            ("Last (1/5/15 Min)", " · ".join(map(str, s["load"]))))
    for i, (k, v) in enumerate(info):
        c = Gtk.Box(orientation=V)
        c.add_css_class("card")
        c.append(lbl(k, "dim", "small"))
        c.append(lbl(v, "b"))
        g.attach(c, i % 2, i // 2, 1, 1)
    return [hero, rings, g]


def b_services(d, w):
    e = Gtk.SearchEntry()
    e.set_placeholder_text("Dienste filtern")
    e.set_text(w.q)
    lst = Gtk.Box(orientation=V, spacing=2)

    def fill(*_):
        w.q = e.get_text().lower()
        clear(lst)
        for x in sorted(d, key=lambda x: (x["active"] != "failed", x["name"])):
            if w.q not in (x["name"] + x["desc"]).lower():
                continue
            nm, run = x["name"], x["active"] == "running"
            box = Gtk.Box(spacing=6)
            if not w.sh.admin:
                pass
            elif run:
                box.append(btn("Neustart", lambda nm=nm: w.sh.act(w, nm, "restart")))
                box.append(btn("Stopp", lambda nm=nm: w.sh.act(w, nm, "stop")))
            else:
                box.append(btn("Start", lambda nm=nm: w.sh.act(w, nm, "start"), True))
            lst.append(row(nm.removesuffix(".service"), x["desc"], box, dot("ok" if run else "bad" if x["active"] == "failed" else "")))
    e.connect("search-changed", fill)
    fill()
    return [e, lst]


def b_disks(d, w):
    out = []
    for x in d:
        p = x["used"] / max(x["size"], 1)
        c = Gtk.Box(orientation=V, spacing=4)
        c.add_css_class("card")
        h = Gtk.Box()
        l = lbl(x["mount"], "b")
        l.set_hexpand(True)
        h.append(l)
        h.append(lbl(x["src"], "dim"))
        c.append(h)
        pb = Gtk.ProgressBar()
        pb.set_fraction(min(p, 1))
        c.append(pb)
        c.append(lbl(f'{gb(x["used"])} von {gb(x["size"])} belegt · {round(p * 100)} %', "dim"))
        out.append(c)
    return out


def b_net(d, w):
    out = []
    for x in d:
        c = Gtk.Box(orientation=V, spacing=4)
        c.add_css_class("card")
        h = Gtk.Box()
        l = lbl(x["name"], "b")
        l.set_hexpand(True)
        h.append(l)
        h.append(lbl(x["state"], "tag", "ok" if x["state"] == "UP" else "dim"))
        c.append(h)
        c.append(lbl(x["mac"], "dim"))
        c.append(lbl("\n".join(x["addrs"]), "mono"))
        out.append(c)
    return out


def b_users(d, w):
    out = []
    for x in d:
        a = lbl(x["name"][:1].upper(), "av")
        a.set_xalign(.5)
        a.set_halign(CENTER)
        a.set_valign(CENTER)
        out.append(row(x["name"], x["home"], lbl(f'UID {x["uid"]} · {x["shell"]}', "dim"), a))
    return out


def b_updates(u, w):
    if u["running"]:
        GLib.timeout_add(2500, lambda: (w.alive and w.refresh(), False)[1])
    c = Gtk.Box(spacing=16)
    c.add_css_class("card")
    t = Gtk.Box(orientation=V)
    t.set_hexpand(True)
    t.append(lbl("Updates werden installiert …" if u["running"] else f'{u["count"]} Updates verfügbar' if u["count"] else "Alles aktuell", "h2"))
    t.append(lbl("Das kann einige Minuten dauern." if u["running"] else "Sicherheits- und Systemaktualisierungen" if u["count"] else "Es sind keine Updates nötig.", "dim"))
    c.append(t)
    if u["count"] and not u["running"] and w.sh.admin:
        c.append(btn("Jetzt installieren", w.sh.run_updates, True))
    lst = Gtk.Box(orientation=V, spacing=2)
    for p in u["pkgs"]:
        lst.append(row(p["name"], "", lbl(f'{p["old"]} → {p["new"]}', "dim")))
    return [c, lst]


def b_logs(d, w):
    e = Gtk.SearchEntry()
    e.set_placeholder_text("Protokoll durchsuchen")
    e.set_text(w.q)
    lst = Gtk.Box(orientation=V)

    def fill(*_):
        w.q = e.get_text().lower()
        clear(lst)
        for x in d:
            if w.q in x.lower():
                low = x.lower()
                lst.append(lbl(x, "mono", *(["bad"] if any(k in low for k in ("error", "fail", "fehler")) else ["warn"] if "warn" in low else [])))
    e.connect("search-changed", fill)
    fill()
    return [e, lst]


def b_ai(d, w):
    if not w.sh.admin:
        return [lbl("Dieser Bereich ist nur für Administratoren.", "dim")]
    st, out = d["status"], []
    run = st["service"] == "active"
    c = Gtk.Box(spacing=16)
    c.add_css_class("card")
    t = Gtk.Box(orientation=V)
    t.set_hexpand(True)
    t.append(lbl("AI Core läuft" if run else "AI Core ist gestoppt", "h2", "ok" if run else "bad"))
    t.append(lbl(f'Aktive Version: {st["active"] or "keine"} · Port {st["port_no"]}' + ("" if st["port"] else " · antwortet nicht"), "dim"))
    c.append(t)
    if st["active"]:
        c.append(btn("Neustart", lambda: w.sh.ai(w, "Neustart", zosai.restart)))
    if st["previous"]:
        c.append(btn("Zurück auf " + st["previous"], lambda: w.sh.ai(w, "Zurücksetzen", zosai.rollback)))
    out.append(c)
    out.append(lbl("Neue Version bereitstellen: ZIP in den Ordner /srv/zos/inbox kopieren, zum Beispiel mit scp.", "dim", "small"))
    if d["inbox"]:
        out.append(lbl("Bereit zum Einspielen", "b"))
        for x in d["inbox"]:
            out.append(row(x["name"], gb(x["size"]), btn("Einspielen und aktivieren", lambda p=x["path"]: w.sh.ai(w, "Einspielen", zosai.install_and_activate, p), True)))
    out.append(lbl("Versionen", "b"))
    for v in d["versions"]:
        right = Gtk.Box(spacing=6)
        if v["active"]:
            right.append(lbl("aktiv", "tag", "ok"))
        else:
            right.append(btn("Aktivieren", lambda n=v["name"]: w.sh.ai(w, "Aktivieren", zosai.activate, n)))
            right.append(btn("Löschen", lambda n=v["name"]: w.sh.ai(w, "Löschen", zosai.delete, n)))
        out.append(row(v["name"], "" if v["deps"] else "Abhängigkeiten fehlen", right, dot("ok" if v["active"] else "")))
    if not d["versions"]:
        out.append(lbl("Noch keine Version eingespielt.", "dim"))
    if d["logs"]:
        out.append(lbl("\n".join(d["logs"]), "mono", "dim"))
    return out


def qr_widget(text):
    try:
        import qrcode
        q = qrcode.QRCode(border=2)
        q.add_data(text)
        q.make(fit=True)
        mx = q.get_matrix()
    except Exception:
        return lbl("(QR-Code nicht verfügbar, bitte den Schlüssel eintippen)", "dim", "small")
    a = Gtk.DrawingArea()
    a.set_content_width(190)
    a.set_content_height(190)
    a.set_halign(CENTER)

    def draw(_a, cr, w, h, *_):
        sz = 190 / len(mx)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.set_source_rgb(0, 0, 0)
        for y, r in enumerate(mx):
            for x, v in enumerate(r):
                if v:
                    cr.rectangle(x * sz, y * sz, sz + .5, sz + .5)
        cr.fill()
    a.set_draw_func(draw)
    return a


def b_security(d, w):
    fw, ip = d
    u = w.sh.user

    def card(*kids):
        c = Gtk.Box(orientation=V, spacing=8)
        c.add_css_class("card")
        for k in kids:
            c.append(k)
        return c
    out = [card(lbl("Konto", "b"), lbl(f'Angemeldet als {u} · {"Administrator" if w.sh.admin else "Benutzer"}', "dim"))]
    code = Gtk.Entry()
    code.set_placeholder_text("6-stelliger Code")
    kids = [lbl("Zwei-Faktor-Anmeldung", "b")]
    if zossec.has_totp(u):
        kids += [lbl("Aktiv. Beim Anmelden wird zusätzlich ein Code aus der Authenticator-App verlangt.", "dim"), code,
                 btn("Deaktivieren", lambda: w.sh.totp_off(w, code.get_text()))]
    elif getattr(w, "pend", None):
        kids += [lbl("QR-Code mit einer Authenticator-App scannen (oder den Schlüssel eintippen) und mit einem Code bestätigen.", "dim"),
                 qr_widget(zossec.uri(u, w.pend)), lbl(w.pend, "mono"), code,
                 btn("Bestätigen", lambda: w.sh.totp_on(w, code.get_text()), True)]
    else:
        kids += [lbl("Nicht aktiv. Für Administratoren empfohlen.", "dim"),
                 btn("Einrichten", lambda: (setattr(w, "pend", zossec.new_secret()), w.refresh()), True)]
    out.append(card(*kids))
    seg = Gtk.Box(spacing=6)
    for v in (0, 5, 10, 30):
        seg.append(btn("Aus" if v == 0 else f"{v} Min", lambda v=v: w.sh.set_lock(v, w), S.get("lock", 10) == v))
    out.append(card(lbl("Automatische Sperre", "b"), lbl("Sperrt den Bildschirm nach Inaktivität.", "dim"), seg))
    out.append(card(lbl("Fernzugriff", "b"), lbl(f"https://{ip or 'SERVER-IP'}:6080/vnc.html", "mono"),
                    lbl("Verschlüsselt (HTTPS). Das Zertifikat ist selbst erstellt, der Browser warnt einmalig. Danach folgen das VNC-Passwort und die Anmeldung am Desktop.", "dim", "small")))
    out.append(card(lbl("Firewall", "b"), lbl("\n".join(fw[:12]), "mono")))
    return out


PAGES = {"overview": (lambda: (zoscore.system(), zoscore.disks()), b_overview), "services": (zoscore.services, b_services),
         "disks": (zoscore.disks, b_disks), "net": (zoscore.net, b_net), "users": (zoscore.users, b_users),
         "updates": (zoscore.updates, b_updates), "ai": (zosai.overview, b_ai),
         "security": (lambda: (zossec.firewall(), zoscore.system()["ip"]), b_security), "logs": (lambda: zoscore.logs(150), b_logs)}


# ---------- Fenster ----------
class Win(Gtk.Box):
    def __init__(self, sh, wid, title, ico):
        super().__init__(orientation=V)
        self.sh, self.id, self.q, self.alive, self.maxed = sh, wid, "", True, False
        self.add_css_class("mica")
        self.set_size_request(min(780, sh.W - 24), min(520, sh.H - 90))
        tb = Gtk.Box(spacing=8)
        tb.add_css_class("tb")
        tb.append(icon(ico, 16))
        t = lbl(title, "b")
        t.set_hexpand(True)
        t.set_valign(CENTER)
        tb.append(t)
        for nm, cb, cls in (("view-refresh-symbolic", self.refresh, ""), ("window-minimize-symbolic", self.minimize, ""),
                            ("window-maximize-symbolic", self.toggle_max, ""), ("window-close-symbolic", self.close, "x")):
            b = Gtk.Button.new_from_icon_name(nm)
            if cls:
                b.add_css_class(cls)
            b.connect("clicked", lambda *_, cb=cb: cb())
            tb.append(b)
        self.append(tb)
        sc = Gtk.ScrolledWindow()
        sc.set_vexpand(True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.holder = Gtk.Box(orientation=V, spacing=10)
        for m in ("start", "end", "top", "bottom"):
            getattr(self.holder, "set_margin_" + m)(18)
        sc.set_child(self.holder)
        self.append(sc)
        d = Gtk.GestureDrag()
        d.connect("drag-begin", self.on_db)
        d.connect("drag-update", self.on_du)
        tb.add_controller(d)
        c = Gtk.GestureClick()
        c.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        c.connect("released", lambda *_: sh.focus(self))
        self.add_controller(c)

    def on_db(self, g, x, y):
        self._p = self.sh.fixed.get_child_position(self)

    def on_du(self, g, dx, dy):
        if not self.maxed:
            self.sh.fixed.move(self, max(0, min(self.sh.W - 80, self._p[0] + dx)), max(0, min(self.sh.H - 110, self._p[1] + dy)))

    def refresh(self):
        fetch, build = PAGES[self.id]

        def done(data, err):
            if not self.alive:
                return
            clear(self.holder)
            if err:
                self.holder.append(lbl(str(err), "bad"))
                return
            for wd in build(data, self):
                self.holder.append(wd)
        bg(fetch, done)

    def minimize(self):
        self.set_visible(False)
        self.sh.top = None
        self.sh.tbar()

    def toggle_max(self):
        f = self.sh.fixed
        if not self.maxed:
            self._rest = (f.get_child_position(self), self.get_size_request())
            f.move(self, 0, 0)
            self.set_size_request(self.sh.W, self.sh.H - 54)
        else:
            f.move(self, *self._rest[0])
            self.set_size_request(*self._rest[1])
        self.maxed = not self.maxed

    def close(self):
        self.alive = False
        self.sh.fixed.remove(self)
        del self.sh.wins[self.id]
        if self.sh.top == self.id:
            self.sh.top = None
        self.sh.tbar()


# ---------- Desktop ----------
def draw_wall(_a, cr, w, h, *_):
    p = PAL[S["t"]]
    cr.set_source_rgb(*rgb(p["bg"]))
    cr.paint()
    c1, c2, c3 = p["w"]
    for cx, cy, r, col, a in ((.15, .15, .60, c1, 1), (.88, .25, .60, c2, 1), (.55, 1.0, .70, c3, 1),
                              (.50, .44, .46, c1, .5), (.62, .50, .40, c2, .4), (.42, .56, .40, c3, .4)):
        g = cairo.RadialGradient(cx * w, cy * h, 0, cx * w, cy * h, r * max(w, h))
        g.add_color_stop_rgba(0, *rgb(col), a)
        g.add_color_stop_rgba(1, *rgb(col), 0)
        cr.set_source(g)
        cr.paint()


def draw_logo(_a, cr, w, h, *_):
    cr.set_source_rgb(*rgb(S["a"]))
    s, r = 8.2, 1.6
    for x, y in ((1, 1), (10.8, 1), (1, 10.8), (10.8, 10.8)):
        cr.new_sub_path()
        cr.arc(x + s - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + s - r, y + s - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + s - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.fill()


class Shell(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="de.zos.shell", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.wins, self.top, self.n, self.prov, self.tt = {}, None, 0, None, 0
        self.user, self.admin, self.locked, self.pwr = None, False, True, []
        self.failed, self.svc_cache, self.last_input = set(), [], time.time()

    def do_activate(self):
        self.win = Gtk.ApplicationWindow(application=self)
        self.win.set_decorated(False)
        g = Gdk.Display.get_default().get_monitors().get_item(0).get_geometry()
        self.W, self.H = g.width, g.height
        self.win.set_default_size(self.W, self.H)
        ov = Gtk.Overlay()
        self.wall = Gtk.DrawingArea()
        self.wall.set_draw_func(draw_wall)
        ov.set_child(self.wall)
        self.fixed = Gtk.Fixed()
        c = Gtk.GestureClick()
        c.connect("pressed", lambda *_: self.close_menus())
        self.fixed.add_controller(c)
        ov.add_overlay(self.fixed)
        self.build_menu(ov)
        self.build_bar(ov)
        self.toast_l = lbl("", "toast")
        self.toast_l.set_halign(CENTER)
        self.toast_l.set_valign(END)
        self.toast_l.set_margin_bottom(70)
        self.toast_l.set_visible(False)
        ov.add_overlay(self.toast_l)
        self.build_lock(ov)
        k = Gtk.EventControllerKey()
        k.connect("key-pressed", self.on_key)
        self.win.add_controller(k)
        m = Gtk.EventControllerMotion()
        m.connect("motion", lambda *_: setattr(self, "last_input", time.time()))
        self.win.add_controller(m)
        self.win.set_child(ov)
        self.theme()
        self.win.present()
        self.win.fullscreen()
        self.tick()
        GLib.timeout_add_seconds(10, self.tick)
        GLib.timeout_add_seconds(3, self.tick_ov)
        GLib.timeout_add_seconds(20, self.tick_alerts)
        self.lock()

    # Startmenü und Schnellpanel
    def build_menu(self, ov):
        sm = Gtk.Box(orientation=V, spacing=10)
        sm.add_css_class("mica")
        sm.add_css_class("menu")
        sm.set_halign(CENTER)
        sm.set_valign(END)
        sm.set_margin_bottom(64)
        sm.set_size_request(min(580, self.W - 20), -1)
        sm.set_visible(False)
        self.sm = sm
        self.sq = Gtk.SearchEntry()
        self.sq.set_placeholder_text("Apps und Einstellungen suchen")
        sm.append(self.sq)
        sm.append(lbl("Angepinnt", "b"))
        fb = Gtk.FlowBox()
        fb.set_selection_mode(Gtk.SelectionMode.NONE)
        fb.set_min_children_per_line(4)
        fb.set_max_children_per_line(4)
        fb.set_homogeneous(True)
        for app in APPS:
            b = Gtk.Button()
            b.add_css_class("tile")
            b.app = app
            v = Gtk.Box(orientation=V, spacing=8)
            i = Gtk.Box()
            i.add_css_class("tilei")
            i.set_halign(CENTER)
            im = icon(app[2], 24)
            im.set_hexpand(True)
            i.append(im)
            v.append(i)
            v.append(lbl(app[1]))
            b.set_child(v)
            b.connect("clicked", lambda *_, a=app[0]: self.open(a))
            fb.append(b)
        fb.set_filter_func(lambda ch: self.sq.get_text().lower() in ch.get_child().app[1].lower())
        self.sq.connect("search-changed", lambda *_: self.on_search(fb))
        self.sq.connect("activate", lambda *_: next((self.open(a[0]) for a in APPS if self.sq.get_text().lower() in a[1].lower()), None))
        sm.append(fb)
        self.res = Gtk.Box(orientation=V, spacing=2)
        sm.append(self.res)
        foot = Gtk.Box(spacing=10)
        av = lbl("A", "av")
        av.set_xalign(.5)
        foot.append(av)
        u = lbl("Administrator", "b")
        u.set_hexpand(True)
        u.set_valign(CENTER)
        foot.append(u)
        for name, cmd in (("Neustart", "systemctl reboot"), ("Herunterfahren", "systemctl poweroff")):
            b = Gtk.Button(label=name)
            b.add_css_class("btn")
            b.connect("clicked", lambda b, n=name, c=cmd: self.power(b, n, c))
            foot.append(b)
            self.pwr.append(b)
            b.set_visible(False)
        lk = Gtk.Button(label="Sperren")
        lk.add_css_class("btn")
        lk.connect("clicked", lambda *_: self.lock())
        foot.append(lk)
        sm.append(foot)
        ov.add_overlay(sm)
        qp = Gtk.Box(orientation=V, spacing=12)
        qp.add_css_class("mica")
        qp.add_css_class("menu")
        qp.set_halign(END)
        qp.set_valign(END)
        qp.set_margin_bottom(64)
        qp.set_margin_end(10)
        qp.set_size_request(280, -1)
        qp.set_visible(False)
        self.qp = qp
        ov.add_overlay(qp)

    def build_qp(self):
        clear(self.qp)
        self.qp.append(lbl("Design", "b"))
        seg = Gtk.Box(spacing=6, homogeneous=True)
        for t, name in (("light", "Hell"), ("dark", "Dunkel")):
            seg.append(btn(name, lambda t=t: self.set_theme(t=t), S["t"] == t))
        self.qp.append(seg)
        sw = Gtk.Box(spacing=10)
        for c in ACC:
            a = Gtk.DrawingArea()
            a.set_content_width(28)
            a.set_content_height(28)

            def draw(_a, cr, w, h, *_, c=c):
                cr.set_source_rgb(*rgb(c))
                cr.arc(14, 14, 11, 0, 2 * math.pi)
                cr.fill()
                if S["a"] == c:
                    cr.set_source_rgb(*rgb(PAL[S["t"]]["tx"]))
                    cr.set_line_width(2)
                    cr.arc(14, 14, 13, 0, 2 * math.pi)
                    cr.stroke()
            a.set_draw_func(draw)
            g = Gtk.GestureClick()
            g.connect("pressed", lambda *_, c=c: self.set_theme(a=c))
            a.add_controller(g)
            sw.append(a)
        self.qp.append(sw)
        self.qp.append(lbl("Textgröße", "b"))
        sz = Gtk.Box(spacing=6, homogeneous=True)
        for v in (100, 125, 150):
            sz.append(btn(f"{v} %", lambda v=v: self.set_theme(sc=v), S.get("sc", 100) == v))
        self.qp.append(sz)
        self.qp.append(btn("Animationen: " + ("an" if S.get("an", True) else "aus"), lambda: self.set_theme(an=not S.get("an", True))))
        self.qp.append(lbl("Lokal, ohne Netzwerk nutzbar.", "dim", "small"))

    def set_theme(self, t=None, a=None, sc=None, an=None):
        S["t"] = t or S["t"]
        S["a"] = a or S["a"]
        S["sc"] = sc or S.get("sc", 100)
        S["an"] = S.get("an", True) if an is None else an
        self.theme()
        self.build_qp()

    def theme(self):
        k = S.get("sc", 100) / 100
        on = S.get("an", True)
        css = CSS.safe_substitute(ac=S["a"], fs=round(14 * k), fs2=round(12 * k), h1=round(30 * k), h2=round(20 * k),
                                  anim="animation: pop 160ms ease-out;" if on else "",
                                  trans="transition: background 120ms ease, border-color 120ms ease;" if on else "",
                                  **{k2: v for k2, v in PAL[S["t"]].items() if k2 != "w"})
        prov = Gtk.CssProvider()
        try:
            prov.load_from_string(css)
        except AttributeError:
            prov.load_from_data(css.encode())
        disp = Gdk.Display.get_default()
        if self.prov:
            Gtk.StyleContext.remove_provider_for_display(disp, self.prov)
        Gtk.StyleContext.add_provider_for_display(disp, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.prov = prov
        self.wall.queue_draw()
        self.logo.queue_draw()
        for w in self.wins.values():
            w.refresh()
        save()

    # Taskleiste
    def build_bar(self, ov):
        bar = self.bar = Gtk.CenterBox()
        bar.add_css_class("taskbar")
        bar.set_valign(END)
        mid = Gtk.Box(spacing=2)
        st = Gtk.Button()
        st.add_css_class("ti")
        self.logo = Gtk.DrawingArea()
        self.logo.set_content_width(20)
        self.logo.set_content_height(20)
        self.logo.set_draw_func(draw_logo)
        st.set_child(self.logo)
        st.connect("clicked", lambda *_: self.toggle_menu(self.sm))
        self.apps = Gtk.Box(spacing=2)
        mid.append(st)
        mid.append(self.apps)
        bar.set_center_widget(mid)
        tray = Gtk.Button()
        tray.add_css_class("ti")
        tb = Gtk.Box(spacing=10)
        tb.append(icon("network-wired-symbolic", 18))
        self.badge = lbl("", "tag", "bad")
        self.badge.set_visible(False)
        tb.append(self.badge)
        cl = Gtk.Box(orientation=V)
        self.ck, self.dt = lbl("", "b", "small"), lbl("", "dim", "small")
        cl.append(self.ck)
        cl.append(self.dt)
        tb.append(cl)
        tray.set_child(tb)
        tray.connect("clicked", lambda *_: (self.build_qp(), self.toggle_menu(self.qp)))
        bar.set_end_widget(tray)
        ov.add_overlay(bar)
        self.tbar()

    def tbar(self):
        clear(self.apps)
        for wid, name, ico in APPS:
            b = Gtk.Button()
            b.add_css_class("ti")
            b.set_child(icon(ico, 22))
            b.set_tooltip_text(name)
            w = self.wins.get(wid)
            if w:
                b.add_css_class("on")
                if w.get_visible() and self.top == wid:
                    b.add_css_class("act")
            b.connect("clicked", lambda *_, i=wid: self.toggle(i))
            self.apps.append(b)

    def toggle_menu(self, m):
        show = not m.get_visible()
        self.close_menus()
        m.set_visible(show)
        if show and m is self.sm:
            self.sq.set_text("")
            self.sq.grab_focus()

    def close_menus(self):
        self.sm.set_visible(False)
        self.qp.set_visible(False)

    def toggle(self, wid):
        w = self.wins.get(wid)
        if w and w.get_visible() and self.top == wid:
            w.minimize()
        elif w:
            w.set_visible(True)
            self.focus(w)
        else:
            self.open(wid)

    def open(self, wid):
        self.close_menus()
        if wid in self.wins:
            self.wins[wid].set_visible(True)
            return self.focus(self.wins[wid])
        _, name, ico = next(a for a in APPS if a[0] == wid)
        w = Win(self, wid, name, ico)
        self.wins[wid] = w
        self.fixed.put(w, 60 + (self.n % 6) * 34, 36 + (self.n % 6) * 30)
        self.n += 1
        self.top = wid
        self.tbar()
        w.refresh()

    def focus(self, w):
        if self.top != w.id:
            pos = self.fixed.get_child_position(w)
            self.fixed.remove(w)
            self.fixed.put(w, *pos)
            self.top = w.id
        self.tbar()

    # Aktionen
    def act(self, w, name, action):
        if not self.admin:
            return self.toast("Nur Administratoren dürfen das.")
        done = {"start": "gestartet", "stop": "gestoppt", "restart": "neu gestartet"}[action]

        def cb(_r, err):
            self.toast(str(err) if err else f"{name.removesuffix('.service')}: {done}")
            w.refresh()
        bg(lambda: zoscore.svc_action(name, action), cb)

    def run_updates(self):
        if not self.admin:
            return self.toast("Nur Administratoren dürfen das.")
        def cb(_r, err):
            self.toast(str(err) if err else "Updates gestartet")
            w = self.wins.get("updates")
            if w:
                w.refresh()
        bg(zoscore.run_updates, cb)

    def power(self, b, name, cmd):
        if not self.admin:
            return self.toast("Nur Administratoren dürfen das.")
        if b.get_label() != "Bestätigen":
            b.set_label("Bestätigen")
            GLib.timeout_add_seconds(3, lambda: (b.set_label(name), False)[1])
        else:
            os.system(cmd)

    def toast(self, msg):
        self.tt += 1
        n = self.tt
        self.toast_l.set_label(msg)
        self.toast_l.set_visible(True)
        GLib.timeout_add(3200, lambda: (n == self.tt and self.toast_l.set_visible(False), False)[1])

    # ---- Sperrbildschirm und Anmeldung ----
    def build_lock(self, ov):
        L = Gtk.Box(orientation=V, spacing=24)
        L.add_css_class("lock")
        top = Gtk.Box(orientation=V)
        top.set_margin_top(max(40, self.H // 9))
        self.lk_clock, self.lk_date = lbl("", "clock", "onscrim"), lbl("", "lockdate", "onscrim")
        for l in (self.lk_clock, self.lk_date):
            l.set_halign(CENTER)
            top.append(l)
        L.append(top)
        card = Gtk.Box(orientation=V, spacing=8)
        card.add_css_class("mica")
        card.add_css_class("menu")
        card.set_halign(CENTER)
        card.set_size_request(340, -1)
        av = lbl("A", "av")
        av.set_xalign(.5)
        av.set_halign(CENTER)
        card.append(av)
        self.lk_user = Gtk.Entry()
        self.lk_user.set_placeholder_text("Benutzername")
        self.lk_pw = Gtk.PasswordEntry()
        self.lk_pw.set_show_peek_icon(True)
        self.lk_code = Gtk.Entry()
        self.lk_code.set_placeholder_text("Code aus der Authenticator-App")
        self.lk_code.set_visible(False)
        self.lk_msg = lbl("", "bad")
        for wd in (self.lk_user, self.lk_pw, self.lk_code):
            wd.connect("activate", self.try_login)
        for wd in (lbl("Benutzername", "dim", "small"), self.lk_user, lbl("Passwort", "dim", "small"), self.lk_pw,
                   self.lk_code, self.lk_msg, btn("Anmelden", self.try_login, True)):
            card.append(wd)
        L.append(card)
        self.lock_box = L
        ov.add_overlay(L)

    def lock(self):
        self.locked = True
        self.close_menus()
        self.fixed.set_visible(False)
        self.bar.set_visible(False)
        self.lock_box.set_visible(True)
        users = zossec.login_users()
        self.lk_user.set_text(S.get("u") or (users[0] if users else ""))
        self.lk_pw.set_text("")
        self.lk_code.set_text("")
        self.lk_code.set_visible(False)
        self.lk_msg.set_label("")
        self.update_clock()
        self.lk_pw.grab_focus()

    def try_login(self, *_):
        u, code = self.lk_user.get_text().strip(), self.lk_code.get_text().strip()
        st, msg = zossec.authenticate(u, self.lk_pw.get_text(), code or None)
        if st == "ok":
            self.user, self.admin, self.locked = u, zossec.is_admin(u), False
            S["u"] = u
            save()
            self.lock_box.set_visible(False)
            self.fixed.set_visible(True)
            self.bar.set_visible(True)
            for b in self.pwr:
                b.set_visible(self.admin)
            self.last_input = time.time()
            if self.wins:
                for w in self.wins.values():
                    w.refresh()
            else:
                self.open("overview")
            self.tick_alerts()
        elif st == "need_code":
            self.lk_code.set_visible(True)
            self.lk_code.grab_focus()
            self.lk_msg.set_label("Bitte den Code eingeben.")
        else:
            self.lk_msg.set_label(msg)
            self.lk_pw.set_text("")
            self.lk_code.set_text("")

    def on_key(self, c, kv, kc, st):
        self.last_input = time.time()
        if self.locked:
            return False
        if kv == Gdk.KEY_Escape:
            self.close_menus()
        elif kv in (Gdk.KEY_Super_L, Gdk.KEY_Super_R):
            self.toggle_menu(self.sm)
        elif kv == Gdk.KEY_l and st & Gdk.ModifierType.CONTROL_MASK:
            self.lock()
        return False

    # ---- Benachrichtigungen, Suche, Sicherheit, AI-Core ----
    def tick_alerts(self):
        if not self.locked:
            def cb(r, err):
                if err:
                    return
                self.svc_cache = r
                bad = {x["name"] for x in r if x["active"] == "failed"}
                for n in sorted(bad - self.failed):
                    self.toast("Dienst ausgefallen: " + n.removesuffix(".service"))
                self.failed = bad
                self.badge.set_label(str(len(bad)))
                self.badge.set_visible(bool(bad))
            bg(zoscore.services, cb)
        return True

    def on_search(self, fb):
        fb.invalidate_filter()
        clear(self.res)
        q = self.sq.get_text().lower().strip()
        if len(q) < 2:
            return
        for x in [x for x in self.svc_cache if q in (x["name"] + x["desc"]).lower()][:5]:
            b = Gtk.Button()
            b.add_css_class("tile")
            b.set_child(lbl("Dienst: " + x["name"].removesuffix(".service")))
            b.connect("clicked", lambda *_, n=x["name"]: self.open_service(n))
            self.res.append(b)

    def open_service(self, name):
        self.open("services")
        w = self.wins["services"]
        w.q = name.removesuffix(".service").lower()
        w.refresh()

    def ai(self, w, what, fn, *a):
        if not self.admin:
            return self.toast("Nur Administratoren dürfen das.")
        self.toast(what + " …")

        def cb(_r, err):
            self.toast(f"{what}: {err}" if err else f"{what}: fertig")
            w.refresh()
        bg(lambda: fn(*a), cb)

    def totp_on(self, w, code):
        sec = getattr(w, "pend", None)
        if sec and zossec.totp_verify(sec, code, user=self.user):
            zossec.set_secret(self.user, sec)
            w.pend = None
            self.toast("Zwei-Faktor ist aktiv.")
        else:
            self.toast("Der Code stimmt nicht.")
        w.refresh()

    def totp_off(self, w, code):
        if zossec.totp_verify(zossec.get_secret(self.user), code, user=self.user):
            zossec.remove_secret(self.user)
            self.toast("Zwei-Faktor ist aus.")
        else:
            self.toast("Der Code stimmt nicht.")
        w.refresh()

    def set_lock(self, v, w):
        S["lock"] = v
        save()
        w.refresh()

    def update_clock(self):
        t, d = time.strftime("%H:%M"), time.strftime("%d.%m.%Y")
        self.ck.set_label(t)
        self.dt.set_label(d)
        self.lk_clock.set_label(t)
        self.lk_date.set_label(d)

    def tick(self):
        self.update_clock()
        m = S.get("lock", 10)
        if not self.locked and m and time.time() - self.last_input > m * 60:
            self.lock()
        return True

    def tick_ov(self):
        w = self.wins.get("overview")
        if w and w.get_visible():
            w.refresh()
        return True


if __name__ == "__main__":
    sys.exit(Shell().run(sys.argv))
