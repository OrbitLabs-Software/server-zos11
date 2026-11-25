#!/usr/bin/env python3
"""zoscore - Systemfunktionen fuer die zOS-Oberflaeche (Dienste, Speicher, Netzwerk, Benutzer, Updates, Protokolle)."""
import json, os, pwd, re, subprocess
from pathlib import Path

PROTECTED = {"ssh.service": ("stop",), "zos-shell.service": ("stop", "restart")}  # Aussperr-Schutz
SVC = re.compile(r"^[A-Za-z0-9@._:\-]+\.service$")
_cpu = None
_upd = None


def sh(*args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout


def cpu_pct():
    global _cpu
    v = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:]))
    idle, tot = v[3] + v[4], sum(v)
    p = 0.0
    if _cpu and tot > _cpu[1]:
        p = 100 * (1 - (idle - _cpu[0]) / (tot - _cpu[1]))
    _cpu = (idle, tot)
    return round(p, 1)


def system():
    mi = {l.split(":")[0]: int(l.split()[1]) * 1024 for l in Path("/proc/meminfo").read_text().splitlines()}
    osr = dict(l.split("=", 1) for l in Path("/etc/os-release").read_text().splitlines() if "=" in l)
    ip = ""
    try:
        for i in json.loads(sh("ip", "-j", "-4", "addr")):
            if i["ifname"] != "lo" and i.get("addr_info"):
                ip = i["addr_info"][0]["local"]
                break
    except Exception:
        pass
    return {
        "host": os.uname().nodename,
        "os": "zOS Server 2.1 · " + osr.get("PRETTY_NAME", "Linux").strip('"'),
        "uptime": int(float(Path("/proc/uptime").read_text().split()[0])),
        "load": [round(x, 2) for x in os.getloadavg()],
        "cpu": cpu_pct(),
        "mem": {"total": mi["MemTotal"], "used": mi["MemTotal"] - mi["MemAvailable"]},
        "ip": ip,
    }


def disks():
    out = sh("df", "-B1", "--output=source,target,size,used", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs", "-x", "overlay")
    res = []
    for l in out.splitlines()[1:]:
        s, t, size, used = l.split()
        res.append({"src": s, "mount": t, "size": int(size), "used": int(used)})
    return res


def net():
    return [
        {"name": i["ifname"], "state": i.get("operstate", ""), "mac": i.get("address", ""),
         "addrs": [f'{a["local"]}/{a["prefixlen"]}' for a in i.get("addr_info", [])]}
        for i in json.loads(sh("ip", "-j", "addr"))
    ]


def services():
    out = sh("systemctl", "list-units", "--type=service", "--state=running,failed", "--no-legend", "--plain", "--no-pager")
    res = []
    for l in out.splitlines():
        p = l.split(None, 4)
        if len(p) >= 4:
            res.append({"name": p[0], "desc": p[4] if len(p) > 4 else "", "active": "failed" if p[2] == "failed" else p[3]})
    return res


def svc_action(name, act):
    """Dienst starten/stoppen/neu starten (von Oberflaeche und Web-API genutzt)."""
    if not SVC.match(name) or act not in ("start", "stop", "restart"):
        raise ValueError("Ungueltige Aktion")
    if act in PROTECTED.get(name, ()):
        raise PermissionError("Dieser Dienst ist geschützt und kann nicht gestoppt werden.")
    r = subprocess.run(["systemctl", act, name], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "Aktion fehlgeschlagen")


def users():
    return [{"name": u.pw_name, "uid": u.pw_uid, "home": u.pw_dir, "shell": u.pw_shell}
            for u in pwd.getpwall() if u.pw_uid == 0 or 1000 <= u.pw_uid < 65534]


def updates():
    pk = []
    for l in sh("apt", "list", "--upgradable").splitlines():
        if "/" in l and "upgradable" in l:
            m = re.search(r"from: (\S+)", l)
            pk.append({"name": l.split("/")[0], "new": l.split()[1], "old": m.group(1) if m else ""})
    return {"count": len(pk), "pkgs": pk, "running": bool(_upd and _upd.poll() is None)}


def run_updates():
    global _upd
    if _upd and _upd.poll() is None:
        return
    cmd = "{ DEBIAN_FRONTEND=noninteractive apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get -y -q upgrade; } >> /var/log/zos-update.log 2>&1"
    _upd = subprocess.Popen(["bash", "-c", cmd])


def logs(n):
    return sh("journalctl", "-n", str(max(10, min(n, 500))), "-o", "short", "--no-pager").splitlines()
