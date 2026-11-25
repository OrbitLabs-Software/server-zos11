#!/usr/bin/env bash
# zOS Server 2.1 - installiert native Oberflaeche, Anmeldung, AI-Core-Manager und Fernzugriff auf Ubuntu Server 24.04
# Das Internet wird nur zum Installieren der Pakete gebraucht, danach laeuft alles offline.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Bitte als root starten: sudo bash install.sh"; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"
export DEBIAN_FRONTEND=noninteractive

# ---------- Pakete ----------
apt-get update -q || echo "Hinweis: Paketlisten nicht aktualisiert"
for p in python3 iproute2 openssl ufw nodejs npm python3-qrcode \
         xserver-xorg-core xserver-xorg-input-libinput xinit x11-xserver-utils x11-xkb-utils \
         python3-gi python3-gi-cairo gir1.2-gtk-4.0 adwaita-icon-theme librsvg2-common fonts-noto-core fonts-noto-mono \
         x11vnc novnc websockify; do
  dpkg -s "$p" >/dev/null 2>&1 || apt-get install -y -q "$p" || echo "Hinweis: $p konnte nicht installiert werden"
done
apt-get install -y -q fonts-inter >/dev/null 2>&1 || true

# ---------- Reste frueherer Versionen (Web-Oberflaeche) entfernen ----------
systemctl disable --now zosd >/dev/null 2>&1 || true
rm -f /etc/systemd/system/zosd.service /opt/zos/bin/zosd /opt/zos/bin/zosd.py /opt/zos/shell/index.html /etc/zos/token

# ---------- Programme ----------
install -d -m 755 /opt/zos/shell /opt/zos/bin
install -m 644 "$SRC"/core/*.py /opt/zos/bin/
install -m 755 "$SRC/shell/zos-shell.py" /opt/zos/shell/zos-shell.py
install -d -m 700 /etc/zos /etc/zos/totp /etc/zos/tls

cat > /opt/zos/bin/zos-session <<'EOF'
#!/bin/sh
mkdir -p /run/zos-ui && chmod 700 /run/zos-ui
export XDG_RUNTIME_DIR=/run/zos-ui HOME=/root
export GDK_BACKEND=x11 GSK_RENDERER=cairo LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=1 GSETTINGS_BACKEND=memory
setxkbmap de 2>/dev/null || true
xset s off -dpms 2>/dev/null || true
xsetroot -solid '#0b1020' -cursor_name left_ptr 2>/dev/null || true
exec python3 /opt/zos/shell/zos-shell.py
EOF
chmod 755 /opt/zos/bin/zos-session

cat > /etc/systemd/system/zos-shell.service <<'EOF'
[Unit]
Description=zOS Oberflaeche (lokal)
After=systemd-user-sessions.service getty@tty1.service
Conflicts=getty@tty1.service
OnFailure=getty@tty1.service
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
ExecStart=/usr/bin/xinit /opt/zos/bin/zos-session -- /usr/bin/Xorg :0 vt1 -nolisten tcp
StandardInput=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

# ---------- AI-Core: Benutzer, Ordner, Dienst (Versionen werden in der Oberflaeche eingespielt) ----------
id aicore >/dev/null 2>&1 || useradd --system --home-dir /var/lib/ai-core --shell /usr/sbin/nologin aicore
install -d -m 755 /opt/ai-core /opt/ai-core/versions
install -d -m 750 -o aicore -g aicore /var/lib/ai-core /var/lib/ai-core/data
install -d -m 755 /etc/ai-core
if [ ! -f /etc/ai-core/env ]; then
  printf '# AI-Core-Einstellungen (siehe .env.example der jeweiligen Version)\nPORT=3000\nHOST=0.0.0.0\n' > /etc/ai-core/env
  chown root:aicore /etc/ai-core/env && chmod 640 /etc/ai-core/env
fi
install -d -m 2775 -o root -g sudo /srv/zos /srv/zos/inbox

cat > /etc/systemd/system/ai-core.service <<'EOF'
[Unit]
Description=AI Core
After=network-online.target
Wants=network-online.target
ConditionPathExists=/opt/ai-core/current/server/server.js

[Service]
User=aicore
WorkingDirectory=/opt/ai-core/current
EnvironmentFile=-/etc/ai-core/env
Environment=NODE_ENV=production AICORE_DATA_DIR=/var/lib/ai-core/data
ExecStart=/usr/bin/node server/server.js
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# ---------- Fernzugriff: VNC nur lokal, nach aussen nur verschluesselt (HTTPS) ----------
if [ ! -s /etc/zos/tls/cert.pem ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=zos" -addext "subjectAltName=DNS:zos,DNS:localhost" \
    -keyout /etc/zos/tls/key.pem -out /etc/zos/tls/cert.pem >/dev/null 2>&1 || echo "Hinweis: Zertifikat konnte nicht erstellt werden"
  chmod 600 /etc/zos/tls/key.pem 2>/dev/null || true
fi
if command -v x11vnc >/dev/null 2>&1; then
  if [ ! -s /etc/zos/vncpasswd ]; then
    VNCPW="$(head -c 9 /dev/urandom | base64 | tr -d '/+=' | cut -c1-8)"
    x11vnc -storepasswd "$VNCPW" /etc/zos/vncpasswd >/dev/null 2>&1
    echo "$VNCPW" > /etc/zos/vnc-password.txt
    chmod 600 /etc/zos/vncpasswd /etc/zos/vnc-password.txt
  fi
  cat > /etc/systemd/system/zos-vnc.service <<'EOF'
[Unit]
Description=zOS Fernbildschirm (VNC, nur lokal)
After=zos-shell.service
PartOf=zos-shell.service

[Service]
ExecStart=/usr/bin/x11vnc -display :0 -auth guess -rfbauth /etc/zos/vncpasswd -rfbport 5900 -localhost -forever -shared -noxdamage -nolookup -quiet
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
fi
if command -v websockify >/dev/null 2>&1 && [ -d /usr/share/novnc ]; then
  cat > /etc/systemd/system/zos-web.service <<'EOF'
[Unit]
Description=zOS Fernzugriff im Browser (noVNC, HTTPS)
After=zos-vnc.service

[Service]
ExecStart=/usr/bin/websockify --web /usr/share/novnc --ssl-only --cert /etc/zos/tls/cert.pem --key /etc/zos/tls/key.pem 6080 127.0.0.1:5900
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
fi

# ---------- Firewall ----------
if command -v ufw >/dev/null 2>&1; then
  for port in 22 3000 6080; do ufw allow "$port/tcp" >/dev/null 2>&1 || true; done
  ufw --force enable >/dev/null 2>&1 || true
fi

printf 'zOS Server 2.1  \\n  \\l\n\n' > /etc/issue

systemctl enable zos-shell zos-vnc zos-web ai-core >/dev/null 2>&1 || true
if [ -d /run/systemd/system ]; then
  systemctl daemon-reload || true
  systemctl restart zos-shell || true   # schaltet die Konsole auf die Oberflaeche um
  systemctl restart zos-vnc || true
  systemctl restart zos-web || true
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "zOS Server 2.1 ist installiert. Die Oberflaeche erscheint auf dem Bildschirm des Servers."
echo "Anmeldung: mit dem Linux-Benutzer und -Passwort (Administrator = Mitglied der Gruppe sudo)."
if [ -f /etc/systemd/system/zos-web.service ]; then
  echo "Fernzugriff im Browser: https://$IP:6080/vnc.html?autoconnect=true&resize=scale   (Zertifikatswarnung einmal bestaetigen)"
  [ -s /etc/zos/vnc-password.txt ] && echo "VNC-Passwort: $(cat /etc/zos/vnc-password.txt)"
fi
echo "AI-Core: ZIP nach /srv/zos/inbox kopieren, dann in der Oberflaeche unter AI-Core einspielen."
