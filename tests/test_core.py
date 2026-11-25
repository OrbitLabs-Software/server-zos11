import os, sys, tempfile, time, unittest, zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import zosai, zoscore, zossec

SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # RFC 6238: "12345678901234567890"


class Totp(unittest.TestCase):
    def test_rfc6238_vektoren(self):
        self.assertEqual(zossec.totp_code(SECRET, 59, digits=8), "94287082")
        self.assertEqual(zossec.totp_code(SECRET, 1111111109, digits=8), "07081804")
        self.assertEqual(zossec.totp_code(SECRET, 1234567890, digits=8), "89005924")
        self.assertEqual(zossec.totp_code(SECRET, 59), "287082")

    def test_fenster_und_wiederverwendung(self):
        t = 1111111109
        c = zossec.totp_code(SECRET, t)
        self.assertTrue(zossec.totp_verify(SECRET, c, now=t))
        self.assertTrue(zossec.totp_verify(SECRET, c, now=t + 25))      # eine Stufe später noch gültig
        self.assertFalse(zossec.totp_verify(SECRET, c, now=t + 120))    # zu alt
        self.assertFalse(zossec.totp_verify(SECRET, "12345", now=t))    # falsche Länge
        self.assertTrue(zossec.totp_verify(SECRET, c, user="u1", now=t))
        self.assertFalse(zossec.totp_verify(SECRET, c, user="u1", now=t))  # nicht zweimal

    def test_neues_geheimnis(self):
        s = zossec.new_secret()
        self.assertEqual(len(s), 32)
        self.assertEqual(len(zossec.totp_code(s)), 6)
        self.assertIn("secret=" + s, zossec.uri("admin", s))


@unittest.skipIf(zossec.crypt is None, "crypt nicht verfügbar")
class Login(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        h = zossec.crypt.crypt("geheim", zossec.crypt.mksalt(zossec.crypt.METHOD_SHA512))
        sh = Path(self.d.name, "shadow")
        sh.write_text(f"anna:{h}:19000:0:99999:7:::\ngesperrt:!:19000:0:99999:7:::\n")
        self.p = [mock.patch.object(zossec, "SHADOW", str(sh)), mock.patch.object(zossec, "TOTP_DIR", self.d.name + "/totp")]
        [p.start() for p in self.p]
        zossec._fails.clear()
        zossec._last_counter.clear()

    def tearDown(self):
        [p.stop() for p in self.p]
        self.d.cleanup()

    def test_passwort(self):
        self.assertTrue(zossec.verify_password("anna", "geheim"))
        self.assertFalse(zossec.verify_password("anna", "falsch"))
        self.assertFalse(zossec.verify_password("gesperrt", ""))
        self.assertFalse(zossec.verify_password("nobody-da", "x"))

    def test_sperre_nach_fehlversuchen(self):
        for _ in range(zossec.MAX_FAIL):
            self.assertEqual(zossec.authenticate("anna", "x", now=100)[0], "fail")
        self.assertEqual(zossec.authenticate("anna", "geheim", now=101)[0], "locked")
        self.assertEqual(zossec.authenticate("anna", "geheim", now=100 + zossec.LOCK_SECONDS + 1)[0], "ok")

    def test_zwei_faktor_ablauf(self):
        zossec.set_secret("anna", SECRET)
        self.assertEqual(zossec.authenticate("anna", "geheim", now=1111111109)[0], "need_code")
        self.assertEqual(zossec.authenticate("anna", "geheim", "000000", now=1111111109)[0], "fail")
        c = zossec.totp_code(SECRET, 1111111109)
        self.assertEqual(zossec.authenticate("anna", "geheim", c, now=1111111109)[0], "ok")
        zossec.remove_secret("anna")
        self.assertEqual(zossec.authenticate("anna", "geheim", now=1111111200)[0], "ok")

    def test_ungueltiger_name(self):
        with self.assertRaises(ValueError):
            zossec.set_secret("../x", SECRET)


class Admin(unittest.TestCase):
    def test_rechte(self):
        u = mock.Mock(pw_uid=1000, pw_gid=1000)
        g = mock.Mock(gr_mem=["anna"], gr_gid=27)
        with mock.patch.object(zossec.pwd, "getpwnam", return_value=u), mock.patch.object(zossec.grp, "getgrnam", return_value=g):
            self.assertTrue(zossec.is_admin("anna"))
            self.assertFalse(zossec.is_admin("bob"))
        with mock.patch.object(zossec.pwd, "getpwnam", side_effect=KeyError):
            self.assertFalse(zossec.is_admin("niemand"))


class Dienste(unittest.TestCase):
    def test_pruefung_ohne_systemctl(self):
        with self.assertRaises(ValueError):
            zoscore.svc_action("böse name", "start")
        with self.assertRaises(ValueError):
            zoscore.svc_action("cron.service", "löschen")
        with self.assertRaises(PermissionError):
            zoscore.svc_action("ssh.service", "stop")
        with self.assertRaises(PermissionError):
            zoscore.svc_action("zos-shell.service", "restart")


def make_zip(path, version="1.2.3", server=True, evil=False):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("ai-core/package.json", '{"name":"ai-core","version":"%s"}' % version)
        if server:
            z.writestr("ai-core/server/server.js", "// test")
        if evil:
            z.writestr("../boese.txt", "x")


class AiCore(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        b = Path(self.d.name)
        self.zip = b / "ai.zip"
        self.p = [mock.patch.object(zosai, "BASE", b / "base"), mock.patch.object(zosai, "VERS", b / "base/versions"),
                  mock.patch.object(zosai, "CUR", b / "base/current"), mock.patch.object(zosai, "STATE", b / "base/state.json"),
                  mock.patch.object(zosai, "INBOX", b / "inbox"),
                  mock.patch.object(zosai, "install_deps", lambda d: (Path(d) / "node_modules").mkdir()),
                  mock.patch.object(zosai, "restart", lambda: None), mock.patch.object(zosai, "healthy", lambda *a: True)]
        (b / "base").mkdir()
        [p.start() for p in self.p]

    def tearDown(self):
        [p.stop() for p in self.p]
        self.d.cleanup()

    def test_einspielen_und_namen(self):
        make_zip(self.zip)
        self.assertEqual(zosai.import_zip(self.zip), "1.2.3")
        self.assertEqual(zosai.import_zip(self.zip), "1.2.3-2")

    def test_ungueltige_zips(self):
        make_zip(self.zip, server=False)
        with self.assertRaises(ValueError):
            zosai.import_zip(self.zip)
        make_zip(self.zip, evil=True)
        with self.assertRaises(ValueError):
            zosai.import_zip(self.zip)
        with self.assertRaises(ValueError):
            zosai.import_zip(self.d.name + "/nichts.txt")
        self.assertEqual(zosai.list_versions(), [])

    def test_fehlende_abhaengigkeiten_raeumen_auf(self):
        make_zip(self.zip)
        with mock.patch.object(zosai, "install_deps", side_effect=RuntimeError("kein Internet")):
            with self.assertRaises(RuntimeError):
                zosai.import_zip(self.zip)
        self.assertEqual(zosai.list_versions(), [])

    def test_aktivieren_zurueck_loeschen(self):
        make_zip(self.zip, "1.0.0"); a = zosai.import_zip(self.zip)
        make_zip(self.zip, "2.0.0"); b = zosai.import_zip(self.zip)
        zosai.activate(a)
        zosai.activate(b)
        self.assertEqual(os.readlink(zosai.CUR), str(zosai.VERS / b))
        self.assertEqual(zosai.status.__name__, "status")
        zosai.rollback()
        self.assertEqual(os.readlink(zosai.CUR), str(zosai.VERS / a))
        with self.assertRaises(ValueError):
            zosai.delete(a)           # aktiv
        zosai.delete(b)
        self.assertEqual([v["name"] for v in zosai.list_versions()], ["1.0.0"])

    def test_start_fehlschlag_setzt_zurueck(self):
        make_zip(self.zip, "1.0.0"); a = zosai.import_zip(self.zip)
        make_zip(self.zip, "2.0.0"); b = zosai.import_zip(self.zip)
        zosai.activate(a)
        with mock.patch.object(zosai, "healthy", lambda *a: False):
            with self.assertRaises(RuntimeError) as cm:
                zosai.activate(b)
        self.assertIn("Zurückgesetzt", str(cm.exception))
        self.assertEqual(os.readlink(zosai.CUR), str(zosai.VERS / a))
        self.assertEqual(zosai._state()["active"], a)

    def test_posteingang(self):
        (Path(zosai.INBOX)).mkdir()
        make_zip(Path(zosai.INBOX) / "ai.zip")
        self.assertEqual([x["name"] for x in zosai.inbox()], ["ai.zip"])
        self.assertEqual(zosai.install_and_activate(Path(zosai.INBOX) / "ai.zip"), "1.2.3")
        self.assertEqual(zosai.inbox(), [])


if __name__ == "__main__":
    unittest.main()
