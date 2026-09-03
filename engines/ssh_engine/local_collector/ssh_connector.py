import getpass
import os
import paramiko

from socks5 import connect_via_socks5

# NOT: Test/demo sunucusunda, SSH ile baglanilan kullanicinin
# /etc/sudoers dosyasinda blockdev ve dd gibi komutlar icin NOPASSWD
# tanimli olmasi gerekir. Aksi halde run_command() ile calistirilan
# "sudo ..." komutlari parola isteyip otomatik akisi durdurabilir/asili
# birakabilir (write_block_helper.py bu yuzden get_pty=True kullanir,
# ama bu sadece "no tty" hatasini onler, parola isteme ihtiyacini degil).


class SSHConnector:
    def __init__(self, host, port=22, username=None, password=None,
                 key_path=None, known_hosts_path=None, strict=True,
                 socks_proxy_port=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.known_hosts_path = known_hosts_path or os.path.expanduser("~/.ssh/known_hosts")
        self.strict = strict
        self.client = None
        # socks_proxy_port verilirse (Tor senaryosu -- host bir .onion
        # adresi), TCP baglantisi dogrudan degil, 127.0.0.1:<bu port>'taki
        # yerel Tor SOCKS proxy'si uzerinden acilir. Mevcut duz SSH yolu
        # (socks_proxy_port=None) hicbir sekilde degismez.
        self.socks_proxy_port = socks_proxy_port

    def connect(self):
        """Uzak sunucuya güvenli bir şekilde SSH bağlantısı kurar."""
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()

            if self.known_hosts_path and os.path.exists(self.known_hosts_path):
                self.client.load_host_keys(self.known_hosts_path)

            if self.strict:
                # Bilinmeyen host key gelirse bağlantıyı REDDET
                self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                # Sadece bilinçli olarak test ortamında kullanın
                self.client.set_missing_host_key_policy(paramiko.WarningPolicy())

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

            self.client.connect(**connect_kwargs)

            # Uzun surebilecek imaj alma islemlerinde firewall/NAT/cloud LB
            # gibi ara katmanlarin "bosta" gordugu baglantiyi sessizce
            # kapatmasini onlemek icin periyodik keepalive paketi gonderilir.
            transport = self.client.get_transport()
            if transport is not None:
                transport.set_keepalive(15)

            print(f"[SSH] Güvenli bağlantı başarılı: {self.host}:{self.port}")
            return True

        except paramiko.SSHException as ssh_err:
            print(f"[SSH] Güvenlik / Protokol hatası: {ssh_err}")
            return False
        except Exception as e:
            print(f"[SSH] Bağlantı hatası: {e}")
            return False

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