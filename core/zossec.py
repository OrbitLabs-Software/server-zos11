#!/usr/bin/env python3
"""zossec - Anmeldung, Rechte und Zwei-Faktor (TOTP) fuer die zOS-Oberflaeche."""
import base64, grp, hmac, os, pwd, secrets, struct, subprocess, time, warnings
from urllib.parse import quote

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        import crypt
    except ImportError:  # Python 3.13+ hat crypt entfernt (Ubuntu 24.04 hat 3.12)
        crypt = None

SHADOW = os.environ.get("ZOS_SHADOW", "/etc/shadow")
TOTP_DIR = os.environ.get("ZOS_TOTP_DIR", "/etc/zos/totp")
MAX_FAIL, LOCK_SECONDS = 5, 60
_fails = {}          # Benutzer -> (Fehlversuche, gesperrt bis)
_last_counter = {}   # Benutzer -> zuletzt benutzter TOTP-Zaehler (gegen Wiederverwendung)


# ---------- Passwort und Rechte ----------
def _hash(user):
    try:
        with open(SHADOW, encoding="utf-8") as f:
            for line in f:
                p = line.rstrip("\n").split(":")
                if len(p) > 1 and p[0] == user:
                    return p[1]
    except OSError:
        pass
    return ""


def verify_password(user, password):
    h = _hash(user)
    if crypt is None or not h or h[0] in "!*":
        return False
    try:
        calc = crypt.crypt(password, h)
    except Exception:
        return False
    return bool(calc) and hmac.compare_digest(calc, h)


def is_admin(user):
    try:
        u = pwd.getpwnam(user)
    except KeyError:
        return False
    if u.pw_uid == 0:
        return True
    try:
        g = grp.getgrnam("sudo")
    except KeyError:
        return False
    return user in g.gr_mem or u.pw_gid == g.gr_gid


def login_users():
    return [u.pw_name for u in pwd.getpwall()
            if 1000 <= u.pw_uid < 65534 and not u.pw_shell.endswith(("nologin", "false"))]


# ---------- Zwei-Faktor (TOTP, RFC 6238) ----------
def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret, t=None, digits=6, step=30):
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    n = int((time.time() if t is None else t) // step)
    h = hmac.new(key, struct.pack(">Q", n), "sha1").digest()
    o = h[-1] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digits).zfill(digits)


def totp_verify(secret, code, user=None, now=None, window=1, step=30):
    now = time.time() if now is None else now
    code = "".join(c for c in str(code) if c.isdigit())
    if len(code) != 6:
        return False
    n = int(now // step)
    for d in range(-window, window + 1):
        if hmac.compare_digest(totp_code(secret, (n + d) * step), code):
            if user is not None:
                if _last_counter.get(user, -1) >= n + d:
                    return False  # derselbe Code darf nicht zweimal benutzt werden
                _last_counter[user] = n + d
            return True
    return False


def uri(user, secret):
    return "otpauth://totp/%s?secret=%s&issuer=%s" % (quote("zOS Server:" + user), secret, quote("zOS Server"))


def _path(user):
    if not user or "/" in user or user.startswith("."):
        raise ValueError("Ungueltiger Benutzername")
    return os.path.join(TOTP_DIR, user)


def has_totp(user):
    return os.path.isfile(_path(user))


def get_secret(user):
    try:
        with open(_path(user), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def set_secret(user, secret):
    os.makedirs(TOTP_DIR, mode=0o700, exist_ok=True)
    fd = os.open(_path(user), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(secret)


def remove_secret(user):
    try:
        os.remove(_path(user))
    except OSError:
        pass


# ---------- Anmeldung mit Sperre nach Fehlversuchen ----------
def _locked(user, now):
    c = _fails.get(user)
    if c and c[0] >= MAX_FAIL:
        if now < c[1]:
            return True
        del _fails[user]
    return False


def _fail(user, now):
    n = _fails.get(user, (0, 0))[0] + 1
    _fails[user] = (n, now + LOCK_SECONDS if n >= MAX_FAIL else 0)


def authenticate(user, password, code=None, now=None):
    """Gibt (Status, Meldung) zurueck. Status: ok, need_code, fail, locked."""
    now = time.time() if now is None else now
    if not user:
        return "fail", "Bitte einen Benutzernamen eingeben."
    if _locked(user, now):
        return "locked", "Zu viele Versuche. Bitte %d Sekunden warten." % (int(_fails[user][1] - now) + 1)
    if not verify_password(user, password):
        _fail(user, now)
        return "fail", "Benutzername oder Passwort ist falsch."
    sec = get_secret(user)
    if sec:
        if not code:
            return "need_code", ""
        if not totp_verify(sec, code, user=user, now=now):
            _fail(user, now)
            return "fail", "Der Code ist falsch."
    _fails.pop(user, None)
    return "ok", ""


def firewall():
    try:
        out = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ["Firewall-Status nicht verfügbar"]
    return [l.strip() for l in out.splitlines() if l.strip()] or ["Firewall-Status nicht verfügbar"]
