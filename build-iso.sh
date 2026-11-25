#!/usr/bin/env bash
# Baut build/zos-server-2.0.iso aus dem Ubuntu-Server-ISO (Linux, WSL oder GitHub Actions).
# Voraussetzung: xorriso, openssl
# Ohne ZOS_PASSWORD fragt der Installer selbst nach Benutzer und Passwort.
set -euo pipefail
SRC="${1:?Aufruf: ./build-iso.sh ubuntu-24.04.x-live-server-amd64.iso}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/build/zos-server-2.0.iso"
mkdir -p "$HERE/build"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT

if [ -n "${ZOS_PASSWORD:-}" ]; then
  HASH="$(openssl passwd -6 "$ZOS_PASSWORD")"
  IDENT="  identity: {hostname: zos, username: admin, password: '$HASH'}"
  INTERACTIVE="[storage]"
else
  IDENT=""   # kein identity-Block: der Installer fragt Benutzer und Passwort selbst ab
  INTERACTIVE="[identity, storage]"
fi

mkdir -p "$W/server" "$W/zos"
cp -r "$HERE/shell" "$HERE/core" "$HERE/install.sh" "$W/zos/"
: > "$W/server/meta-data"
cat > "$W/server/user-data" <<EOF
#cloud-config
autoinstall:
  version: 1
  locale: de_DE.UTF-8
  keyboard: {layout: de}
$IDENT
  ssh: {install-server: true}
  interactive-sections: $INTERACTIVE
  late-commands:
    - cp -r /cdrom/zos /target/opt/zos-src
    - curtin in-target --target=/target -- bash /opt/zos-src/install.sh
EOF

# Bootmenü: Autoinstall aktivieren, Wartezeit verkürzen
xorriso -osirrox on -indev "$SRC" -extract /boot/grub/grub.cfg "$W/grub.cfg" >/dev/null 2>&1
chmod u+w "$W/grub.cfg"
sed -i 's|---$|autoinstall ds=nocloud\\;s=/cdrom/server/ ---|' "$W/grub.cfg"
sed -i 's/^set timeout=.*/set timeout=5/' "$W/grub.cfg"

xorriso -indev "$SRC" -outdev "$OUT" -boot_image any replay \
  -map "$W/server" /server -map "$W/zos" /zos -map "$W/grub.cfg" /boot/grub/grub.cfg -commit >/dev/null

echo "Fertig: $OUT"
