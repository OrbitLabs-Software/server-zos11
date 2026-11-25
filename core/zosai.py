#!/usr/bin/env python3
"""zosai - AI-Core-Versionen verwalten: einspielen, aktivieren, zuruecksetzen, loeschen."""
import json, os, re, shutil, socket, subprocess, tempfile, time, zipfile
from pathlib import Path

BASE = Path(os.environ.get("ZOS_AI_DIR", "/opt/ai-core"))
VERS = BASE / "versions"
CUR = BASE / "current"
STATE = BASE / "state.json"
INBOX = Path(os.environ.get("ZOS_INBOX", "/srv/zos/inbox"))
SERVICE = "ai-core"
PORT = int(os.environ.get("ZOS_AI_PORT", "3000"))
MAX_BYTES = 2 * 1024 ** 3
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")


def _run(*a, timeout=60, cwd=None):
    r = subprocess.run(a, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return r.returncode, (r.stdout + r.stderr).strip()


def _state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active": None, "previous": None}


def _save(st):
    BASE.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st), encoding="utf-8")


# ---- Hilfen, die sich in Tests ersetzen lassen ----
def install_deps(d):
    cmd = ["npm", "ci"] if (Path(d) / "package-lock.json").is_file() else ["npm", "install"]
    code, out = _run(*cmd, "--omit=dev", "--no-audit", "--no-fund", timeout=900, cwd=str(d))
    if code:
        raise RuntimeError("Abhängigkeiten konnten nicht installiert werden (Internet nötig): " + out[-300:])


def restart():
    code, out = _run("systemctl", "restart", SERVICE)
    if code:
        raise RuntimeError("Dienst konnte nicht neu starten: " + out[-200:])


def _port_open():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            return True
    except OSError:
        return False


def healthy(timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        if _port_open():
            time.sleep(2)  # Absturzschleifen erkennen
            return _port_open() and _run("systemctl", "is-active", SERVICE)[1] == "active"
        time.sleep(1)
    return False


# ---- Versionen ----
def _safe_extract(zpath, dest):
    with zipfile.ZipFile(zpath) as z:
        total = 0
        for i in z.infolist():
            p = Path(i.filename)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError("Ungültiger Pfad im ZIP: " + i.filename)
            total += i.file_size
        if total > MAX_BYTES:
            raise ValueError("Das ZIP ist zu groß.")
        z.extractall(dest)


def _find_root(tmp):
    for c in [tmp] + sorted(p for p in tmp.iterdir() if p.is_dir()):
        if (c / "package.json").is_file() and (c / "server" / "server.js").is_file():
            return c
    raise ValueError("Das ZIP enthält keinen AI-Core (package.json und server/server.js fehlen).")


def _free_name(ver):
    base = re.sub(r"[^A-Za-z0-9._-]", "-", str(ver)) or "version"
    name, n = base, 2
    while (VERS / name).exists():
        name, n = f"{base}-{n}", n + 1
    return name


def import_zip(zip_path):
    zp = Path(zip_path)
    if not zp.is_file() or zp.suffix.lower() != ".zip":
        raise ValueError("Das ist keine ZIP-Datei.")
    VERS.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=BASE, prefix=".import-"))
    try:
        _safe_extract(zp, tmp)
        root = _find_root(tmp)
        ver = json.loads((root / "package.json").read_text(encoding="utf-8")).get("version", "version")
        target = VERS / _free_name(ver)
        shutil.move(str(root), str(target))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        if not (target / "node_modules").is_dir():
            install_deps(target)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target.name


def _switch(name):
    tmp = BASE / ".current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(VERS / name)
    os.replace(tmp, CUR)


def activate(name):
    if not NAME.match(name) or not (VERS / name / "server" / "server.js").is_file():
        raise ValueError("Version nicht gefunden.")
    if not (VERS / name / "node_modules").is_dir():
        raise RuntimeError("Für diese Version fehlen die Abhängigkeiten.")
    before = _state()
    old = before.get("active")
    if old == name:
        return
    _switch(name)
    _save({"active": name, "previous": old})
    try:
        restart()
        ok = healthy()
    except RuntimeError:
        ok = False
    if not ok:
        if old and (VERS / old).is_dir():
            _switch(old)
            _save(before)
            try:
                restart()
            except RuntimeError:
                pass
            raise RuntimeError(f"Version {name} startet nicht. Zurückgesetzt auf {old}.")
        raise RuntimeError(f"Version {name} startet nicht.")


def rollback():
    prev = _state().get("previous")
    if not prev or not (VERS / prev).is_dir():
        raise ValueError("Es gibt keine frühere Version.")
    activate(prev)


def delete(name):
    st = _state()
    if not NAME.match(name) or not (VERS / name).is_dir():
        raise ValueError("Version nicht gefunden.")
    if st.get("active") == name:
        raise ValueError("Die aktive Version kann nicht gelöscht werden.")
    shutil.rmtree(VERS / name)
    if st.get("previous") == name:
        st["previous"] = None
        _save(st)


def install_and_activate(path):
    name = import_zip(path)
    activate(name)
    done = INBOX / "erledigt"
    try:
        done.mkdir(exist_ok=True)
        shutil.move(str(path), str(done / Path(path).name))
    except OSError:
        pass
    return name


# ---- Anzeige ----
def list_versions():
    st, out = _state(), []
    if VERS.is_dir():
        for d in sorted(VERS.iterdir()):
            if d.is_dir():
                out.append({"name": d.name, "active": d.name == st.get("active"),
                            "previous": d.name == st.get("previous"), "deps": (d / "node_modules").is_dir()})
    return out


def inbox():
    if not INBOX.is_dir():
        return []
    return [{"name": p.name, "path": str(p), "size": p.stat().st_size}
            for p in sorted(INBOX.glob("*.zip"), key=lambda p: -p.stat().st_mtime)]


def status():
    st = _state()
    return {"service": _run("systemctl", "is-active", SERVICE)[1] or "unknown", "port": _port_open(),
            "active": st.get("active"), "previous": st.get("previous"), "port_no": PORT}


def overview():
    logs = _run("journalctl", "-u", SERVICE, "-n", "8", "-o", "cat", "--no-pager")[1].splitlines()
    return {"status": status(), "versions": list_versions(), "inbox": inbox(), "logs": logs}
