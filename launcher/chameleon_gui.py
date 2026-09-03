"""
chameleon_gui.py
Chameleon ana ekrani (PySide6). Tek giris noktasi: sol sidebar navigasyon
+ tanitim sayfalari + Vaka Bilgileri on-ekrani + gercek SSH (gui_v2.py) ve
RAM (ram_gui.py) ekranlarina gecis. Bu dosyanin kendisi SAF UI'dir --
hicbir SSH/Tor/disk/RAM mantigina dogrudan dokunmuyor.

customtkinter surumunden PySide6'ya tam gecis tamamlandi (bkz.
docs/roadmap.md, docs/oturum_ozeti.md) -- eski dosyalar kaldirildi.
"""

import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSizePolicy, QSplashScreen, QStackedWidget,
    QVBoxLayout, QWidget,
)

if getattr(sys, "frozen", False):
    PROJECT_ROOT = sys._MEIPASS
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHARED_DIR = os.path.join(PROJECT_ROOT, "shared")
sys.path.insert(0, SHARED_DIR)
sys.path.insert(0, os.path.join(SHARED_DIR, "i18n"))
from strings import t  # noqa: E402
import version  # noqa: E402
from ui_kit import theme_qt as ui, fonts, icons, widgets  # noqa: E402

SSH_ENGINE_DIR = os.path.join(PROJECT_ROOT, "engines", "ssh_engine", "local_collector")
RAM_ENGINE_DIR = os.path.join(PROJECT_ROOT, "engines", "ram_engine")
ICON_PNG = os.path.join(SHARED_DIR, "assets", "chameleon_icon.png")

# Sidebar'dan acilan her yontemin tanitim sayfasi -- chameleon_gui.py'deki
# METHOD_INFO ile AYNI icerik (veri, UI degil), oradan degistirmeden
# tasindi.
METHOD_INFO = {
    "direct": {
        "tr": {
            "title": "Doğrudan / Port Yönlendirme ile İmaj Al",
            "icon": "link",
            "short": "Hedefe ağ üzerinden doğrudan ulaşabiliyorsanız -- en basit, en hızlı yöntem",
            "what": (
                "Hedef bilgisayara ağ üzerinden doğrudan ulaşabiliyorsanız (aynı ağdaysanız "
                "ya da router'da bir port yönlendirme kuralı eklenmişse) kullanılan en basit "
                "ve en hızlı yöntem. SSH ile bağlanıp disk ya da tek dosya/klasör imajı alır."
            ),
            "when": [
                "Hedef bilgisayar sizinle aynı ağdaysa (örn. aynı ofis/lab ağı)",
                "Hedef, internete çıkan bir router'ın arkasındaysa VE o router'da port yönlendirme "
                "kuralı ekleyebiliyorsanız (örn. dış port 5632 → hedefin 22 portu)",
            ],
            "requires": [
                "Hedefte çalışan bir SSH sunucusu (Linux: sshd, Windows: OpenSSH Server)",
                "Hedefin IP adresi ve SSH portu (port yönlendirmedeyse router'ın dış IP'si + yönlendirilen port)",
                "Kullanıcı adı + parola YA DA bir SSH özel anahtarı",
                "Tam disk modunda: hedefte sudo/yönetici yetkisi",
            ],
            "steps": [
                "\"Başlat\"a basıp (isteğe bağlı) vaka bilgilerini girin",
                "Host alanına hedefin IP'sini (port yönlendirmedeyse router'ın dış IP'sini), "
                "Port alanına SSH portunu yazın",
                "Kullanıcı adı ve parola/anahtar girin",
                "\"Bağlantı Yöntemi\"nde \"Doğrudan / Port Yönlendirme\" seçili geldiğini kontrol edin",
                "\"Bağlan ve Diskleri Listele\"ye basın",
                "Hedef işletim sistemini ve ne alınacağını seçip \"İmaj Almayı Başlat\"a basın",
            ],
            "warning": None,
        },
        "en": {
            "title": "Direct / Port Forwarding Acquisition",
            "icon": "link",
            "short": "Use this when you can reach the target directly over the network -- simplest, fastest method",
            "what": (
                "The simplest and fastest method, used when you can reach the target computer "
                "directly over the network (same network, or a port-forwarding rule set up on "
                "the router). Connects via SSH and acquires a disk image or a single file/folder."
            ),
            "when": [
                "The target computer is on the same network as you (e.g. same office/lab network)",
                "The target is behind a router with internet access AND you can add a port "
                "forwarding rule on that router (e.g. external port 5632 -> target's port 22)",
            ],
            "requires": [
                "An SSH server running on the target (Linux: sshd, Windows: OpenSSH Server)",
                "The target's IP address and SSH port (if port forwarding, the router's external IP + forwarded port)",
                "A username + password OR an SSH private key",
                "For full-disk mode: sudo/administrator privileges on the target",
            ],
            "steps": [
                "Click \"Start\" and (optionally) enter the case information",
                "Enter the target's IP in the Host field (or the router's external IP if port "
                "forwarding), and the SSH port in the Port field",
                "Enter the username and password/key",
                "Check that \"Direct / Port Forwarding\" is selected under \"Connection Method\"",
                "Click \"Connect and List Disks\"",
                "Select the target OS and what to acquire, then click \"Start Acquisition\"",
            ],
            "warning": None,
        },
    },
    "vpn": {
        "tr": {
            "title": "VPN ile İmaj Al",
            "icon": "shield",
            "short": "Bilgisayarınız hedefin ağına VPN ile bağlıysa kullanılır",
            "what": (
                "Bilgisayarınız zaten hedefin bulunduğu ağa bir VPN tüneliyle bağlıysa kullanılır. "
                "Teknik olarak Doğrudan bağlantıyla AYNIDIR -- SSH direkt kurulur, Tor gibi ekstra "
                "bir katman yoktur. Tek fark: VPN üzerinden erişilebilir bir IP kullanırsınız ve bu "
                "delil zincirinde ayrıca kayıt altına alınır."
            ),
            "when": [
                "Hedef ağa doğrudan erişiminiz yok ama kurumsal/uzak bir VPN'e bağlanabiliyorsanız "
                "(örn. şirketin kendi VPN'i, bir müşterinin size sağladığı VPN erişimi)",
            ],
            "requires": [
                "Zaten KURULU ve BAĞLI durumda bir VPN istemcisi -- Chameleon VPN bağlantısını "
                "kendisi KURMAZ, bu adımı kendi VPN yazılımınızla önceden siz yaparsınız",
                "VPN üzerinden hedefin IP adresine erişim",
                "Hedefte çalışan bir SSH sunucusu + kullanıcı adı/parola ya da anahtar",
            ],
            "steps": [
                "Önce kendi VPN istemcinizle hedef ağa bağlanın (bu adım Chameleon'un DIŞINDA yapılır)",
                "\"Başlat\"a basıp (isteğe bağlı) vaka bilgilerini girin",
                "Host alanına hedefin VPN üzerinden erişilebilir IP'sini yazın",
                "\"Bağlantı Yöntemi\"nde \"VPN\" seçili geldiğini kontrol edin",
                "\"Bağlan ve Diskleri Listele\"ye basıp normal şekilde devam edin",
            ],
            "warning": None,
        },
        "en": {
            "title": "VPN Acquisition",
            "icon": "shield",
            "short": "Use this when your computer is connected to the target's network via VPN",
            "what": (
                "Used when your computer is already connected to the target's network through a "
                "VPN tunnel. Technically IDENTICAL to Direct connection -- SSH is set up directly, "
                "there is no extra layer like Tor. The only difference: you use an IP reachable "
                "through the VPN, and this is separately recorded in the chain of custody."
            ),
            "when": [
                "You have no direct access to the target network but can connect to a corporate/"
                "remote VPN (e.g. the company's own VPN, VPN access provided by a client)",
            ],
            "requires": [
                "A VPN client that is already INSTALLED and CONNECTED -- Chameleon does NOT set "
                "up the VPN connection itself, you do this beforehand with your own VPN software",
                "Access to the target's IP address over the VPN",
                "An SSH server running on the target + username/password or key",
            ],
            "steps": [
                "First connect to the target network with your own VPN client (this step happens OUTSIDE Chameleon)",
                "Click \"Start\" and (optionally) enter the case information",
                "Enter the target's IP reachable over the VPN in the Host field",
                "Check that \"VPN\" is selected under \"Connection Method\"",
                "Click \"Connect and List Disks\" and continue as normal",
            ],
            "warning": None,
        },
    },
    "tor": {
        "tr": {
            "title": "Tor (Acil Durum) ile İmaj Al",
            "icon": "shield-alert",
            "short": "Hedef ağa HİÇ erişiminiz yoksa kullanılan son çare -- yavaştır",
            "what": (
                "Hedef ağa HİÇBİR şekilde erişiminiz yoksa (ne doğrudan, ne VPN, ne port "
                "yönlendirme) kullanılan son çare yöntem. Sahaya götürülen bir USB \"taşınabilir "
                "kit\", hedef cihazda çalıştırılınca kendiliğinden Tor ağı üzerinden dışarıya "
                "açılan bir adres (.onion) oluşturur -- router'da hiçbir ayar yapmadan, hiçbir "
                "port açmadan. Bu adrese sadece SİZİN (operatörün) özel anahtarınıza sahip olan "
                "bağlanabilir; adresi başka biri ele geçirse bile işe yaramaz."
            ),
            "when": [
                "Hedef şirketin ağına hiçbir yetkiniz/erişiminiz yoksa (router'a giremiyorsunuz, "
                "IT departmanından yardım alamıyorsunuz ya da vakit yok)",
                "VPN de kurulamıyorsa",
            ],
            "requires": [
                "Önce SİZİN bir \"operatör anahtarı\" oluşturmuş olmanız -- \"Başlat\"a basınca "
                "açılan ekranda otomatik üretilir/gösterilir, ilk seferinde yapılır",
                "Bu anahtarı, SAHA ZİYARETİNDEN ÖNCE, taşınabilir kiti hazırlayacak/götürecek "
                "kişiye vermiş olmanız -- kit bu anahtarla önceden hazırlanmalıdır",
                "Sahadaki kişinin taşınabilir kiti hedef cihazda (USB'den) çalıştırmış olması",
                "Kit'in ürettiği \".onion\" adresinin size ulaştırılmış olması -- sahadaki kişi "
                "bunu KENDİ telefonuyla iletir, delil cihazının ağı/uygulamaları hiç kullanılmaz",
            ],
            "steps": [
                "\"Başlat\"a basınca açılan ekrandaki \"Operatör Anahtarım\" kutusundan anahtarınızı "
                "\"Kopyala\" ile alın ve sahadaki kişiye ÖNCEDEN iletin",
                "Sahadaki kişi taşınabilir kiti hedef cihazda çalıştırır, size bir \".onion\" adresi gönderir",
                "(İsteğe bağlı) vaka bilgilerini girin",
                "Host alanına aldığınız .onion adresini eksiksiz yazın (örn. abcxyz....onion)",
                "\"Bağlantı Yöntemi\"nde \"Tor (Acil Durum)\" zaten seçili gelir",
                "\"Bağlan ve Diskleri Listele\"ye basın -- bağlantı Tor ağı üzerinden, anahtarınızla "
                "doğrulanarak kurulur",
            ],
            "warning": (
                "Bağlantı, Tor ağındaki birden fazla farklı sunucu (röle) üzerinden dolaşarak "
                "gider -- doğrudan bağlantıya göre çok daha yüksek gecikme ve çok daha düşük hız "
                "beklenmelidir. Büyük bir disk imajı (onlarca/yüzlerce GB) saatlerce sürebilir. Bu "
                "yüzden gerçekten SON ÇARE: mümkünse önce Doğrudan/VPN'i deneyin."
            ),
        },
        "en": {
            "title": "Tor (Emergency) Acquisition",
            "icon": "shield-alert",
            "short": "Last resort when you have NO access to the target network -- slow",
            "what": (
                "The last-resort method used when you have NO access to the target network "
                "whatsoever (no direct, no VPN, no port forwarding). A USB \"portable kit\" "
                "taken on-site, once run on the target device, automatically opens an outbound "
                "address (.onion) over the Tor network -- with no router configuration and no "
                "port opened. Only YOU (the operator), holding your private key, can connect to "
                "this address; even if someone else obtains the address, it is useless to them."
            ),
            "when": [
                "You have no authority/access to the target company's network at all (can't get "
                "into the router, can't get help from IT, or there's no time)",
                "A VPN can't be set up either",
            ],
            "requires": [
                "You must have already generated an \"operator key\" -- it is auto-generated/shown "
                "on the screen that opens when you click \"Start\", done the first time",
                "You must have given this key to the person preparing/taking the portable kit "
                "BEFORE the site visit -- the kit must be prepared with this key in advance",
                "The person on-site must have run the portable kit on the target device (from USB)",
                "The \".onion\" address produced by the kit must have reached you -- the on-site "
                "person delivers it via THEIR OWN phone, the evidence device's network/apps are never used",
            ],
            "steps": [
                "From the \"My Operator Key\" box on the screen that opens when you click \"Start\", "
                "\"Copy\" your key and deliver it to the on-site person IN ADVANCE",
                "The on-site person runs the portable kit on the target device and sends you a \".onion\" address",
                "(Optional) enter the case information",
                "Enter the .onion address you received in full in the Host field (e.g. abcxyz....onion)",
                "\"Tor (Emergency)\" is already selected under \"Connection Method\"",
                "Click \"Connect and List Disks\" -- the connection is established over the Tor "
                "network, authenticated with your key",
            ],
            "warning": (
                "The connection travels through multiple different servers (relays) on the Tor "
                "network -- expect much higher latency and much lower speed than a direct "
                "connection. A large disk image (tens/hundreds of GB) can take hours. This is why "
                "it is truly a LAST RESORT: try Direct/VPN first if at all possible."
            ),
        },
    },
    "ram": {
        "tr": {
            "title": "RAM İmajı Al (Windows, yerel)",
            "icon": "cpu",
            "short": "Bu makinenin kendi belleğini alır -- uzak bağlantı gerekmez",
            "what": (
                "Bu bilgisayarın kendi belleğini (RAM) adli olarak imaj alır -- uzak "
                "bağlantı gerekmez, doğrudan bu makinede çalışır."
            ),
            "when": [
                "İncelediğiniz bilgisayar önünüzde ve o an açıksa, kapatmadan önce "
                "bellekteki veriyi kaybetmeden almak istiyorsanız",
            ],
            "requires": [
                "Windows işletim sistemi",
                "Full (tam bellek) modunda: Yönetici olarak çalıştırma + sürücünün "
                "test-signing ile yüklenmiş olması (Secure Boot ayarını etkiler, "
                "kendi makinenizde önceden hazırlanmalı)",
            ],
            "steps": [
                "\"Başlat\"a basıp (isteğe bağlı) vaka bilgilerini girin",
                "\"Process Dump\" (tek bir programın belleği, yönetici gerekmez, hızlı) ya da "
                "\"Full\" (tüm sistem belleği, yönetici + sürücü gerekir) modunu seçin",
                "Process Dump modunda listeden hedef process'i seçin",
                "\"Başlat\" ile imaj almayı başlatın",
                "İşlem bitince hash/boyut/süre bilgilerini içeren rapor otomatik oluşturulur",
            ],
            "warning": None,
        },
        "en": {
            "title": "RAM Acquisition (Windows, local)",
            "icon": "cpu",
            "short": "Acquires this machine's own memory -- no remote connection needed",
            "what": (
                "Forensically acquires this computer's own memory (RAM) -- no remote connection "
                "needed, runs directly on this machine."
            ),
            "when": [
                "The computer you're examining is in front of you and currently on, and you want "
                "to capture the data in memory before shutting it down without losing it",
            ],
            "requires": [
                "Windows operating system",
                "For Full (entire memory) mode: running as Administrator + the driver must be "
                "loaded with test-signing enabled (affects the Secure Boot setting, must be "
                "prepared in advance on your own machine)",
            ],
            "steps": [
                "Click \"Start\" and (optionally) enter the case information",
                "Choose \"Process Dump\" (a single program's memory, no admin needed, fast) or "
                "\"Full\" (entire system memory, needs admin + driver) mode",
                "In Process Dump mode, select the target process from the list",
                "Click \"Start\" to begin the acquisition",
                "Once finished, a report with hash/size/duration information is generated automatically",
            ],
            "warning": None,
        },
    },
}


class SidebarButton(QPushButton):
    """
    Sol menu ogesi: ikon + metin, secili/degil durumuna gore dolgu.
    Sadece launcher'a ozgu (tek kullanim yeri) -- bu yuzden shared/
    ui_kit'e degil, buraya konuldu.
    """

    def __init__(self, icon_name, text, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self.setText(f"  {text}")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._apply_style()
        self.toggled.connect(self._apply_style)

    def _apply_style(self, *_args):
        active = self.isChecked()
        self.setIcon(icons.icon(self._icon_name, color="white" if active else ui.TEXT_MAIN, size=17))
        self.setIconSize(self.iconSize().__class__(17, 17))
        self.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 8px 10px;
                border: none;
                border-radius: {ui.RADIUS}px;
                font-family: "{ui.FONT_UI}";
                font-size: {ui.SIZE_HELPER}px;
                background-color: {ui.ACCENT if active else "transparent"};
                color: {"white" if active else ui.TEXT_MAIN};
            }}
            QPushButton:hover {{
                background-color: {ui.ACCENT_HOVER if active else ui.BG_LAYER2};
            }}
        """)


class BodyText(QLabel):
    def __init__(self, text, secondary=True, parent=None):
        super().__init__(text, parent)
        color = ui.TEXT_SECONDARY if secondary else ui.TEXT_MAIN
        self.setStyleSheet(
            f"color: {color}; font-family: '{ui.FONT_UI}'; font-size: {ui.SIZE_HELPER}px; background: transparent;"
        )
        self.setWordWrap(True)


class ChameleonWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "tr"
        self.active_nav = "home"
        self._set_window_icon()
        self._build_shell()
        self._show_home()

    # -- Pencere ikonu ----------------------------------------------------
    def _set_window_icon(self):
        if os.path.exists(ICON_PNG):
            self.setWindowIcon(QIcon(ICON_PNG))

    # -- Kabuk: sidebar + icerik alani (tema/dil degisince YENIDEN kurulur) --
    def _build_shell(self):
        """
        Widget'lar renklerini KURULUM ANINDA QSS'e gomdugu icin (canli
        guncellenmiyor), tema ya da dil degisince tek care butun kabugu
        yikip yeniden kurmak -- eski Tk suruminun _toggle_theme() ->
        _build_shell() deseniyle ayni.
        """
        self.setWindowTitle(t("title", self.lang))

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        self.stack_container = QWidget()
        self.stack_layout = QVBoxLayout(self.stack_container)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.stack_container, stretch=1)

        self.setCentralWidget(central)

    def _apply_theme(self, mode):
        """QApplication'in genel QSS'ini yeniden uygular + kabugu (ve
        acik olan sayfayi) yeniden kurar -- bkz. _build_shell() aciklamasi."""
        ui.set_mode(mode)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(ui.base_stylesheet())
        self._build_shell()
        self._show_settings()

    def _apply_lang(self, lang):
        self.lang = lang
        self._build_shell()
        self._show_settings()

    # -- Sidebar ------------------------------------------------------------
    def _build_sidebar(self):
        panel = QFrame()
        panel.setFixedWidth(240)
        panel.setStyleSheet(f"background-color: {ui.BG_SURFACE}; border-right: 1px solid {ui.BORDER};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(2)

        header = QHBoxLayout()
        if os.path.exists(ICON_PNG):
            logo = QLabel()
            logo.setPixmap(QPixmap(ICON_PNG).scaledToHeight(28, Qt.TransformationMode.SmoothTransformation))
            header.addWidget(logo)
        name = QLabel(t("title", self.lang))
        name.setStyleSheet(f"font-family:'{ui.FONT_UI}'; font-size:16px; font-weight:600; color:{ui.TEXT_MAIN};")
        header.addWidget(name)
        header.addStretch()
        header_w = QWidget()
        header_w.setLayout(header)
        layout.addWidget(header_w)
        layout.addSpacing(14)

        self.nav_buttons = {}
        self.nav_group = QButtonGroup(panel)
        self.nav_group.setExclusive(True)
        lang = self.lang
        nav_items = [
            ("home", "home", "Ana Sayfa" if lang == "tr" else "Home", self._show_home),
            ("direct", "link", "Doğrudan / Port Yönlendirme" if lang == "tr" else "Direct / Port Forward", self._show_direct_detail),
            ("vpn", "shield", "VPN", self._show_vpn_detail),
            ("tor", "shield-alert", "Tor (Acil Durum)" if lang == "tr" else "Tor (Emergency)", self._show_tor_detail),
            ("ram", "cpu", "RAM İmajı Al" if lang == "tr" else "RAM Image", self._show_ram_detail),
            ("settings", "settings", "Ayarlar" if lang == "tr" else "Settings", self._show_settings),
        ]
        for key, icon_name, label, handler in nav_items:
            btn = SidebarButton(icon_name, label)
            btn.clicked.connect(handler)
            self.nav_group.addButton(btn)
            layout.addWidget(btn)
            self.nav_buttons[key] = btn
        self.nav_buttons["home"].setChecked(True)

        layout.addStretch()
        version_lbl = QLabel(f"v{version.VERSION}")
        version_lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:10px;")
        layout.addWidget(version_lbl)
        return panel

    def _set_active_nav(self, key):
        self.active_nav = key
        btn = self.nav_buttons.get(key)
        if btn:
            btn.setChecked(True)

    # -- Icerik alani ---------------------------------------------------
    def _clear_content(self):
        while self.stack_layout.count():
            item = self.stack_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        page = QWidget()
        self.stack_layout.addWidget(page)
        return page

    def _scrollable(self, page):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(32, 28, 32, 28)
        inner_layout.setSpacing(ui.CARD_GAP)
        scroll.setWidget(inner)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        return inner_layout

    # -- Ana Sayfa ------------------------------------------------------
    def _show_home(self):
        self._set_active_nav("home")
        page = self._clear_content()
        body = self._scrollable(page)

        lang = self.lang
        title = QLabel(t("subtitle", self.lang))
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:15px; font-weight:600;")
        body.addWidget(title)
        body.addWidget(BodyText(
            "Bir yöntem seçin -- her birinin ne yaptığını ve nasıl kullanılacağını açan sayfada görebilirsiniz."
            if lang == "tr" else
            "Choose a method -- the page for each explains what it does and how to use it."
        ))

        for key, handler in [
            ("direct", self._show_direct_detail), ("vpn", self._show_vpn_detail),
            ("tor", self._show_tor_detail), ("ram", self._show_ram_detail),
        ]:
            info = METHOD_INFO[key][self.lang]
            body.addWidget(self._home_card(info, handler))
        body.addStretch()

    def _home_card(self, info, handler):
        card = widgets.Card()
        row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(icons.icon(info["icon"], color=ui.ACCENT, size=22).pixmap(22, 22))
        icon_lbl.setFixedWidth(30)
        row.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        title_lbl = QLabel(info["title"])
        title_lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:14px; font-weight:600;")
        text_col.addWidget(title_lbl)
        text_col.addWidget(BodyText(info["short"]))
        row.addLayout(text_col, stretch=1)

        open_btn = widgets.SecondaryButton("Aç" if self.lang == "tr" else "Open")
        open_btn.clicked.connect(handler)
        row.addWidget(open_btn)
        card.body.addLayout(row)
        return card

    # -- Yontem tanitim sayfalari ----------------------------------------
    def _show_method_detail(self, nav_key, start_command):
        self._set_active_nav(nav_key)
        page = self._clear_content()
        body = self._scrollable(page)
        info = METHOD_INFO[nav_key][self.lang]
        lang = self.lang

        title = QLabel(info["title"])
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_TITLE}px; font-weight:600;")
        body.addWidget(title)
        body.addWidget(BodyText(info["what"]))

        body.addWidget(self._info_section("Ne zaman kullanılır?" if lang == "tr" else "When to use it?", info["when"]))
        body.addWidget(self._info_section("Gerekenler (sırasıyla)" if lang == "tr" else "Requirements (in order)", info["requires"], numbered=True))
        body.addWidget(self._info_section("Adım adım kullanım" if lang == "tr" else "Step by step", info["steps"], numbered=True))

        if info.get("warning"):
            warn_card = QFrame()
            warn_card.setStyleSheet(
                f"background-color: {ui.BG_SURFACE}; border: 1px solid {ui.WARNING}; border-radius: {ui.RADIUS}px;"
            )
            warn_layout = QHBoxLayout(warn_card)
            warn_icon = QLabel()
            warn_icon.setPixmap(icons.icon("alert-triangle", color=ui.WARNING, size=18).pixmap(18, 18))
            warn_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
            warn_layout.addWidget(warn_icon)
            warn_text = QLabel(info["warning"])
            warn_text.setWordWrap(True)
            warn_text.setStyleSheet(f"color:{ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
            warn_layout.addWidget(warn_text, stretch=1)
            body.addWidget(warn_card)

        start_btn = widgets.PrimaryButton("Başlat" if lang == "tr" else "Start")
        start_btn.clicked.connect(start_command)
        row = QHBoxLayout()
        row.addWidget(start_btn)
        row.addStretch()
        row_w = QWidget()
        row_w.setLayout(row)
        body.addWidget(row_w)
        body.addStretch()

    def _info_section(self, heading, items, numbered=False):
        card = widgets.Card(heading)
        for i, item in enumerate(items, start=1):
            if numbered:
                row = QHBoxLayout()
                row.setSpacing(10)
                row.addWidget(widgets.StepBadge(i), alignment=Qt.AlignmentFlag.AlignTop)
                row.addWidget(BodyText(item, secondary=False), stretch=1)
                card.body.addLayout(row)
            else:
                card.body.addWidget(BodyText(f"•  {item}", secondary=False))
        return card

    def _show_direct_detail(self):
        self._show_method_detail("direct", lambda: self._show_case_info(lambda case: self._open_ssh_engine("direct", case)))

    def _show_vpn_detail(self):
        self._show_method_detail("vpn", lambda: self._show_case_info(lambda case: self._open_ssh_engine("vpn", case)))

    def _show_tor_detail(self):
        self._show_method_detail("tor", lambda: self._show_case_info(lambda case: self._open_ssh_engine("tor", case)))

    def _show_ram_detail(self):
        self._show_method_detail("ram", lambda: self._show_case_info(lambda case: self._open_ram_engine(case)))

    # -- Vaka Bilgileri ----------------------------------------------------
    def _show_case_info(self, on_continue):
        page = self._clear_content()
        body = self._scrollable(page)
        lang = self.lang

        title = QLabel("Vaka Bilgileri" if lang == "tr" else "Case Information")
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_TITLE}px; font-weight:600;")
        body.addWidget(title)

        card = widgets.Card()
        card.setMaximumWidth(640)
        note = QLabel(
            "(İsteğe bağlı -- rapor üretmiyorsanız boş bırakabilirsiniz)"
            if lang == "tr" else
            "(Optional -- leave blank if you're not producing a report)"
        )
        note.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style:italic;")
        card.body.addWidget(note)

        entries = {}
        for key, label in [
            ("case_id", "Vaka No" if lang == "tr" else "Case No"),
            ("examiner", "İnceleyen" if lang == "tr" else "Examiner"),
            ("custodian", "Cihaz Sahibi / Yetkili Kişi" if lang == "tr" else "Device Owner / Custodian"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(190)
            row.addWidget(lbl)
            entry = widgets.Input()
            row.addWidget(entry)
            card.body.addLayout(row)
            entries[key] = entry

        def _continue():
            on_continue({k: e.text().strip() for k, e in entries.items()})

        cont_btn = widgets.PrimaryButton("Devam Et" if lang == "tr" else "Continue")
        cont_btn.clicked.connect(_continue)
        cont_row = QHBoxLayout()
        cont_row.addWidget(cont_btn)
        cont_row.addStretch()
        card.body.addLayout(cont_row)

        card_row = QHBoxLayout()
        card_row.addWidget(card)
        card_row.addStretch()
        card_row_w = QWidget()
        card_row_w.setLayout(card_row)
        body.addWidget(card_row_w)
        body.addStretch()

    # -- Ayarlar ----------------------------------------------------------
    def _show_settings(self):
        self._set_active_nav("settings")
        page = self._clear_content()
        body = self._scrollable(page)
        lang = self.lang

        title = QLabel("Ayarlar" if lang == "tr" else "Settings")
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:18px; font-weight:600;")
        body.addWidget(title)

        lang_card = widgets.Card("Dil" if lang == "tr" else "Language")
        lang_row = QHBoxLayout()
        lang_group = QButtonGroup(lang_card)
        radio_tr = widgets.RadioButton("Türkçe")
        radio_en = widgets.RadioButton("English")
        radio_tr.setChecked(lang == "tr")
        radio_en.setChecked(lang == "en")
        for r, code in [(radio_tr, "tr"), (radio_en, "en")]:
            lang_group.addButton(r)
            lang_row.addWidget(r)
            r.toggled.connect(lambda checked, c=code: checked and self._apply_lang(c))
        lang_row.addStretch()
        lang_card.body.addLayout(lang_row)
        body.addWidget(lang_card)

        theme_card = widgets.Card("Tema" if lang == "tr" else "Theme")
        theme_row = QHBoxLayout()
        theme_group = QButtonGroup(theme_card)
        current_mode = ui.get_mode()
        radio_dark = widgets.RadioButton("Koyu" if lang == "tr" else "Dark")
        radio_light = widgets.RadioButton("Açık" if lang == "tr" else "Light")
        radio_dark.setChecked(current_mode == "dark")
        radio_light.setChecked(current_mode == "light")
        for r, mode in [(radio_dark, "dark"), (radio_light, "light")]:
            theme_group.addButton(r)
            theme_row.addWidget(r)
            r.toggled.connect(lambda checked, m=mode: checked and self._apply_theme(m))
        theme_row.addStretch()
        theme_card.body.addLayout(theme_row)
        body.addWidget(theme_card)

        body.addWidget(BodyText(f"Chameleon v{version.VERSION}"))
        body.addStretch()

    # -- SSH / RAM motoruna gecis (henuz Qt'ye tasinmadi) ------------------
    def _open_ssh_engine(self, connection_method, case):
        """SSH motoru Qt'ye tasindi (plan adim 4) -- gercek ekran gomuluyor."""
        if SSH_ENGINE_DIR not in sys.path:
            sys.path.insert(0, SSH_ENGINE_DIR)
        try:
            from gui_v2 import ForensicWidget
        except ImportError as exc:
            self._show_pending_migration_notice(f"SSH ile Uzak İmaj Al (yüklenemedi: {exc})")
            return

        page = self._clear_content()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        ssh_widget = ForensicWidget(
            on_back=self._show_home,
            initial_case_id=case.get("case_id", ""), initial_examiner=case.get("examiner", ""),
            initial_custodian=case.get("custodian", ""), initial_connection_method=connection_method,
        )
        page_layout.addWidget(ssh_widget)

    def _open_ram_engine(self, case):
        """RAM motoru Qt'ye tasindi (plan adim 3) -- gercek ekran gomuluyor."""
        if RAM_ENGINE_DIR not in sys.path:
            sys.path.insert(0, RAM_ENGINE_DIR)
        try:
            from ram_gui import RamEngineWidget
        except ImportError as exc:
            self._show_pending_migration_notice(f"RAM İmajı Al (yüklenemedi: {exc})")
            return

        page = self._clear_content()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        ram_widget = RamEngineWidget(
            on_back=self._show_home,
            initial_case_id=case.get("case_id", ""), initial_examiner=case.get("examiner", ""),
            initial_custodian=case.get("custodian", ""),
        )
        page_layout.addWidget(ram_widget)

    def _show_pending_migration_notice(self, method_name):
        page = self._clear_content()
        body = self._scrollable(page)
        card = widgets.Card("Henüz Taşınmadı")
        lbl = BodyText(
            f"\"{method_name}\" ekranı PySide6'ya taşınma sırasını bekliyor "
            f"(plan adım 3/4). Şimdilik bu sayfa sadece launcher'ın (adım 2) "
            f"kendi başına doğru çalıştığını göstermek için var.",
            secondary=False,
        )
        card.body.addWidget(lbl)
        body.addWidget(card)
        body.addStretch()


def show_splash(on_done):
    """
    Bukalemun ikonu + isim + surum + telif, 1.8sn gosterilip kapanir.
    QSplashScreen'in kendi pixmap'i sadece arka plan; asil icerik
    (ikon/metin), splash'in USTUNE bindirilmis kucuk bir QWidget'la
    ciziliyor (Tk surumundeki 'body' Frame'iyle ayni fikir).
    """
    splash_pix = QPixmap(520, 320)
    splash_pix.fill(QColor(ui.BG_DARKEST))
    splash = QSplashScreen(splash_pix)
    splash.show()

    layout_widget = QWidget(splash)
    layout_widget.setGeometry(0, 0, 520, 320)
    layout = QVBoxLayout(layout_widget)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    if os.path.exists(ICON_PNG):
        icon_lbl = QLabel()
        icon_lbl.setPixmap(QPixmap(ICON_PNG).scaledToHeight(120, Qt.TransformationMode.SmoothTransformation))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(icon_lbl)

    name_lbl = QLabel(t("title", "tr").upper())
    name_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    name_lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:24px; font-weight:600;")
    layout.addWidget(name_lbl)

    sub_lbl = QLabel(t("subtitle", "tr"))
    sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    sub_lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:11px;")
    layout.addWidget(sub_lbl)

    ver_lbl = QLabel(f"v{version.VERSION}")
    ver_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    ver_lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:9px;")
    layout.addWidget(ver_lbl)

    layout_widget.show()
    QTimer.singleShot(1800, lambda: (splash.close(), on_done()))
    return splash, layout_widget


if __name__ == "__main__":
    app = QApplication([])
    fonts.register_fonts()
    app.setStyleSheet(ui.base_stylesheet())

    window = ChameleonWindow()

    def _start_main():
        window.resize(1100, 720)
        window.show()

    splash, _kept_alive = show_splash(_start_main)
    sys.exit(app.exec())
