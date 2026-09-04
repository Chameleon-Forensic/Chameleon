import contextlib
import getpass
import os
import threading
import paramiko

from socks5 import connect_via_socks5

# strict=False ("atla") modunda CHAMELEON_KNOWN_HOSTS'a yazma islemini
# (load + connect + paramiko'nun ic AutoAddPolicy kaydi) BU SUREC icindeki
# SSHConnector'lar arasinda sirali yapar -- aksi halde iki baglanti
# (orn. ayni anda iki farkli hedefe TOFU ile baglanma) ayni dosyayi
# OKUYUP-degistirip-YAZDIGI icin (paramiko save_host_keys() butun HostKeys
# kumesini bastan yaziyor) biri digerinin az once ogrendigi anahtari
# ustune yazip kaybedebilirdi. Farkli SURECLER (orn. iki ayri Chameleon.exe)
# arasindaki yarisi bu kilit onlemez -- o cok daha nadir bir senaryo.
_TOFU_SAVE_LOCK = threading.Lock()

# NOT: Test/demo sunucusunda, SSH ile baglanilan kullanicinin
# /etc/sudoers dosyasinda blockdev ve dd gibi komutlar icin NOPASSWD
# tanimli olmasi gerekir. Aksi halde run_command() ile calistirilan
# "sudo ..." komutlari parola isteyip otomatik akisi durdurabilir/asili
# birakabilir (write_block_helper.py bu yuzden get_pty=True kullanir,
# ama bu sadece "no tty" hatasini onler, parola isteme ihtiyacini degil).

# strict=False ("Dogrulamayi atla") secildiginde host key'lerin
# kaydedildigi, Chameleon'a ozel known_hosts dosyasi -- kullanicinin
# gercek ~/.ssh/known_hosts'unu HIC degistirmiyoruz (kisisel SSH
# kullanimini kirletmesin, Chameleon'un kendi guven listesi kisisel SSH
# istemcisinin guvenini de sessizce kullanmasin diye ayri tutuldu).
# keys/operator_tor_key.json ile AYNI dizin/desen (bkz. gui_v2.py,
# .gitignore'daki **/ssh_engine/keys/ zaten bunu da kapsiyor).
_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAMELEON_KNOWN_HOSTS = os.path.join(_ENGINE_ROOT, "keys", "chameleon_known_hosts")


class _TofuPolicy(paramiko.AutoAddPolicy):
    """AutoAddPolicy + bir bayrak: bu baglantida sunucunun kimligi
    GERCEKTEN ilk kez mi ogrenildi (once hic bilinmiyordu, simdi
    CHAMELEON_KNOWN_HOSTS'a kaydedildi) yoksa zaten bilinen/eslesen bir
    anahtarla mi baglanildi -- paramiko'nun kendisi bu ikisini ayirt
    etmiyor (missing_host_key() SADECE ilk durumda cagrilir), ama
    SSHConnector.connect() sonrasinda GUI'nin/chain-of-custody'nin
    "ilk kez guvenildi" ile "onceden bilinen sunucuya baglanildi"
    arasindaki farki gosterebilmesi icin bu bilgi gerekli.

    Onemli: sunucunun anahtari DEGISMISSE (once bilinen bir host'un
    key'i farkliysa) bu policy hic devreye girmez -- paramiko boyle bir
    durumda missing_host_key()'i degil, dogrudan BadHostKeyException
    firlatir (bkz. connect()'teki ayri except bloğu). Yani "atla"
    modunda bile, DEGISEN bir sunucu kimligi sessizce gecilmez."""

    def __init__(self):
        super().__init__()
        self.learned_new_key = False

    def missing_host_key(self, client, hostname, key):
        self.learned_new_key = True
        super().missing_host_key(client, hostname, key)


class _UnknownHostKeyError(paramiko.SSHException):
    """RejectPolicy ile AYNI islevi gorur (bilinmeyen host key -> reddet)
    ama kendi turunde -- connect()'in last_error_type'i, paramiko'nun
    hata METNINI (kirilgan, ic detay) arayarak degil, exception TURUNU
    kontrol ederek belirleyebilsin diye."""
    pass


class _StrictPolicy(paramiko.RejectPolicy):
    def missing_host_key(self, client, hostname, key):
        raise _UnknownHostKeyError(f"Server {hostname!r} not found in known_hosts")


class SSHConnector:
    def __init__(self, host, port=22, username=None, password=None,
                 key_path=None, known_hosts_path=None, strict=True,
                 socks_proxy_port=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.known_hosts_path = known_hosts_path or CHAMELEON_KNOWN_HOSTS
        self.strict = strict
        self.client = None
        # connect() basarili olup strict=False ise, sunucunun kimliginin bu
        # baglantida ILK KEZ mi ogrenildigi ("learned") yoksa CHAMELEON_KNOWN_HOSTS'ta
        # ONCEDEN kayitli bir anahtarla mi eslestigi ("known") burada tutulur --
        # strict=True ise ya da baglanti basarisizsa None kalir.
        self.host_key_status = None
        # connect() basarili olunca sunucunun host key'inin okunakli
        # parmak izi (SHA256, paramiko'nun kendi bicimi) -- delil zincirine
        # sadece "ogrenildi/biliniyor" DEGIL, TAM OLARAK HANGI kimlige
        # guvenildigini de kaydedebilmek icin (bkz. gui_v2.py).
        self.host_key_fingerprint = None
        # socks_proxy_port verilirse (Tor senaryosu -- host bir .onion
        # adresi), TCP baglantisi dogrudan degil, 127.0.0.1:<bu port>'taki
        # yerel Tor SOCKS proxy'si uzerinden acilir. Mevcut duz SSH yolu
        # (socks_proxy_port=None) hicbir sekilde degismez.
        self.socks_proxy_port = socks_proxy_port
        # connect() basarisiz olursa GUI'nin kullaniciya "ne yapmasi gerektigini"
        # soyleyebilmesi icin son hatanin turu burada saklanir. Degerler:
        # "host_key" (sunucunun kimligi known_hosts'ta yok, strict=True reddetti),
        # "auth" (kullanici adi/sifre/anahtar yanlis), "unreachable" (aga hic
        # ulasilamadi -- port kapali/sunucu kapali/firewall), "other".
        self.last_error = None
        self.last_error_type = None

    def connect(self):
        """Uzak sunucuya güvenli bir şekilde SSH bağlantısı kurar."""
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()

            tofu_policy = None
            # strict=False'ta CHAMELEON_KNOWN_HOSTS'a yazilabildigi icin
            # (bkz. _TOFU_SAVE_LOCK aciklamasi) o dal kilit altinda; strict
            # hicbir sey yazmadigi icin kilide hic girmiyor.
            lock = _TOFU_SAVE_LOCK if not self.strict else contextlib.nullcontext()
            with lock:
                if self.strict:
                    if self.known_hosts_path and os.path.exists(self.known_hosts_path):
                        self.client.load_host_keys(self.known_hosts_path)
                    # Bilinmeyen host key gelirse bağlantıyı REDDET
                    self.client.set_missing_host_key_policy(_StrictPolicy())
                else:
                    # "Doğrulamayı atla": ilk bağlantıda sunucunun kimliğini
                    # CHAMELEON_KNOWN_HOSTS'a kaydeder (paramiko'nun load_host_keys()
                    # ile ayarladığı _host_keys_filename sayesinde AutoAddPolicy
                    # otomatik yazıyor), sonraki bağlantılarda o kayıtla
                    # karşılaştırır. Bilinmeyen bir sunucuyu sessizce kabul eder
                    # AMA daha önce bilinen bir sunucunun kimliği değişirse
                    # (aşağıdaki BadHostKeyException'a bakın) sessizce GEÇMEZ.
                    # Dosya ONCEDEN yoksa bile load_host_keys() cagirilmali --
                    # aksi halde paramiko'nun _host_keys_filename'i hic
                    # ayarlanmaz ve AutoAddPolicy ilk ogrendigi anahtari
                    # diske YAZAMAZ (once bos dosya olusturulup sonra
                    # yukleniyor, load_host_keys() var olmayan dosyada
                    # IOError firlatiyor).
                    if os.path.dirname(self.known_hosts_path):
                        os.makedirs(os.path.dirname(self.known_hosts_path), exist_ok=True)
                    if os.path.islink(self.known_hosts_path):
                        # Bu dosyanin yerine biri (ayni makinede baska bir
                        # yerel kullanici) sembolik link koymus olabilir --
                        # oyle bir dosyaya paramiko'nun kendi yazmasina izin
                        # vermek yerine erken ve acikca hata veriyoruz.
                        raise OSError(f"{self.known_hosts_path} bir sembolik link -- guvenlik icin kullanilmadi.")
                    if not os.path.exists(self.known_hosts_path):
                        open(self.known_hosts_path, "a").close()
                    self.client.load_host_keys(self.known_hosts_path)
                    tofu_policy = _TofuPolicy()
                    self.client.set_missing_host_key_policy(tofu_policy)

                connect_kwargs = self._build_connect_kwargs()
                self.client.connect(**connect_kwargs)

                if tofu_policy is not None:
                    self.host_key_status = "learned" if tofu_policy.learned_new_key else "known"

            transport = self.client.get_transport()
            if transport is not None:
                remote_key = transport.get_remote_server_key()
                if remote_key is not None:
                    self.host_key_fingerprint = remote_key.get_fingerprint().hex(":")
                # Uzun surebilecek imaj alma islemlerinde firewall/NAT/cloud
                # LB gibi ara katmanlarin "bosta" gordugu baglantiyi
                # sessizce kapatmasini onlemek icin periyodik keepalive.
                transport.set_keepalive(15)

            print(f"[SSH] Güvenli bağlantı başarılı: {self.host}:{self.port}")
            return True

        except _UnknownHostKeyError as unk_err:
            self.last_error, self.last_error_type = unk_err, "host_key"
            print(f"[SSH] Güvenlik / Protokol hatası: {unk_err}")
            return False
        except paramiko.BadHostKeyException as bhk_err:
            # Sunucunun kimligi ONCEDEN biliniyordu ama SIMDI FARKLI --
            # strict=True/False farketmez, bu durum HICBIR ZAMAN sessizce
            # gecilmez (paramiko'nun kendi davranisi). Gercek bir "ortadaki
            # adam" saldirisi ya da sunucunun gercekten degistigi (orn.
            # yeniden kurulum) anlamina gelebilir.
            self.last_error, self.last_error_type = bhk_err, "host_key_mismatch"
            print(f"[SSH] UYARI: Sunucunun kimliği daha önce bildiğimizden FARKLI! {bhk_err}")
            return False
        except paramiko.AuthenticationException as auth_err:
            self.last_error, self.last_error_type = auth_err, "auth"
            print(f"[SSH] Kimlik doğrulama hatası: {auth_err}")
            return False
        except paramiko.SSHException as ssh_err:
            self.last_error, self.last_error_type = ssh_err, "other"
            print(f"[SSH] Güvenlik / Protokol hatası: {ssh_err}")
            return False
        except OSError as sock_err:
            # Baglanti reddedildi/timeout/DNS cozulemedi -- hepsi OSError alt
            # sinifi: sunucuya ag seviyesinde hic ulasilamadigi anlamina gelir.
            self.last_error, self.last_error_type = sock_err, "unreachable"
            print(f"[SSH] Bağlantı hatası: {sock_err}")
            return False
        except Exception as e:
            self.last_error, self.last_error_type = e, "other"
            print(f"[SSH] Bağlantı hatası: {e}")
            return False

    def _build_connect_kwargs(self):
        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": 10,
            "look_for_keys": True,
            "allow_agent": True,
        }

        if self.socks_proxy_port:
            # .onion adresleri normal DNS ile cozulemez -- TCP
            # baglantisini biz acip paramiko'ya hazir soket olarak
            # veriyoruz (paramiko kendi baglanti mantigini atlar).
            connect_kwargs["sock"] = connect_via_socks5(
                "127.0.0.1", self.socks_proxy_port, self.host, self.port,
            )
            # look_for_keys/allow_agent, sock uzerinden baglanirken de
            # gecerli kalir; sadece hostname/port artik sadece SSH
            # protokol seviyesinde (banner/host key dogrulama) kullanilir.

        if self.key_path and os.path.exists(self.key_path):
            connect_kwargs["key_filename"] = self.key_path
            if self.password:
                connect_kwargs["passphrase"] = self.password
        elif self.password:
            connect_kwargs["password"] = self.password
        else:
            raise ValueError("Ne key ne de parola sağlanmadı.")

        return connect_kwargs

    def is_active(self):
        """Alttaki transport hala canli mi (paket duzeyinde) kontrol eder."""
        if self.client is None:
            return False
        transport = self.client.get_transport()
        return transport is not None and transport.is_active()

    def reconnect(self):
        """
        Kopmus bir baglantiyi ayni kimlik bilgileriyle yeniden kurar.
        Onceki (olu) client kapatilip yeni bir client olusturulur; boylece
        image_acquirer.py gibi cagiran kod, baglanti koptugunda islemi
        bastan baslatmak yerine kaldigi yerden devam edebilir.
        """
        self.close()
        return self.connect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def run_command(self, command, get_pty=False, sudo_password=None):
        """
        Uzak sunucuda komut çalıştırır, (stdout, stderr, exit_code) üçlüsünü
        döner. Bağlantı yoksa ya da komut çalıştırılamazsa (None, None, None)
        döner.

        get_pty=True: sudo gerektiren komutlar (örn. blockdev) için TTY
        talep eder — aksi halde sudo "no tty present and no askpass program"
        hatasıyla başarısız olur. NOT: TTY açıldığında uzak taraf stdout ve
        stderr'i genelde TEK akışta birleştirir; bu durumda stderr boş
        dönebilir, gerçek hata mesajı stdout içinde görünür. Bu yalnızca
        sudo'nun "no tty" hatasını önler; hedef hesapta NOPASSWD tanımlı
        değilse sudo yine de parola ister (bkz. docs/PROJE_TALIMATI.md).

        sudo_password verilirse: komutun başına "sudo -S " eklenir ve parola,
        komut metnine hiç YAZILMADAN doğrudan SSH stdin kanalı üzerinden
        gönderilir. Bunu (parolayı f-string ile komut satırına gömmek yerine)
        tercih etmenin sebebi: parola komut metninde olursa hem shell
        injection riski oluşur (parolada `'` gibi bir karakter komutu
        bozabilir/başka komut çalıştırabilir) hem de parola uzak sunucuda
        `ps aux` ile bir süreliğine görünür olabilir. Bu yöntemde parola
        şifreli SSH kanalından geçer, komut satırında hiç yer almaz.
        """
        if self.client is None:
            print("[SSH] Önce SSH bağlantısı kurulmalıdır.")
            return None, None, None

        if sudo_password is not None:
            command = f"sudo -S {command}"

        try:
            stdin, stdout, stderr = self.client.exec_command(command, get_pty=get_pty)

            if sudo_password is not None:
                stdin.write(sudo_password + "\n")
                stdin.flush()

            # Büyük çıktılarda kilitlenmeyi önlemek için kanalı bekliyoruz
            exit_status = stdout.channel.recv_exit_status()

            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")

            if exit_status != 0 and error:
                print(f"[SSH] Komut hatası (Kod {exit_status}): {error}")

            return output, error, exit_status

        except Exception as e:
            print(f"[SSH] Komut calistirilamadi: {e}")
            return None, None, None

    # Geriye dönük uyumluluk için eski isim
    execute_command = run_command

    def list_disks(self):
        """Uzak Linux sistemindeki diskleri listeler."""
        command = "lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT"
        output, _error, _exit_status = self.run_command(command)
        return output

    def close(self):
        """SSH bağlantısını kapatır."""
        if self.client:
            self.client.close()
            self.client = None
            print("[SSH] Bağlantı kapatıldı.")


if __name__ == "__main__":
    # Modülü tek başına test etmek için basit soru-cevap
    HOST = input("SSH Host: ").strip()
    PORT_INPUT = input("SSH Port [22]: ").strip()
    PORT = int(PORT_INPUT) if PORT_INPUT else 22
    USERNAME = input("SSH Kullanici adi: ").strip()
    PASSWORD = getpass.getpass("SSH Sifre (bos birakilabilir): ").strip() or None

    if not HOST or not USERNAME:
        print("[HATA] Host ve kullanici adi bos birakilamaz.")
        exit(1)

    print(f"Baglaniliyor: {USERNAME}@{HOST}:{PORT}")

    ssh = SSHConnector(host=HOST, port=PORT, username=USERNAME,
                        password=PASSWORD, strict=True)
    try:
        if ssh.connect():
            print("\n[SSH] Uzak diskler:")
            disks = ssh.list_disks()
            if disks:
                print(disks)
    finally:
        ssh.close()