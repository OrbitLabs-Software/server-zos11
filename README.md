# zOS Server 2.1

Ubuntu Server 24.04 als Unterbau, darauf eine native Oberfläche (GTK4). Kein Browser, keine Web-Seite von zOS.

**Stand:** Die Logik (Anmeldung, Zwei-Faktor, AI-Core-Versionen) ist mit Unit-Tests geprüft (`python3 -m unittest discover -s tests -v`). Die Oberfläche selbst, die Installation und die ISO sind ungetestet. Fehlerausgaben und Screenshots bitte zurückschicken.

## Die sechs Stufen

1. **Basis-ISO:** `build-iso.sh` und der GitHub-Workflow bauen aus dem Ubuntu-Server-ISO eine Installer-ISO mit Autoinstall.
2. **Design:** natives Fluent-Design mit Hell/Dunkel, Akzentfarben, Textgröße 100/125/150 %, Animationen schaltbar.
3. **Systemverwaltung:** Übersicht, Dienste, Speicher, Netzwerk, Benutzer, Updates, Protokolle.
4. **AI-Core-Manager:** Versionen einspielen, aktivieren, zurücksetzen, löschen. Ein Fehlstart setzt automatisch auf die vorige Version zurück.
5. **Sicherheit:** Sperrbildschirm mit Linux-Anmeldung, Rechte (Administrator = Gruppe `sudo`), Zwei-Faktor (TOTP), Sperre nach 5 Fehlversuchen, automatische Sperre bei Inaktivität, Firewall, verschlüsselter Fernzugriff.
6. **Feinschliff:** Benachrichtigung bei ausgefallenen Diensten, Suche im Startmenü (Apps und Dienste), Tastatur (Windows-Taste = Startmenü, Strg+L = Sperren), Tests im Workflow.

## Dateien

| Datei | Zweck |
|---|---|
| `shell/zos-shell.py` | Oberfläche |
| `core/zoscore.py` | Systemfunktionen (Dienste, Speicher, Netzwerk, Benutzer, Updates, Protokolle) |
| `core/zossec.py` | Anmeldung, Rechte, Zwei-Faktor |
| `core/zosai.py` | AI-Core-Versionen |
| `tests/test_core.py` | Tests |
| `install.sh` | Installiert alles |
| `build-iso.sh`, `.github/workflows/build-iso.yml` | ISO-Bau, Workflow führt vorher die Tests aus |

## Installation auf einem laufenden Ubuntu Server

Ordner per `scp -r` auf den Server kopieren, dann dort:

```
cd ~/zos-server-2.0
sudo bash install.sh
```

Internet braucht nur die Installation (Pakete). Danach erscheint der Sperrbildschirm auf dem Bildschirm des Servers. Anmeldung mit Linux-Benutzer und -Passwort. Startet die Oberfläche nicht, kommt nach drei Versuchen die Textanmeldung zurück. Fehlersuche: `sudo journalctl -u zos-shell -n 40 --no-pager`.

## AI-Core einspielen

1. ZIP vom PC in den Posteingang kopieren: `scp ai-core-5_4.zip BENUTZER@SERVER-IP:/srv/zos/inbox/`
2. In der Oberfläche **AI-Core** öffnen, bei der Datei **Einspielen und aktivieren** wählen.
3. Beim Einspielen werden die Abhängigkeiten mit `npm ci` installiert (Internet nötig, außer das ZIP enthält `node_modules`). Das kann einige Minuten dauern.

Daten (`/var/lib/ai-core/data`) und Einstellungen (`/etc/ai-core/env`) liegen außerhalb der Versionen und bleiben bei Wechsel und Zurücksetzen erhalten. Der Dienst läuft als eigener Benutzer `aicore` auf Port 3000.

## Zwei-Faktor

Oberfläche, **Sicherheit**, **Einrichten**: QR-Code mit einer Authenticator-App scannen, Code bestätigen. Danach verlangt die Anmeldung zusätzlich den Code. Geheimnisse liegen in `/etc/zos/totp/` (nur root). Verlorener Zugang: als root `rm /etc/zos/totp/BENUTZER`.

## Fernzugriff

Der Desktop ist nativ, übertragen wird nur sein Bild.

- Im Browser: `https://SERVER-IP:6080/vnc.html?autoconnect=true&resize=scale`. Das Zertifikat ist selbst erstellt, der Browser warnt einmalig. Danach VNC-Passwort (steht am Ende der Installation und in `/etc/zos/vnc-password.txt`), dann die Anmeldung am Desktop. Die Seite stammt vom Paket noVNC.
- VNC lauscht nur lokal. Mit einem VNC-Programm: `ssh -L 5900:localhost:5900 BENUTZER@SERVER-IP`, dann `localhost:5900`.

Die Firewall (ufw) erlaubt nur die Ports 22, 3000 und 6080.

## ISO bauen

GitHub: Inhalt dieses Ordners in ein Repository hochladen (auch `.github`), im Reiter Actions „ISO bauen“ starten, nach etwa 10 Minuten unter Artifacts `zos-server-iso` herunterladen. In Hyper-V Secure Boot für die VM ausschalten.

## Grenzen

- Kein Weichzeichner hinter den Fenstern, das Hintergrundbild ist statisch.
- Netzwerk und Benutzer lassen sich nur anzeigen, nicht ändern.
- Kein Terminal und keine Dateiverwaltung in der Oberfläche.
- Der Fernzugriff nutzt ein selbst erstelltes Zertifikat.
