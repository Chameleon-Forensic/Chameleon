"""
Mantiksal imaj (docs/roadmap.md madde 0.5) testleri.

Linux tarafi: kucuk bir "sahte dosya sistemi" tutan mock SSH ile (find/test/
stat/dd/sha256sum taklidi) -- diger testlerle AYNI yontem.

Windows tarafi: mock DEGIL, GERCEK PowerShell -- kod tabani PowerShell
BETIKLERINI uretiyor; bu betiklerin (kilitli dosya, yansima noktasi/
junction, buyuk dosya bloklari, ACL ile izin reddi) gercekten calistigini
mock'la dogrulamak mumkun degil. Fake SSH nesnesi sadece run_command'i
yerel `powershell`e yonlendiriyor. Windows disinda atlanir.
"""

import base64
import hashlib
import os
import shlex
import subprocess
import sys

import pytest

import file_acquirer as fa
import image_acquirer as ia


@pytest.fixture(autouse=True)
def _isolated(isolated_coc_log, tmp_path, monkeypatch):
    """coc log'u ve kalici manifest klasorunu gecici klasore yonlendirir --
    gercek logs/ altina hicbir sey yazilmaz."""
    monkeypatch.setattr(ia, "MANIFEST_DIR", str(tmp_path / "manifests"))
    return isolated_coc_log


# ---------------------------------------------------------------------------
# Linux: sahte dosya sistemi
# ---------------------------------------------------------------------------
class _Out:
    def __init__(self, data, exit_status=0):
        self._data = data
        self.channel = self
        self._exit = exit_status

    def read(self):
        return self._data

    def recv_exit_status(self):
        return self._exit


class _NullIO:
    def write(self, _):
        pass

    def flush(self):
        pass

    def read(self):
        return b""


class FakeLinuxFS:
    def __init__(self, files, unreadable=()):
        self.files = dict(files)
        self.unreadable = set(unreadable)
        self.client = self
        self.dd_calls = {}  # yol -> dd cagri sayisi

    def is_active(self):
        return True

    def reconnect(self):
        return True

    def _under(self, root):
        root = root.rstrip("/") + "/"
        return sorted(p for p in self.files if p.startswith(root))

    def run_command(self, cmd, sudo_password=None, get_pty=False):
        if cmd.startswith("test -f"):
            p = shlex.split(cmd)[2]
            if p in self.files:
                return "FILE\n", "", 0
            if self._under(p):
                return "DIR\n", "", 0
            return "NONE\n", "", 0
        if cmd.startswith("find ") and "-xdev -type f" in cmd:
            root = shlex.split(cmd)[1]
            if "! -readable" in cmd:
                return "\n".join(p for p in self._under(root) if p in self.unreadable), "", 0
            return "\n".join(self._under(root)), "", 0
        if cmd.startswith("stat -c%s"):
            return str(len(self.files[shlex.split(cmd)[2]])), "", 0
        if cmd.startswith("test -e"):
            p = shlex.split(cmd)[2]
            if p not in self.files:
                return "GONE\n", "", 0
            return ("DENIED\n" if p in self.unreadable else "OK\n"), "", 0
        if "sha256sum" in cmd:
            p, n = self._parse_dd(cmd)
            data = b"" if p in self.unreadable else self._block(p, n)
            return f"{hashlib.sha256(data).hexdigest()}  -\n", "", 0
        return "", "", 0

    def exec_command(self, cmd, get_pty=False):
        p, n = self._parse_dd(cmd)
        self.dd_calls[p] = self.dd_calls.get(p, 0) + 1
        if p in self.unreadable:
            return _NullIO(), _Out(b"", exit_status=1), _NullIO()
        return _NullIO(), _Out(self._block(p, n)), _NullIO()

    @staticmethod
    def _parse_dd(cmd):
        import re
        path = shlex.split(cmd[cmd.index("dd "):])[1][3:]
        skip = int(re.search(r"skip=(\d+)", cmd).group(1))
        return path, skip

    def _block(self, path, block_no):
        b = 4 * 1024 * 1024
        return self.files[path][block_no * b:(block_no + 1) * b]


def _linux_tree():
    return {
        "/data/a.txt": b"alpha",
        "/data/sub/b.bin": bytes(range(256)) * 100,
        "/data/secret.db": b"top secret",
        "/data/empty.txt": b"",
        "/other/outside.txt": b"not under root",
    }


def test_linux_logical_takes_all_readable_files_and_reports_unreadable_with_reason(tmp_path):
    fs = FakeLinuxFS(_linux_tree(), unreadable={"/data/secret.db"})
    out = tmp_path / "out"
    manifest = fa.acquire_logical_image(fs, "/data", str(out))

    assert manifest["mode"] == "logical"
    alinan = {a["remote_path"]: a for a in manifest["acquired"]}
    assert set(alinan) == {"/data/a.txt", "/data/sub/b.bin", "/data/empty.txt"}
    assert "/other/outside.txt" not in alinan
    for yol, veri in _linux_tree().items():
        if yol in alinan:
            assert alinan[yol]["sha256"] == hashlib.sha256(veri).hexdigest()
            assert (out / yol[len("/data/"):]).read_bytes() == veri

    assert manifest["failed"] == ["/data/secret.db"]
    assert "izin yok" in manifest["failed_reasons"]["/data/secret.db"]
    assert manifest["total_files"] == 4
    # Onceden tespit edilen okunamayan dosya alma dongusune HIC girmemeli
    # (4 yeniden deneme + hash sorgusuyla zaman kaybettirmemeli).
    assert "/data/secret.db" not in fs.dd_calls
    # Islem bitti -> "Yarim Kalanlar"da kalici kayit birakilmamali
    assert ia.list_incomplete_tree_manifests() == []


def test_linux_logical_writes_persistent_manifest_only_every_n_files(tmp_path, monkeypatch):
    fs = FakeLinuxFS({f"/v/f{i:03d}.txt": b"x" * 10 for i in range(250)})
    yazimlar = []
    gercek = fa._write_manifest
    monkeypatch.setattr(fa, "_write_manifest", lambda p, s: (yazimlar.append(len(s["acquired_files"])), gercek(p, s)))

    fa.acquire_logical_image(fs, "/v", str(tmp_path / "out"))
    assert yazimlar == [100, 200], "her dosyada degil, 100 dosyada bir yazilmali (O(n^2) onlemi)"


def test_linux_plain_folder_mode_still_writes_manifest_after_every_file(tmp_path, monkeypatch):
    """Mantiksal imaj icin eklenen seyrek yazma, MEVCUT klasor modunun
    (her dosyadan sonra kalici resume noktasi) davranisini degistirmemeli."""
    fs = FakeLinuxFS({f"/v/f{i}.txt": b"x" for i in range(5)})
    yazimlar = []
    gercek = fa._write_manifest
    monkeypatch.setattr(fa, "_write_manifest", lambda p, s: (yazimlar.append(1), gercek(p, s)))
    monkeypatch.setattr(fa, "list_remote_files", lambda ssh, root, password=None: sorted(fs._under(root)))

    manifest = fa.acquire_remote_tree(fs, "/v", str(tmp_path / "out"))
    assert len(yazimlar) == 5
    assert manifest["mode"] == "file"


def test_linux_logical_resume_skips_already_acquired(tmp_path):
    fs = FakeLinuxFS({"/d/a": b"1", "/d/b": b"2", "/d/c": b"3"})
    state = {"acquired_files": ["/d/a", "/d/b"], "acquired_detail": [
        {"remote_path": "/d/a", "local_path": "x", "sha256": "h"},
        {"remote_path": "/d/b", "local_path": "y", "sha256": "h"},
    ]}
    manifest = fa.acquire_logical_image(fs, "/d", str(tmp_path / "out"), resume_state=state)
    assert set(fs.dd_calls) == {"/d/c"}, "sadece kalan dosya gercekten cekilmeli"
    assert len(manifest["acquired"]) == 3


# ---------------------------------------------------------------------------
# Windows: gercek PowerShell
# ---------------------------------------------------------------------------
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="gercek PowerShell gerektirir")


class LocalPowerShell:
    """run_command'i SSH yerine yerel powershell'e yonlendirir -- betikler
    hedefte calisacaklarla BIREBIR ayni."""
    client = True

    def is_active(self):
        return True

    def reconnect(self):
        return True

    def run_command(self, cmd, sudo_password=None, get_pty=False):
        script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + cmd
        enc = base64.b64encode(script.encode("utf-16-le")).decode()
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
            capture_output=True, timeout=120,
        )
        return r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"), r.returncode


def _lock_exclusively(path):
    """Dosyayi paylasimsiz (dwShareMode=0) acar -- calisan Windows'ta sistem
    dosyalarinin (registry hive, pagefile) durumuyla ayni: baska hicbir
    islem okuyamaz."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    h = k32.CreateFileW(path, 0x80000000, 0, None, 3, 0, None)
    assert h not in (None, wintypes.HANDLE(-1).value), "kilitleme basarisiz"
    return lambda: k32.CloseHandle(h)


@pytest.fixture
def win_tree(tmp_path):
    root = tmp_path / "vol"
    (root / "sub").mkdir(parents=True)
    (root / "System Volume Information").mkdir()
    (root / "a.txt").write_bytes(b"alpha")
    (root / "empty.txt").write_bytes(b"")
    (root / "sub" / "b.txt").write_bytes(b"bravo" * 1000)
    (root / "pagefile.sys").write_bytes(b"P" * 100)
    (root / "sub" / "pagefile.sys").write_bytes(b"user file with same name")
    (root / "System Volume Information" / "x.dat").write_bytes(b"svi")
    (root / "hidden.txt").write_bytes(b"hidden")
    subprocess.run(["attrib", "+h", str(root / "hidden.txt")], check=True)
    # Kendine geri bakan junction: -Recurse takip etse SONSUZ dongu olurdu
    subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "sub" / "loop"), str(root)],
                   check=True, capture_output=True)
    return root


@windows_only
def test_windows_lister_skips_junction_excludes_system_files_but_keeps_hidden(win_tree):
    dosyalar, basarisiz, dislanan = __import__("windows_acquirer").list_logical_files_windows(
        LocalPowerShell(), str(win_tree),
    )
    goreli = sorted(os.path.relpath(p, win_tree) for p in dosyalar)
    assert goreli == ["a.txt", "empty.txt", "hidden.txt", os.path.join("sub", "b.txt"),
                      os.path.join("sub", "pagefile.sys")]
    disl = {os.path.relpath(p, win_tree): s for p, s in dislanan.items()}
    assert "pagefile.sys" in disl                       # hacim kokundeki -> dislanir
    assert "System Volume Information" in disl          # sistem klasoru -> dislanir
    assert os.path.join("sub", "pagefile.sys") not in disl  # ayni ad, baska klasor -> NORMAL dosya
    assert basarisiz == {}


@windows_only
def test_windows_logical_image_end_to_end_with_locked_file_and_large_file(win_tree, tmp_path):
    import windows_acquirer as wa
    buyuk = os.urandom(9 * 1024 * 1024 + 123)   # 3 blok (4+4+1 MB) -- blok yolu
    (win_tree / "big.bin").write_bytes(buyuk)
    (win_tree / "locked.dat").write_bytes(b"in use by the OS")
    kilit_birak = _lock_exclusively(str(win_tree / "locked.dat"))
    try:
        out = tmp_path / "out"
        manifest = wa.acquire_logical_image_windows(LocalPowerShell(), str(win_tree), str(out))
    finally:
        kilit_birak()

    alinan = {os.path.relpath(a["remote_path"], win_tree): a for a in manifest["acquired"]}
    assert "big.bin" in alinan and alinan["big.bin"]["sha256"] == hashlib.sha256(buyuk).hexdigest()
    assert (out / "big.bin").read_bytes() == buyuk
    assert (out / "sub" / "b.txt").read_bytes() == b"bravo" * 1000
    assert (out / "empty.txt").read_bytes() == b""
    assert alinan["empty.txt"]["sha256"] == hashlib.sha256(b"").hexdigest()

    kilitli = [p for p in manifest["failed"] if p.endswith("locked.dat")]
    assert len(kilitli) == 1
    assert manifest["failed_reasons"][kilitli[0]].startswith("kilitli")
    assert manifest["mode"] == "logical"
    assert any(p.endswith("pagefile.sys") for p in manifest["excluded"])
    assert not any(p.endswith("pagefile.sys") for p in manifest["failed"]), "dislanan, basarisiz sayilmamali"
    assert ia.list_incomplete_tree_manifests() == []


@windows_only
def test_windows_access_denied_is_reported_as_permission_reason(win_tree):
    import windows_acquirer as wa
    hedef = win_tree / "denied.txt"
    hedef.write_bytes(b"x")
    # ALAN\kullanici bicimi SART: bilgisayar adi kullanici adiyla ayni/benzer
    # olunca (orn. TOPRAK\Toprak) sade "kullanici:" icacls'te BOS bir hesaba
    # cozuluyor ve deny hicbir sey engellemiyor.
    kullanici = f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}"
    subprocess.run(["icacls", str(hedef), "/deny", f"{kullanici}:(R)"], check=True, capture_output=True)
    try:
        sebep = {}
        ok, _ = wa.acquire_remote_file_windows(LocalPowerShell(), str(hedef), str(win_tree / "cikti"), reason_out=sebep)
    finally:
        subprocess.run(["icacls", str(hedef), "/remove:d", kullanici], capture_output=True)
    assert ok is False
    assert sebep["reason"].startswith("izin yok")
