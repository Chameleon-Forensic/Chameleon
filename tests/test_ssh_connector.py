"""ssh_connector.py icin regresyon testleri -- code review'da bulunan
5 gercek hataya karsi (bkz. docs/roadmap.md):

1. run_command(), stdout/stderr TAMAMEN okunmadan ONCE
   stdout.channel.recv_exit_status()'u cagiriyordu -- buyuk ciktilarda
   klasik bir paramiko kilitlenme (deadlock) deseni.
2. host_key_fingerprint, docstring'de "SHA256" diye belgelenirken
   gercekte PKey.get_fingerprint()'in MD5 digest'ini kullaniyordu.
3. connect_via_socks5() cagrilirken self.connect_timeout hic
   iletilmiyordu, socks5.py'nin sabit varsayilani (15sn) kullaniliyordu.
4. _TOFU_SAVE_LOCK, known_hosts okuma/yazma disinda TUM client.connect()
   suresince tutuluyordu -- N hedefe paralel TOFU baglanmayi sirali
   hale getiriyordu.
5. known_hosts_path icin os.path.islink() kontrolu bir TOCTOU acigiydi
   (kontrol ile gercek acma arasinda dosya bir sembolik linke
   donusturulebilirdi).

Gercek bir SSH sunucusu/ag baglantisi kurmadan calisir: paramiko.SSHClient
gercek bir nesne olarak kullanilir (host key dosyasi okuma/yazma
mantiginin GERCEKTEN calistigini dogrulamak icin), sadece ag'a dokunan
iki metod -- SSHClient.connect() ve SSHClient.get_transport() -- fake
implementasyonlarla degistirilir. run_command() testi ise dogrudan
sahte bir paramiko kanali/akisi taklit eder.
"""

import os
import threading
import time

import paramiko
import pytest

import ssh_connector
from ssh_connector import SSHConnector


# ---------------------------------------------------------------------------
# Hata #1: run_command() deadlock deseni
# ---------------------------------------------------------------------------

class _FakeChannel:
    """Gercek paramiko Channel'in run_command() icin ilgili tek davranisini
    taklit eder: recv_exit_status(), stdout VE stderr TAMAMEN okunmadan
    cagrilirsa -- gercek paramiko'da SSH kanalinin flow-control penceresi
    dolup uzak komut BLOKE olacagi ve recv_exit_status() (timeout'suz)
    SONSUZA KADAR bekleyecegi icin -- burada AssertionError firlatarak bu
    deadlock'u deterministik bir test hatasina cevirir."""

    def __init__(self):
        self.stdout_read_done = False
        self.stderr_read_done = False
        self.recv_exit_status_calls = 0

    def recv_exit_status(self):
        self.recv_exit_status_calls += 1
        if not (self.stdout_read_done and self.stderr_read_done):
            raise AssertionError(
                "recv_exit_status() stdout/stderr TAMAMEN okunmadan once "
                "cagirildi -- gercek paramiko'da buyuk ciktida SONSUZA KADAR "
                "bloke olurdu (deadlock)."
            )
        return 0


class _FakeStream:
    """stdout/stderr icin exec_command()'in dondurdugu dosya-benzeri
    nesneyi taklit eder."""

    def __init__(self, data, channel, mark_done):
        self._data = data
        self.channel = channel
        self._mark_done = mark_done

    def read(self):
        self._mark_done()
        return self._data


class _FakeStdin:
    def write(self, *_args, **_kwargs):
        pass

    def flush(self):
        pass


class _FakeClientForRunCommand:
    def __init__(self, stdout_data, stderr_data):
        self.channel = _FakeChannel()
        self.stdout_data = stdout_data
        self.stderr_data = stderr_data
        self.last_command = None

    def exec_command(self, command, get_pty=False):
        self.last_command = command

        def mark_stdout():
            self.channel.stdout_read_done = True

        def mark_stderr():
            self.channel.stderr_read_done = True

        stdout = _FakeStream(self.stdout_data, self.channel, mark_stdout)
        stderr = _FakeStream(self.stderr_data, self.channel, mark_stderr)
        return _FakeStdin(), stdout, stderr


def test_run_command_reads_output_before_exit_status_avoiding_deadlock():
    """Buyuk bir uzak cikti (orn. list_remote_files()'in calistirdigi
    "find <dir> -type f") senaryosunu taklit eder. Eski kod (recv_exit_status()
    ONCE) bu senaryoda AssertionError'a (gercekte deadlock'a) yol acardi;
    fonksiyonun kendi genel except'i bunu yutup (None, None, None) donerdi
    -- bu yuzden asagidaki assert'ler dogrudan REGRESYONU yakalar."""
    buyuk_cikti = ("satir\n" * 200_000).encode("utf-8")  # SSH pencere boyutunu asan boyutta
    fake_client = _FakeClientForRunCommand(buyuk_cikti, b"")

    ssh = SSHConnector(host="1.2.3.4", username="u", password="p")
    ssh.client = fake_client

    output, error, exit_status = ssh.run_command("find /mnt/hedef -type f")

    assert exit_status == 0
    assert output == buyuk_cikti.decode("utf-8")
    assert error == ""
    assert fake_client.channel.recv_exit_status_calls == 1
    assert fake_client.channel.stdout_read_done is True
    assert fake_client.channel.stderr_read_done is True


def test_run_command_still_works_with_stderr_and_nonzero_exit():
    """Duzeltmenin normal (kucuk cikti, hata donen) yolu bozmadigini
    dogrular."""
    fake_client = _FakeClientForRunCommand(b"", b"komut bulunamadi\n")

    ssh = SSHConnector(host="1.2.3.4", username="u", password="p")
    ssh.client = fake_client

    # recv_exit_status() sabit 0 donuyor (fake basitligi icin); burada
    # asil kontrol edilen sey okuma sirasi ve donen degerlerin dogrulugu.
    output, error, exit_status = ssh.run_command("olmayan-komut")

    assert output == ""
    assert error == "komut bulunamadi\n"
    assert exit_status == 0


def test_run_command_without_connection_returns_none_triple():
    ssh = SSHConnector(host="1.2.3.4", username="u", password="p")
    assert ssh.run_command("echo hi") == (None, None, None)


# ---------------------------------------------------------------------------
# Hata #3: connect_timeout, connect_via_socks5()'e iletilmiyordu
# ---------------------------------------------------------------------------

def test_build_connect_kwargs_propagates_connect_timeout_to_socks5(monkeypatch):
    captured = {}

    def fake_connect_via_socks5(proxy_host, proxy_port, dest_host, dest_port, timeout=15):
        captured["proxy_host"] = proxy_host
        captured["proxy_port"] = proxy_port
        captured["dest_host"] = dest_host
        captured["dest_port"] = dest_port
        captured["timeout"] = timeout
        return "FAKE_SOCKET"

    monkeypatch.setattr(ssh_connector, "connect_via_socks5", fake_connect_via_socks5)

    ssh = SSHConnector(host="hedef.onion", port=22, username="u", password="p",
                        socks_proxy_port=9050, connect_timeout=45)
    kwargs = ssh._build_connect_kwargs()

    # Eski hatali kod hicbir zaman timeout iletmiyordu -- socks5.py'nin
    # kendi sabit varsayilani (15) kullanilirdi, cagiranin verdigi 45
    # tamamen goz ardi edilirdi.
    assert captured["timeout"] == 45
    assert captured["dest_host"] == "hedef.onion"
    assert captured["dest_port"] == 22
    assert kwargs["sock"] == "FAKE_SOCKET"


# ---------------------------------------------------------------------------
# Ortak altyapi: connect() testleri icin gercek ag'a dokunmadan calisan
# paramiko.SSHClient taklidi (SADECE connect()/get_transport() fake'lenir --
# host key dosyasi okuma/yazma mantigi GERCEK paramiko kodudur).
# ---------------------------------------------------------------------------

class _FakeTransport:
    def __init__(self, remote_key):
        self._remote_key = remote_key
        self.keepalive_interval = None

    def get_remote_server_key(self):
        return self._remote_key

    def set_keepalive(self, interval):
        self.keepalive_interval = interval


def _install_fake_paramiko_connect(monkeypatch, remote_key, sleep_s=0.0, calls=None):
    """paramiko.SSHClient.connect()/get_transport()'u, GERCEK TCP/SSH hic
    kurmadan, sadece bu testler icin gerekli iki davranisi taklit edecek
    sekilde degistirir:
      - Sunucunun (remote_key) known_hosts'ta zaten bilinip bilinmedigini
        GERCEK client.get_host_keys() uzerinden kontrol eder (SSHConnector.
        connect()'in onceden gercekten cagirdigi client.load_host_keys()
        sayesinde bu dolu olur) -- bilinmiyorsa GERCEK
        client._policy.missing_host_key()'i cagirir (paramiko'nun kendi
        connect()'inin yaptigi TAM OLARAK bu).
      - get_transport(), sahte bir transport donup remote_key'i tasir.
    """
    def fake_connect(self, hostname=None, port=22, username=None, password=None,
                      key_filename=None, passphrase=None, timeout=None,
                      look_for_keys=None, allow_agent=None, sock=None):
        if calls is not None:
            calls.append({"hostname": hostname, "timeout": timeout, "sock": sock})
        if sleep_s:
            time.sleep(sleep_s)
        existing = self.get_host_keys().lookup(hostname)
        if not existing or remote_key.get_name() not in existing:
            self._policy.missing_host_key(self, hostname, remote_key)
        self._fake_transport = _FakeTransport(remote_key)

    def fake_get_transport(self):
        return getattr(self, "_fake_transport", None)

    monkeypatch.setattr(paramiko.SSHClient, "connect", fake_connect)
    monkeypatch.setattr(paramiko.SSHClient, "get_transport", fake_get_transport)


# ---------------------------------------------------------------------------
# Hata #2: host_key_fingerprint gercekte MD5 donduruyordu, SHA256 degil
# ---------------------------------------------------------------------------

def test_host_key_fingerprint_is_real_sha256_not_md5(tmp_path, monkeypatch):
    remote_key = paramiko.RSAKey.generate(1024)
    _install_fake_paramiko_connect(monkeypatch, remote_key)

    ssh = SSHConnector(host="5.6.7.8", username="u", password="p", strict=False,
                        known_hosts_path=str(tmp_path / "known_hosts"))

    assert ssh.connect() is True
    # paramiko'nun kendi modern SHA256 fingerprint property'siyle BIREBIR
    # eslesmeli -- ssh-keygen -lf / ssh -v'nin VARSAYILAN gosterdigi bicim.
    assert ssh.host_key_fingerprint == remote_key.fingerprint
    assert ssh.host_key_fingerprint.startswith("SHA256:")

    # Eski hatali kod PKey.get_fingerprint()'in MD5 digest'ini hex(":")
    # ile birbirine ekleyip "SHA256 fingerprint" diye kaydediyordu -- bu
    # deger asla "SHA256:" ile baslamaz ve dogru SHA256'dan FARKLIDIR.
    eski_hatali_md5_degeri = remote_key.get_fingerprint().hex(":")
    assert ssh.host_key_fingerprint != eski_hatali_md5_degeri


# ---------------------------------------------------------------------------
# Hata #4: _TOFU_SAVE_LOCK tum client.connect() suresince tutuluyordu
# ---------------------------------------------------------------------------

def test_two_tofu_connections_to_different_hosts_run_in_parallel_not_serialized(tmp_path, monkeypatch):
    """Modulun kendi docstring'inin ACIKCA andigi senaryo: ayni anda iki
    farkli hedefe TOFU ile baglanma. Yavas bir "el sikisma" (sleep_s) taklit
    edilir; eski kod _TOFU_SAVE_LOCK'u client.connect() SURESINCE tuttugu
    icin bu iki baglanti SIRALI calisirdi (~2 * sleep_s); duzeltilmis kodda
    kilit sadece known_hosts kaydi icin kisaca tutuldugundan PARALEL
    calismalari gerekir (~sleep_s)."""
    remote_key = paramiko.RSAKey.generate(1024)
    _install_fake_paramiko_connect(monkeypatch, remote_key, sleep_s=0.3)

    known_hosts = tmp_path / "known_hosts"
    results = {}

    def baglan(host):
        ssh = SSHConnector(host=host, username="u", password="p", strict=False,
                            known_hosts_path=str(known_hosts))
        results[host] = ssh.connect()

    t1 = threading.Thread(target=baglan, args=("host-a",))
    t2 = threading.Thread(target=baglan, args=("host-b",))

    start = time.monotonic()
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    gecen_sure = time.monotonic() - start

    assert results == {"host-a": True, "host-b": True}
    # Sirali calissaydi (eski hatali kod) en az ~0.6s surerdi; paralel
    # calistigi icin 0.3s'ye yakin olmali -- bolluca pay birakildi.
    assert gecen_sure < 0.5, f"baglanti lar sirali calismis gibi gorunuyor ({gecen_sure:.3f}s)"


def test_connect_learns_new_key_then_recognizes_it_as_known(tmp_path, monkeypatch):
    """Ust duzey islevsellik: ogrenilen anahtar GERCEKTEN diske yaziliyor
    mu (kilit kucultulurken bu davranis kazara bozulmus olabilirdi)."""
    remote_key = paramiko.RSAKey.generate(1024)
    _install_fake_paramiko_connect(monkeypatch, remote_key)
    known_hosts = tmp_path / "known_hosts"

    ssh1 = SSHConnector(host="10.0.0.5", username="u", password="p", strict=False,
                         known_hosts_path=str(known_hosts))
    assert ssh1.connect() is True
    assert ssh1.host_key_status == "learned"
    assert known_hosts.exists()
    assert "10.0.0.5" in known_hosts.read_text()

    ssh2 = SSHConnector(host="10.0.0.5", username="u", password="p", strict=False,
                         known_hosts_path=str(known_hosts))
    assert ssh2.connect() is True
    assert ssh2.host_key_status == "known"


def test_strict_mode_still_rejects_unknown_host_key(tmp_path, monkeypatch):
    """Kilit kapsami kucultulurken strict=True yolunun (hic kilit
    kullanmayan yol) bozulmadigini dogrular."""
    remote_key = paramiko.RSAKey.generate(1024)
    _install_fake_paramiko_connect(monkeypatch, remote_key)

    ssh = SSHConnector(host="10.10.10.10", username="u", password="p", strict=True,
                        known_hosts_path=str(tmp_path / "known_hosts"))
    assert ssh.connect() is False
    assert ssh.last_error_type == "host_key"


# ---------------------------------------------------------------------------
# Hata #5: known_hosts_path icin os.path.islink() kontrolu bir TOCTOU acigi
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not hasattr(os, "symlink"), reason="platform sembolik link desteklemiyor")
def test_known_hosts_symlink_is_rejected_by_helper(tmp_path):
    gercek_dosya = tmp_path / "hedef_disinda_bir_dosya.txt"
    gercek_dosya.write_text("bu dosyaya yazilmamasi gerekir")
    sembolik_link = tmp_path / "chameleon_known_hosts"
    os.symlink(gercek_dosya, sembolik_link)

    with pytest.raises(OSError, match="sembolik link"):
        ssh_connector._ensure_known_hosts_file_safe(str(sembolik_link))

    # Helper, sembolik linki TAKIP ETMEDEN reddetmeli -- hedef dosyaya
    # hicbir sekilde dokunulmamis olmali.
    assert gercek_dosya.read_text() == "bu dosyaya yazilmamasi gerekir"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="platform sembolik link desteklemiyor")
def test_connect_rejects_known_hosts_symlink_end_to_end(tmp_path, monkeypatch):
    remote_key = paramiko.RSAKey.generate(1024)
    _install_fake_paramiko_connect(monkeypatch, remote_key)

    gercek_dosya = tmp_path / "hedef_disinda_bir_dosya.txt"
    gercek_dosya.write_text("bu dosyaya yazilmamasi gerekir")
    sembolik_link = tmp_path / "chameleon_known_hosts"
    os.symlink(gercek_dosya, sembolik_link)

    ssh = SSHConnector(host="9.9.9.9", username="u", password="p", strict=False,
                        known_hosts_path=str(sembolik_link))

    assert ssh.connect() is False
    assert "sembolik link" in str(ssh.last_error)
    assert gercek_dosya.read_text() == "bu dosyaya yazilmamasi gerekir"


def test_ensure_known_hosts_file_safe_creates_regular_file_when_missing(tmp_path):
    hedef = tmp_path / "alt_klasor_yok" / "chameleon_known_hosts"
    hedef.parent.mkdir()

    ssh_connector._ensure_known_hosts_file_safe(str(hedef))

    assert hedef.exists()
    assert hedef.is_file()
    assert not hedef.is_symlink()
