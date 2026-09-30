import errno
import getpass
import os
import stat
import sys
import threading
import paramiko

from socks5 import connect_via_socks5

# strict=False ("atla") modunda CHAMELEON_KNOWN_HOSTS'a yazma islemini
# BU SUREC icindeki SSHConnector'lar arasinda sirali yapar -- aksi halde
# iki baglanti (orn. ayni anda iki farkli hedefe TOFU ile baglanma) ayni
# dosyayi OKUYUP-degistirip-YAZDIGI icin (paramiko save_host_keys() butun
# HostKeys kumesini bastan yaziyor) biri digerinin az once ogrendigi
# anahtari ustune yazip kaybedebilirdi. Farkli SURECLER (orn. iki ayri
# Chameleon.exe) arasindaki yarisi bu kilit onlemez -- o cok daha nadir
# bir senaryo.
#
# ONEMLI (code review'da bulunan bir hata duzeltildi): bu kilit SADECE
# known_hosts'un okundugu/degistirildigi/yazildigi kritik bolumu korur --
# _TofuPolicy.missing_host_key() (bkz. asagisi) ve connect() SONRASI
# yapilan save_host_keys() cagrisi. client.connect()'in KENDISI (TCP+SSH
# el sikismasinin tamami) kilidin DISINDADIR. Onceki surum, TUM
# client.connect() cagrisini da bu kilidin ICINE aliyordu -- bu da
# modulun kendi amaciyla (N farkli hedefe PARALEL TOFU baglanma) TAM
# TERSI sonuc veriyordu: N hedef icin en kotu durumda calisma suresi
# N * connect_timeout'a kadar SIRALI hale geliyordu.
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
#
# Derlenmis (.exe) modda __file__ yerine sys.executable'a gore hesaplanir --
# aksi halde TOFU ile ogrenilen anahtarlar PyInstaller'in her calistirmada
# silinen gecici _MEIPASS klasorune yazilir ve bir SONRAKI calistirmada hic
# hatirlanmaz (chain_of_custody.LOG_DIR ile ayni gerekce, bkz. docs/roadmap.md).
if getattr(sys, "frozen", False):
    _ENGINE_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
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
        # NOT: paramiko'nun kendi AutoAddPolicy.missing_host_key()'i burada
        # hem bellekteki host_keys kumesine EKLER hem de HEMEN
        # save_host_keys() ile DISKE yazar -- ama bu cagri, client.connect()
        # SURERKEN (yani _TOFU_SAVE_LOCK'un artik kasitli olarak DISINDA
        # tuttugumuz bir noktada) gerceklesir. super().missing_host_key()'i
        # OLDUGU GIBI cagirmak, kilidin DISINDA korumasiz bir diske-yazma
        # yaratirdi -- tam olarak kilidin onlemeye calistigi yarisi. Bu
        # yuzden SADECE bellekteki ekleme yapilir (baglantinin devam
        # edebilmesi icin sart); diske YAZMA islemi connect() basarili
        # olduktan SONRA, kilit ICINDE, connect()'in kendisi tarafindan
        # tetiklenir (bkz. connect()'teki save_host_keys() cagrisi).
        client.get_host_keys().add(hostname, key.get_name(), key)


class _UnknownHostKeyError(paramiko.SSHException):
    """RejectPolicy ile AYNI islevi gorur (bilinmeyen host key -> reddet)
    ama kendi turunde -- connect()'in last_error_type'i, paramiko'nun
    hata METNINI (kirilgan, ic detay) arayarak degil, exception TURUNU
    kontrol ederek belirleyebilsin diye."""
    pass


class _StrictPolicy(paramiko.RejectPolicy):
    def missing_host_key(self, client, hostname, key):
        raise _UnknownHostKeyError(f"Server {hostname!r} not found in known_hosts")


def _ensure_known_hosts_file_safe(path):
    """CHAMELEON_KNOWN_HOSTS dosyasinin gercekten sade bir REGULAR dosya
    oldugunu (sembolik link DEGIL) dogrular, yoksa olusturur.

    Onceki surum, os.path.islink(path) ile AYRI bir kontrol (check) yapip
    SONRA open()/load_host_keys() (use) cagiriyordu -- klasik bir TOCTOU
    (time-of-check-to-time-of-use) acigi: kontrol ile gercek kullanim
    arasindaki pencerede, ayni makinede yazma izni olan baska bir yerel
    kullanici dosyayi bir sembolik linke DONUSTUREBILIRDI, kontrolun
    KENDISI bunu hic engellemiyordu (bir sonraki open() sessizce o linki
    takip ederdi).

    Burada onun yerine ACMA ile DOGRULAMA ayni ana toplanir:
      - Linux/macOS: os.O_NOFOLLOW ile acilir -- path bir sembolik link
        ise open() DOGRUDAN ELOOP ile basarisiz olur, TOCTOU penceresi
        hic OLUSMAZ.
      - Windows: os.O_NOFOLLOW tanimli degil (bu bayrak yok, SSH engine
        Windows'ta HEDEF makine olarak calisiyor ama operator/GUI tarafi
        Linux'ta da calisabiliyor -- bkz. tests/). Orada, AYRI bir
        islink() cagrisi yerine, ACILMIS OLAN fd'nin kendisi os.fstat()
        ile kontrol edilir -- acma ANINDAKI gercek dosya, ayrica
        cozumlenmis bir path degil.
    """
    flags = os.O_RDWR | os.O_CREAT
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | nofollow, 0o600)
    except OSError as exc:
        if nofollow and exc.errno == errno.ELOOP:
            raise OSError(f"{path} bir sembolik link -- guvenlik icin kullanilmadi.") from exc
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"{path} normal bir dosya degil -- guvenlik icin kullanilmadi.")
    finally:
        os.close(fd)


class SSHConnector:
    def __init__(self, host, port=22, username=None, password=None,
                 key_path=None, known_hosts_path=None, strict=True,
                 socks_proxy_port=None, connect_timeout=10):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.known_hosts_path = known_hosts_path or CHAMELEON_KNOWN_HOSTS
        self.strict = strict
        # Varsayilan 10sn cogu durumda yeterli, ama Tor gibi yuksek
        # gecikmeli baglantilarda erken zaman asimina yol acabilir --
        # ihtiyaç halinde caginin bunu artirabilmesi icin parametre olarak
        # disariya acildi (GUI'ye simdilik yansitilmadi, sadece kod
        # seviyesinde -- gereksiz bir "gelismis ayarlar" paneli eklemeden).
        self.connect_timeout = connect_timeout
        self.client = None
        # connect() basarili olup strict=False ise, sunucunun kimliginin bu
        # baglantida ILK KEZ mi ogrenildigi ("learned") yoksa CHAMELEON_KNOWN_HOSTS'ta
        # ONCEDEN kayitli bir anahtarla mi eslestigi ("known") burada tutulur --
        # strict=True ise ya da baglanti basarisizsa None kalir.
        self.host_key_status = None
        # connect() basarili olunca sunucunun host key'inin okunakli
        # parmak izi -- delil zincirine sadece "ogrenildi/biliniyor" DEGIL,
        # TAM OLARAK HANGI kimlige guvenildigini de kaydedebilmek icin
        # (bkz. gui_v2.py). GERCEKTEN SHA256 (paramiko PKey.fingerprint,
        # "SHA256:<base64>" bicimi) -- modern OpenSSH araclarinin
        # (ssh-keygen -lf, ssh -v) VARSAYILAN gosterdigi bicimle AYNI,
        # bagimsiz bir kaynaktan alinan parmak iziyle dogrudan
        # karsilastirilabilir. (Onceki surum PKey.get_fingerprint()'in
        # MD5 digest'ini "SHA256 fingerprint" diye YANLIS etiketleyip
        # kaydediyordu -- modern araclarin SHA256 ciktisiyla ASLA
        # eslesmeyen, delil zincirindeki bagimsiz dogrulama amacini
        # sessizce bosa cikaran bir hataydi; code review'da bulundu.)
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
                # diske YAZAMAZ.
                #
                # Bu hazirlik (dizin olusturma + dosyanin guvenli
                # acilmasi/olusturulmasi + okunmasi) _TOFU_SAVE_LOCK'un
                # DISINDA yapilir -- burada sadece OKUMA var, ayni anda
                # baska bir SSHConnector'in da okumasi zararsizdir; yarisi
                # olusturacak asil islem (DISKE YAZMA) asagida, connect()
                # basarili olduktan SONRA, ayri ve kucuk bir kilitli
                # bolumde yapilir.
                if os.path.dirname(self.known_hosts_path):
                    os.makedirs(os.path.dirname(self.known_hosts_path), exist_ok=True)
                _ensure_known_hosts_file_safe(self.known_hosts_path)
                self.client.load_host_keys(self.known_hosts_path)
                tofu_policy = _TofuPolicy()
                self.client.set_missing_host_key_policy(tofu_policy)

            # client.connect() (TCP acilisi + SSH el sikismasi, Tor gibi
            # yuksek gecikmeli baglantilarda connect_timeout'a kadar
            # surebilir) BILEREK _TOFU_SAVE_LOCK'un DISINDA -- code
            # review'da bulunan bir hata duzeltildi: onceki surum bunu
            # kilidin ICINE aliyordu, bu da modulun kendi amaciyla (N
            # farkli hedefe PARALEL TOFU baglanma) TAM TERSI sonuc
            # veriyordu (N hedef icin en kotu durumda sirali calisma).
            # strict=False'ta bilinmeyen bir host key gelirse
            # _TofuPolicy.missing_host_key() (yukarida) SADECE bellege
            # ekler, diske YAZMAZ -- o adim connect() basarili olduktan
            # sonra asagida, kilit icinde yapilir.
            connect_kwargs = self._build_connect_kwargs()
            self.client.connect(**connect_kwargs)

            if tofu_policy is not None:
                self.host_key_status = "learned" if tofu_policy.learned_new_key else "known"
                if tofu_policy.learned_new_key:
                    # Kritik bolum: known_hosts'a GERCEK diske-yazma burada,
                    # kilit icinde olur. save_host_keys() cagirmadan once
                    # kendi icinde dosyayi TEKRAR diskten yukleyip mevcut
                    # kayitlarla BIRLESTIRIR (paramiko'nun kendi davranisi,
                    # bkz. SSHClient.save_host_keys() kaynagi) -- yani baska
                    # bir thread'in bu kilit disindayken (connect() surerken)
                    # ogrenip kaydettigi baska bir sunucunun anahtari da
                    # kaybolmadan korunur.
                    with _TOFU_SAVE_LOCK:
                        self.client.save_host_keys(self.known_hosts_path)

            transport = self.client.get_transport()
            if transport is not None:
                remote_key = transport.get_remote_server_key()
                if remote_key is not None:
                    # PKey.fingerprint (paramiko >= 3.2): GERCEK SHA256,
                    # "SHA256:<base64>" bicimi -- ssh-keygen -lf / ssh -v
                    # varsayilaniyla AYNI. PKey.get_fingerprint() (onceki
                    # surumde kullanilan) MD5 digest doner, SHA256 DEGILDIR.
                    self.host_key_fingerprint = remote_key.fingerprint
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
            "timeout": self.connect_timeout,
            "look_for_keys": True,
            "allow_agent": True,
        }

        if self.socks_proxy_port:
            # .onion adresleri normal DNS ile cozulemez -- TCP
            # baglantisini biz acip paramiko'ya hazir soket olarak
            # veriyoruz (paramiko kendi baglanti mantigini atlar).
            # self.connect_timeout burada ACIKCA iletiliyor -- code
            # review'da bulunan bir hata duzeltildi: onceki surum burada
            # hicbir timeout iletmiyordu, socks5.py'deki sabit varsayilan
            # (15sn) kullaniliyordu. Cagiran self.connect_timeout'u ozellikle
            # yuksek gecikmeli Tor baglantilari icin yukseltse bile, SOCKS5
            # CONNECT el sikismasi (Tor uzerinden en uzun suren asama) hala
            # sabit 15sn'de zaman asimina ugruyordu.
            connect_kwargs["sock"] = connect_via_socks5(
                "127.0.0.1", self.socks_proxy_port, self.host, self.port,
                timeout=self.connect_timeout,
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

            # Standart paramiko deseni: ONCE stdout/stderr TAMAMEN okunur,
            # SONRA recv_exit_status() cagirilir -- code review'da bulunan
            # klasik bir paramiko kilitlenme deseni duzeltildi. Onceki
            # surum recv_exit_status()'u (timeout'suz) stdout/stderr hic
            # okunmadan ONCE cagiriyordu; uzak komutun ciktisi SSH
            # kanalinin flow-control penceresini asarsa (orn.
            # list_remote_files()'in buyuk bir dizin agacinda calistirdigi
            # "find <dir> -type f"), uzak komut dolu bir pipe'a yazmaya
            # calisirken BLOKE OLUR ve hic bitmez; kimse stdout okumadigi
            # icin recv_exit_status() de SONSUZA KADAR bekler -- tum imaj
            # alma thread'i kurtarilamaz sekilde kilitlenirdi. stdout.read()
            # (ve stderr.read()) kanal kapanana kadar okur; bu da uzak
            # tarafin flow-control penceresini surekli bosaltip tikanmayi
            # onler, exit status ancak bundan SONRA guvenle alinabilir.
            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0 and error:
                print(f"[SSH] Komut hatası (Kod {exit_status}): {error}")

            return output, error, exit_status

        except Exception as e:
            print(f"[SSH] Komut calistirilamadi: {e}")
            return None, None, None

    # Geriye dönük uyumluluk için eski isim
    execute_command = run_command

    def list_disks(self):
        """
        Uzak Linux sistemindeki diskleri listeler. MODEL,SERIAL kolonlari,
        rapora yazilan kaynak tanimini path yerine (orn. /dev/sdb yerine
        gercek disk modeli/seri no) desteklemek icin eklendi -- ISO/IEC
        27037'nin istedigi "delilin benzersiz tanimlanmasi" gereksinimi.
        """
        command = "lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL,SERIAL"
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