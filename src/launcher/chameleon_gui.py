"""
chameleon_gui.py
Chameleon ana ekrani (PySide6). Tek giris noktasi: sol sidebar navigasyon
+ tanitim sayfalari + Vaka Bilgileri on-ekrani + gercek SSH (gui_v2.py) ve
RAM (ram_gui.py) ekranlarina gecis. Bu dosyanin kendisi SAF UI'dir --
hicbir SSH/Tor/disk/RAM mantigina dogrudan dokunmuyor.

customtkinter surumunden PySide6'ya tam gecis tamamlandi (bkz.
docs/roadmap.md, docs/oturum_ozeti.md) -- eski dosyalar kaldirildi.
"""

import csv
import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplashScreen,
    QStackedWidget, QVBoxLayout, QWidget,
)

if getattr(sys, "frozen", False):
    PROJECT_ROOT = sys._MEIPASS
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHARED_DIR = os.path.join(PROJECT_ROOT, "shared")
sys.path.insert(0, SHARED_DIR)
sys.path.insert(0, os.path.join(SHARED_DIR, "i18n"))
from strings import t, LANGUAGES  # noqa: E402
import version  # noqa: E402
from ui_kit import theme_qt as ui, fonts, icons, widgets  # noqa: E402
from help_content import HELP_TOPICS, get_topic  # noqa: E402
from onion_auth import key_fingerprint  # noqa: E402
import tz_display  # noqa: E402

SSH_ENGINE_DIR = os.path.join(PROJECT_ROOT, "engines", "ssh_engine", "local_collector")
RAM_ENGINE_DIR = os.path.join(PROJECT_ROOT, "engines", "ram_engine")
PORTABLE_KIT_DIR = os.path.join(PROJECT_ROOT, "engines", "portable_kit")
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
        "es": {
            "title": "Adquisición Directa / Redirección de Puerto",
            "icon": "link",
            "short": "Úselo cuando pueda alcanzar el destino directamente por la red -- el método más simple y rápido",
            "what": (
                "El método más simple y rápido, usado cuando puede alcanzar el equipo destino "
                "directamente por la red (misma red, o una regla de redirección de puerto "
                "configurada en el router). Se conecta por SSH y adquiere una imagen de disco o "
                "un solo archivo/carpeta."
            ),
            "when": [
                "El equipo destino está en la misma red que usted (p. ej. la misma red de oficina/laboratorio)",
                "El destino está detrás de un router con acceso a internet Y puede añadir una "
                "regla de redirección de puerto en ese router (p. ej. puerto externo 5632 → puerto 22 del destino)",
            ],
            "requires": [
                "Un servidor SSH en ejecución en el destino (Linux: sshd, Windows: OpenSSH Server)",
                "La dirección IP y el puerto SSH del destino (si hay redirección de puerto, la IP externa del router + el puerto redirigido)",
                "Un nombre de usuario + contraseña O una clave privada SSH",
                "En modo disco completo: privilegios de sudo/administrador en el destino",
            ],
            "steps": [
                "Haga clic en \"Iniciar\" e (opcionalmente) introduzca la información del caso",
                "Introduzca la IP del destino en el campo Host (o la IP externa del router si "
                "hay redirección de puerto), y el puerto SSH en el campo Puerto",
                "Introduzca el nombre de usuario y la contraseña/clave",
                "Compruebe que \"Directo / Redirección de Puerto\" esté seleccionado en \"Método de Conexión\"",
                "Haga clic en \"Conectar y Listar Discos\"",
                "Seleccione el sistema operativo destino y qué adquirir, luego haga clic en \"Iniciar Adquisición\"",
            ],
            "warning": None,
        },
        "de": {
            "title": "Direkte Erfassung / Portweiterleitung",
            "icon": "link",
            "short": "Verwenden Sie dies, wenn Sie das Ziel direkt über das Netzwerk erreichen können -- einfachste, schnellste Methode",
            "what": (
                "Die einfachste und schnellste Methode, verwendet wenn Sie den Zielcomputer "
                "direkt über das Netzwerk erreichen können (gleiches Netzwerk, oder eine auf dem "
                "Router eingerichtete Portweiterleitungsregel). Verbindet sich per SSH und "
                "erfasst ein Disk-Image oder eine einzelne Datei/einen Ordner."
            ),
            "when": [
                "Der Zielcomputer befindet sich im selben Netzwerk wie Sie (z. B. dasselbe Büro-/Labornetzwerk)",
                "Das Ziel befindet sich hinter einem Router mit Internetzugang UND Sie können auf "
                "diesem Router eine Portweiterleitungsregel hinzufügen (z. B. externer Port 5632 → Port 22 des Ziels)",
            ],
            "requires": [
                "Ein auf dem Ziel laufender SSH-Server (Linux: sshd, Windows: OpenSSH Server)",
                "Die IP-Adresse und der SSH-Port des Ziels (bei Portweiterleitung die externe IP des Routers + der weitergeleitete Port)",
                "Ein Benutzername + Passwort ODER ein privater SSH-Schlüssel",
                "Im Vollständige-Festplatte-Modus: sudo-/Administratorrechte auf dem Ziel",
            ],
            "steps": [
                "Klicken Sie auf \"Starten\" und geben Sie (optional) die Fallinformationen ein",
                "Geben Sie die IP des Ziels in das Feld Host ein (oder die externe IP des Routers "
                "bei Portweiterleitung) und den SSH-Port in das Feld Port",
                "Geben Sie Benutzername und Passwort/Schlüssel ein",
                "Prüfen Sie, dass unter \"Verbindungsmethode\" \"Direkt / Portweiterleitung\" ausgewählt ist",
                "Klicken Sie auf \"Verbinden und Festplatten auflisten\"",
                "Wählen Sie das Zielbetriebssystem und was erfasst werden soll, klicken Sie dann auf \"Erfassung starten\"",
            ],
            "warning": None,
        },
        "pt": {
            "title": "Aquisição Direta / Encaminhamento de Porta",
            "icon": "link",
            "short": "Use isto quando conseguir alcançar o alvo diretamente pela rede -- método mais simples e rápido",
            "what": (
                "O método mais simples e rápido, usado quando você consegue alcançar o "
                "computador alvo diretamente pela rede (mesma rede, ou uma regra de "
                "encaminhamento de porta configurada no roteador). Conecta-se via SSH e adquire "
                "uma imagem de disco ou um único arquivo/pasta."
            ),
            "when": [
                "O computador alvo está na mesma rede que você (ex.: mesma rede de escritório/laboratório)",
                "O alvo está atrás de um roteador com acesso à internet E você pode adicionar uma "
                "regra de encaminhamento de porta nesse roteador (ex.: porta externa 5632 → porta 22 do alvo)",
            ],
            "requires": [
                "Um servidor SSH em execução no alvo (Linux: sshd, Windows: OpenSSH Server)",
                "O endereço IP e a porta SSH do alvo (se houver encaminhamento de porta, o IP externo do roteador + a porta encaminhada)",
                "Um nome de usuário + senha OU uma chave privada SSH",
                "No modo disco completo: privilégios de sudo/administrador no alvo",
            ],
            "steps": [
                "Clique em \"Iniciar\" e (opcionalmente) insira as informações do caso",
                "Insira o IP do alvo no campo Host (ou o IP externo do roteador se houver "
                "encaminhamento de porta), e a porta SSH no campo Porta",
                "Insira o nome de usuário e a senha/chave",
                "Verifique se \"Direto / Encaminhamento de Porta\" está selecionado em \"Método de Conexão\"",
                "Clique em \"Conectar e Listar Discos\"",
                "Selecione o sistema operacional alvo e o que adquirir, depois clique em \"Iniciar Aquisição\"",
            ],
            "warning": None,
        },
        "fr": {
            "title": "Acquisition Directe / Redirection de Port",
            "icon": "link",
            "short": "À utiliser lorsque vous pouvez atteindre la cible directement via le réseau -- méthode la plus simple et la plus rapide",
            "what": (
                "La méthode la plus simple et la plus rapide, utilisée lorsque vous pouvez "
                "atteindre l'ordinateur cible directement via le réseau (même réseau, ou une "
                "règle de redirection de port configurée sur le routeur). Se connecte via SSH et "
                "acquiert une image disque ou un seul fichier/dossier."
            ),
            "when": [
                "L'ordinateur cible est sur le même réseau que vous (p. ex. même réseau de bureau/labo)",
                "La cible est derrière un routeur avec accès internet ET vous pouvez ajouter une "
                "règle de redirection de port sur ce routeur (p. ex. port externe 5632 → port 22 de la cible)",
            ],
            "requires": [
                "Un serveur SSH en cours d'exécution sur la cible (Linux : sshd, Windows : OpenSSH Server)",
                "L'adresse IP et le port SSH de la cible (en cas de redirection de port, l'IP externe du routeur + le port redirigé)",
                "Un nom d'utilisateur + mot de passe OU une clé privée SSH",
                "En mode disque complet : privilèges sudo/administrateur sur la cible",
            ],
            "steps": [
                "Cliquez sur \"Démarrer\" et (facultatif) saisissez les informations du dossier",
                "Saisissez l'IP de la cible dans le champ Hôte (ou l'IP externe du routeur en cas "
                "de redirection de port), et le port SSH dans le champ Port",
                "Saisissez le nom d'utilisateur et le mot de passe/la clé",
                "Vérifiez que \"Direct / Redirection de Port\" est bien sélectionné sous \"Méthode de Connexion\"",
                "Cliquez sur \"Connecter et Lister les Disques\"",
                "Sélectionnez le système d'exploitation cible et ce qu'il faut acquérir, puis cliquez sur \"Démarrer l'Acquisition\"",
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
        "es": {
            "title": "Adquisición por VPN",
            "icon": "shield",
            "short": "Úselo cuando su equipo esté conectado a la red del destino mediante VPN",
            "what": (
                "Se usa cuando su equipo ya está conectado a la red donde se encuentra el "
                "destino mediante un túnel VPN. Técnicamente IDÉNTICO a la conexión Directa -- "
                "SSH se establece directamente, no hay una capa adicional como Tor. La única "
                "diferencia: usa una IP accesible a través de la VPN, y esto queda registrado "
                "por separado en la cadena de custodia."
            ),
            "when": [
                "No tiene acceso directo a la red destino pero puede conectarse a una VPN "
                "corporativa/remota (p. ej. la VPN propia de la empresa, acceso VPN proporcionado por un cliente)",
            ],
            "requires": [
                "Un cliente VPN ya INSTALADO y CONECTADO -- Chameleon NO establece la conexión "
                "VPN por sí mismo, este paso lo realiza usted de antemano con su propio software VPN",
                "Acceso a la dirección IP del destino a través de la VPN",
                "Un servidor SSH en ejecución en el destino + nombre de usuario/contraseña o clave",
            ],
            "steps": [
                "Primero conéctese a la red destino con su propio cliente VPN (este paso ocurre FUERA de Chameleon)",
                "Haga clic en \"Iniciar\" e (opcionalmente) introduzca la información del caso",
                "Introduzca la IP del destino accesible por VPN en el campo Host",
                "Compruebe que \"VPN\" esté seleccionado en \"Método de Conexión\"",
                "Haga clic en \"Conectar y Listar Discos\" y continúe con normalidad",
            ],
            "warning": None,
        },
        "de": {
            "title": "VPN-Erfassung",
            "icon": "shield",
            "short": "Verwenden Sie dies, wenn Ihr Computer per VPN mit dem Netzwerk des Ziels verbunden ist",
            "what": (
                "Wird verwendet, wenn Ihr Computer bereits über einen VPN-Tunnel mit dem "
                "Netzwerk verbunden ist, in dem sich das Ziel befindet. Technisch IDENTISCH mit "
                "der Direktverbindung -- SSH wird direkt aufgebaut, es gibt keine zusätzliche "
                "Schicht wie bei Tor. Der einzige Unterschied: Sie verwenden eine über das VPN "
                "erreichbare IP, was zusätzlich in der Beweismittelkette vermerkt wird."
            ),
            "when": [
                "Sie haben keinen direkten Zugriff auf das Zielnetzwerk, können sich aber mit "
                "einem Unternehmens-/Remote-VPN verbinden (z. B. dem eigenen VPN der Firma, von einem Kunden bereitgestelltem VPN-Zugang)",
            ],
            "requires": [
                "Ein bereits INSTALLIERTER und VERBUNDENER VPN-Client -- Chameleon baut die "
                "VPN-Verbindung NICHT selbst auf, dies erledigen Sie vorher mit Ihrer eigenen VPN-Software",
                "Zugriff auf die IP-Adresse des Ziels über das VPN",
                "Ein auf dem Ziel laufender SSH-Server + Benutzername/Passwort oder Schlüssel",
            ],
            "steps": [
                "Verbinden Sie sich zuerst mit Ihrem eigenen VPN-Client mit dem Zielnetzwerk (dieser Schritt erfolgt AUSSERHALB von Chameleon)",
                "Klicken Sie auf \"Starten\" und geben Sie (optional) die Fallinformationen ein",
                "Geben Sie die über das VPN erreichbare IP des Ziels in das Feld Host ein",
                "Prüfen Sie, dass unter \"Verbindungsmethode\" \"VPN\" ausgewählt ist",
                "Klicken Sie auf \"Verbinden und Festplatten auflisten\" und fahren Sie normal fort",
            ],
            "warning": None,
        },
        "pt": {
            "title": "Aquisição via VPN",
            "icon": "shield",
            "short": "Use isto quando seu computador estiver conectado à rede do alvo via VPN",
            "what": (
                "Usado quando seu computador já está conectado à rede onde o alvo está "
                "localizado por meio de um túnel VPN. Tecnicamente IDÊNTICO à conexão Direta -- "
                "o SSH é estabelecido diretamente, não há uma camada extra como o Tor. A única "
                "diferença: você usa um IP acessível pela VPN, e isso é registrado separadamente "
                "na cadeia de custódia."
            ),
            "when": [
                "Você não tem acesso direto à rede alvo, mas pode se conectar a uma VPN "
                "corporativa/remota (ex.: a VPN da própria empresa, acesso VPN fornecido por um cliente)",
            ],
            "requires": [
                "Um cliente VPN já INSTALADO e CONECTADO -- o Chameleon NÃO estabelece a conexão "
                "VPN por conta própria, essa etapa é feita por você previamente com seu próprio software VPN",
                "Acesso ao endereço IP do alvo pela VPN",
                "Um servidor SSH em execução no alvo + nome de usuário/senha ou chave",
            ],
            "steps": [
                "Primeiro conecte-se à rede alvo com seu próprio cliente VPN (essa etapa acontece FORA do Chameleon)",
                "Clique em \"Iniciar\" e (opcionalmente) insira as informações do caso",
                "Insira o IP do alvo acessível pela VPN no campo Host",
                "Verifique se \"VPN\" está selecionado em \"Método de Conexão\"",
                "Clique em \"Conectar e Listar Discos\" e continue normalmente",
            ],
            "warning": None,
        },
        "fr": {
            "title": "Acquisition par VPN",
            "icon": "shield",
            "short": "À utiliser lorsque votre ordinateur est connecté au réseau de la cible via VPN",
            "what": (
                "Utilisé lorsque votre ordinateur est déjà connecté au réseau où se trouve la "
                "cible via un tunnel VPN. Techniquement IDENTIQUE à la connexion Directe -- le "
                "SSH est établi directement, il n'y a pas de couche supplémentaire comme Tor. La "
                "seule différence : vous utilisez une IP accessible via le VPN, ce qui est "
                "enregistré séparément dans la chaîne de possession."
            ),
            "when": [
                "Vous n'avez pas d'accès direct au réseau cible mais pouvez vous connecter à un "
                "VPN d'entreprise/distant (p. ex. le VPN propre de l'entreprise, un accès VPN fourni par un client)",
            ],
            "requires": [
                "Un client VPN déjà INSTALLÉ et CONNECTÉ -- Chameleon n'établit PAS lui-même la "
                "connexion VPN, cette étape est effectuée au préalable par vous avec votre propre logiciel VPN",
                "Accès à l'adresse IP de la cible via le VPN",
                "Un serveur SSH en cours d'exécution sur la cible + nom d'utilisateur/mot de passe ou clé",
            ],
            "steps": [
                "Connectez-vous d'abord au réseau cible avec votre propre client VPN (cette étape se déroule EN DEHORS de Chameleon)",
                "Cliquez sur \"Démarrer\" et (facultatif) saisissez les informations du dossier",
                "Saisissez l'IP de la cible accessible via le VPN dans le champ Hôte",
                "Vérifiez que \"VPN\" est bien sélectionné sous \"Méthode de Connexion\"",
                "Cliquez sur \"Connecter et Lister les Disques\" et continuez normalement",
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
        "es": {
            "title": "Adquisición por Tor (Emergencia)",
            "icon": "shield-alert",
            "short": "Último recurso cuando NO tiene acceso a la red destino -- lento",
            "what": (
                "El método de último recurso usado cuando NO tiene ningún acceso a la red "
                "destino (ni directo, ni VPN, ni redirección de puerto). Un \"kit portátil\" USB "
                "llevado al sitio, una vez ejecutado en el dispositivo destino, abre "
                "automáticamente una dirección saliente (.onion) sobre la red Tor -- sin "
                "configurar el router y sin abrir ningún puerto. Solo USTED (el operador), en "
                "posesión de su clave privada, puede conectarse a esta dirección; incluso si "
                "alguien más la obtiene, le resulta inútil."
            ),
            "when": [
                "No tiene ninguna autoridad/acceso a la red de la empresa destino (no puede "
                "entrar al router, no puede obtener ayuda de TI, o no hay tiempo)",
                "Tampoco se puede configurar una VPN",
            ],
            "requires": [
                "Debe haber generado ya una \"clave de operador\" -- se genera/muestra "
                "automáticamente en la pantalla que se abre al hacer clic en \"Iniciar\", se hace la primera vez",
                "Debe haber entregado esta clave a la persona que preparará/llevará el kit "
                "portátil ANTES de la visita al sitio -- el kit debe prepararse con esta clave de antemano",
                "La persona en el sitio debe haber ejecutado el kit portátil en el dispositivo destino (desde USB)",
                "La dirección \".onion\" generada por el kit debe habérsele hecho llegar -- la "
                "persona en el sitio la entrega por SU PROPIO teléfono, la red/aplicaciones del "
                "dispositivo de evidencia nunca se usan",
            ],
            "steps": [
                "Desde el cuadro \"Mi Clave de Operador\" en la pantalla que se abre al hacer "
                "clic en \"Iniciar\", \"Copie\" su clave y entréguesela a la persona en el sitio POR ADELANTADO",
                "La persona en el sitio ejecuta el kit portátil en el dispositivo destino y le envía una dirección \".onion\"",
                "(Opcional) introduzca la información del caso",
                "Introduzca la dirección .onion recibida completa en el campo Host (p. ej. abcxyz....onion)",
                "\"Tor (Emergencia)\" ya viene seleccionado en \"Método de Conexión\"",
                "Haga clic en \"Conectar y Listar Discos\" -- la conexión se establece sobre la "
                "red Tor, autenticada con su clave",
            ],
            "warning": (
                "La conexión viaja a través de varios servidores diferentes (repetidores) en la "
                "red Tor -- espere una latencia mucho mayor y una velocidad mucho menor que una "
                "conexión directa. Una imagen de disco grande (decenas/cientos de GB) puede "
                "tardar horas. Por eso es realmente un ÚLTIMO RECURSO: intente Directo/VPN "
                "primero si es posible."
            ),
        },
        "de": {
            "title": "Tor-Erfassung (Notfall)",
            "icon": "shield-alert",
            "short": "Letzter Ausweg, wenn Sie KEINEN Zugriff auf das Zielnetzwerk haben -- langsam",
            "what": (
                "Die Methode als letzter Ausweg, verwendet wenn Sie ÜBERHAUPT KEINEN Zugriff auf "
                "das Zielnetzwerk haben (weder direkt, noch VPN, noch Portweiterleitung). Ein vor "
                "Ort mitgebrachtes USB-\"tragbares Kit\" öffnet, sobald es auf dem Zielgerät "
                "ausgeführt wird, automatisch eine ausgehende Adresse (.onion) über das "
                "Tor-Netzwerk -- ohne Router-Konfiguration und ohne geöffneten Port. Nur SIE (der "
                "Operator) können sich mit Ihrem privaten Schlüssel mit dieser Adresse verbinden; "
                "selbst wenn jemand anderes die Adresse erhält, ist sie für ihn nutzlos."
            ),
            "when": [
                "Sie haben überhaupt keine Berechtigung/keinen Zugriff auf das Netzwerk des "
                "Zielunternehmens (kommen nicht in den Router, bekommen keine Hilfe von der IT, oder es fehlt die Zeit)",
                "Auch ein VPN kann nicht eingerichtet werden",
            ],
            "requires": [
                "Sie müssen bereits einen \"Operator-Schlüssel\" erzeugt haben -- er wird auf dem "
                "Bildschirm, der sich beim Klicken auf \"Starten\" öffnet, automatisch "
                "erzeugt/angezeigt, dies geschieht beim ersten Mal",
                "Sie müssen diesen Schlüssel der Person, die das tragbare Kit vorbereitet/"
                "mitnimmt, VOR dem Vor-Ort-Besuch gegeben haben -- das Kit muss vorab mit diesem "
                "Schlüssel vorbereitet werden",
                "Die Person vor Ort muss das tragbare Kit auf dem Zielgerät (von USB) ausgeführt haben",
                "Die vom Kit erzeugte \".onion\"-Adresse muss Sie erreicht haben -- die Person vor "
                "Ort übermittelt sie über IHR EIGENES Telefon, das Netzwerk/die Apps des "
                "Beweismittelgeräts werden nie verwendet",
            ],
            "steps": [
                "Kopieren Sie Ihren Schlüssel aus dem Feld \"Mein Operator-Schlüssel\" auf dem "
                "Bildschirm, der sich beim Klicken auf \"Starten\" öffnet, mit \"Kopieren\" und "
                "übermitteln Sie ihn der Person vor Ort IM VORAUS",
                "Die Person vor Ort führt das tragbare Kit auf dem Zielgerät aus und sendet Ihnen eine \".onion\"-Adresse",
                "(Optional) geben Sie die Fallinformationen ein",
                "Geben Sie die erhaltene .onion-Adresse vollständig in das Feld Host ein (z. B. abcxyz....onion)",
                "Unter \"Verbindungsmethode\" ist \"Tor (Notfall)\" bereits ausgewählt",
                "Klicken Sie auf \"Verbinden und Festplatten auflisten\" -- die Verbindung wird "
                "über das Tor-Netzwerk aufgebaut und mit Ihrem Schlüssel authentifiziert",
            ],
            "warning": (
                "Die Verbindung läuft über mehrere verschiedene Server (Relays) im Tor-Netzwerk "
                "-- erwarten Sie eine deutlich höhere Latenz und eine deutlich geringere "
                "Geschwindigkeit als bei einer Direktverbindung. Ein großes Disk-Image "
                "(Dutzende/Hunderte GB) kann Stunden dauern. Deshalb ist dies wirklich der "
                "LETZTE AUSWEG: Versuchen Sie nach Möglichkeit zuerst Direkt/VPN."
            ),
        },
        "pt": {
            "title": "Aquisição via Tor (Emergência)",
            "icon": "shield-alert",
            "short": "Último recurso quando você NÃO tem acesso à rede alvo -- lento",
            "what": (
                "O método de último recurso, usado quando você NÃO tem nenhum acesso à rede "
                "alvo (nem direto, nem VPN, nem encaminhamento de porta). Um \"kit portátil\" "
                "USB levado ao local, ao ser executado no dispositivo alvo, abre automaticamente "
                "um endereço de saída (.onion) pela rede Tor -- sem configuração de roteador e "
                "sem abrir nenhuma porta. Somente VOCÊ (o operador), de posse da sua chave "
                "privada, pode se conectar a esse endereço; mesmo que outra pessoa obtenha o "
                "endereço, ele é inútil para ela."
            ),
            "when": [
                "Você não tem nenhuma autoridade/acesso à rede da empresa alvo (não consegue "
                "entrar no roteador, não consegue ajuda do TI, ou não há tempo)",
                "Uma VPN também não pode ser configurada",
            ],
            "requires": [
                "Você já deve ter gerado uma \"chave de operador\" -- ela é gerada/exibida "
                "automaticamente na tela que se abre ao clicar em \"Iniciar\", feito na primeira vez",
                "Você deve ter entregado essa chave à pessoa que vai preparar/levar o kit "
                "portátil ANTES da visita ao local -- o kit deve ser preparado com essa chave com antecedência",
                "A pessoa no local deve ter executado o kit portátil no dispositivo alvo (a partir de USB)",
                "O endereço \".onion\" gerado pelo kit deve ter chegado até você -- a pessoa no "
                "local o entrega pelo PRÓPRIO telefone dela, a rede/aplicativos do dispositivo de "
                "evidência nunca são usados",
            ],
            "steps": [
                "Na caixa \"Minha Chave de Operador\" na tela que se abre ao clicar em "
                "\"Iniciar\", clique em \"Copiar\" para obter sua chave e entregue-a à pessoa no "
                "local COM ANTECEDÊNCIA",
                "A pessoa no local executa o kit portátil no dispositivo alvo e envia a você um endereço \".onion\"",
                "(Opcional) insira as informações do caso",
                "Insira o endereço .onion recebido por completo no campo Host (ex.: abcxyz....onion)",
                "\"Tor (Emergência)\" já vem selecionado em \"Método de Conexão\"",
                "Clique em \"Conectar e Listar Discos\" -- a conexão é estabelecida pela rede "
                "Tor, autenticada com sua chave",
            ],
            "warning": (
                "A conexão passa por vários servidores diferentes (retransmissores) na rede Tor "
                "-- espere latência muito maior e velocidade muito menor do que uma conexão "
                "direta. Uma imagem de disco grande (dezenas/centenas de GB) pode levar horas. "
                "Por isso é verdadeiramente um ÚLTIMO RECURSO: tente Direto/VPN primeiro, se possível."
            ),
        },
        "fr": {
            "title": "Acquisition par Tor (Urgence)",
            "icon": "shield-alert",
            "short": "Dernier recours lorsque vous n'avez AUCUN accès au réseau cible -- lent",
            "what": (
                "La méthode de dernier recours, utilisée lorsque vous n'avez AUCUN accès au "
                "réseau cible (ni direct, ni VPN, ni redirection de port). Un \"kit portable\" "
                "USB apporté sur place, une fois exécuté sur l'appareil cible, ouvre "
                "automatiquement une adresse sortante (.onion) sur le réseau Tor -- sans "
                "configuration du routeur et sans ouvrir de port. Seul VOUS (l'opérateur), en "
                "possession de votre clé privée, pouvez vous connecter à cette adresse ; même si "
                "quelqu'un d'autre obtient l'adresse, elle lui est inutile."
            ),
            "when": [
                "Vous n'avez aucune autorité/accès au réseau de l'entreprise cible (impossible "
                "d'accéder au routeur, pas d'aide du service informatique, ou pas le temps)",
                "Un VPN ne peut pas non plus être configuré",
            ],
            "requires": [
                "Vous devez déjà avoir généré une \"clé d'opérateur\" -- elle est "
                "générée/affichée automatiquement sur l'écran qui s'ouvre en cliquant sur "
                "\"Démarrer\", fait la première fois",
                "Vous devez avoir remis cette clé à la personne qui préparera/emportera le kit "
                "portable AVANT la visite sur site -- le kit doit être préparé avec cette clé à l'avance",
                "La personne sur place doit avoir exécuté le kit portable sur l'appareil cible (depuis une clé USB)",
                "L'adresse \".onion\" générée par le kit doit vous être parvenue -- la personne "
                "sur place la transmet via SON PROPRE téléphone, le réseau/les applications de "
                "l'appareil de preuve ne sont jamais utilisés",
            ],
            "steps": [
                "Depuis la case \"Ma Clé d'Opérateur\" sur l'écran qui s'ouvre en cliquant sur "
                "\"Démarrer\", cliquez sur \"Copier\" pour récupérer votre clé et transmettez-la "
                "à la personne sur place À L'AVANCE",
                "La personne sur place exécute le kit portable sur l'appareil cible et vous envoie une adresse \".onion\"",
                "(Facultatif) saisissez les informations du dossier",
                "Saisissez l'adresse .onion reçue en entier dans le champ Hôte (p. ex. abcxyz....onion)",
                "\"Tor (Urgence)\" est déjà sélectionné sous \"Méthode de Connexion\"",
                "Cliquez sur \"Connecter et Lister les Disques\" -- la connexion s'établit sur le "
                "réseau Tor, authentifiée avec votre clé",
            ],
            "warning": (
                "La connexion transite par plusieurs serveurs différents (relais) sur le réseau "
                "Tor -- attendez-vous à une latence beaucoup plus élevée et une vitesse beaucoup "
                "plus faible qu'une connexion directe. Une image disque volumineuse "
                "(dizaines/centaines de Go) peut prendre des heures. C'est pourquoi il s'agit "
                "vraiment d'un DERNIER RECOURS : essayez d'abord Direct/VPN si possible."
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
        "es": {
            "title": "Adquisición de RAM (Windows, local)",
            "icon": "cpu",
            "short": "Adquiere la memoria de este equipo -- no requiere conexión remota",
            "what": (
                "Adquiere forense de la memoria (RAM) de este propio equipo -- no requiere "
                "conexión remota, se ejecuta directamente en esta máquina."
            ),
            "when": [
                "El equipo que está examinando está frente a usted y actualmente encendido, y "
                "quiere capturar los datos en memoria antes de apagarlo sin perderlos",
            ],
            "requires": [
                "Sistema operativo Windows",
                "En modo Full (memoria completa): ejecutar como Administrador + el controlador "
                "debe estar cargado con test-signing habilitado (afecta la configuración de "
                "Secure Boot, debe prepararse de antemano en su propio equipo)",
            ],
            "steps": [
                "Haga clic en \"Iniciar\" e (opcionalmente) introduzca la información del caso",
                "Elija el modo \"Volcado de Proceso\" (memoria de un solo programa, no requiere "
                "administrador, rápido) o \"Completo\" (memoria completa del sistema, requiere administrador + controlador)",
                "En modo Volcado de Proceso, seleccione el proceso destino de la lista",
                "Haga clic en \"Iniciar\" para comenzar la adquisición",
                "Al finalizar, se genera automáticamente un informe con hash/tamaño/duración",
            ],
            "warning": None,
        },
        "de": {
            "title": "RAM-Erfassung (Windows, lokal)",
            "icon": "cpu",
            "short": "Erfasst den eigenen Arbeitsspeicher dieses Rechners -- keine Remote-Verbindung nötig",
            "what": (
                "Erfasst forensisch den Arbeitsspeicher (RAM) dieses Computers selbst -- keine "
                "Remote-Verbindung nötig, läuft direkt auf diesem Rechner."
            ),
            "when": [
                "Der zu untersuchende Computer steht vor Ihnen und ist gerade eingeschaltet, und "
                "Sie möchten die Daten im Speicher erfassen, bevor Sie ihn ausschalten, ohne sie zu verlieren",
            ],
            "requires": [
                "Windows-Betriebssystem",
                "Im Full-Modus (gesamter Speicher): Ausführung als Administrator + der Treiber "
                "muss mit aktiviertem Test-Signing geladen sein (betrifft die Secure-Boot-"
                "Einstellung, muss vorab auf Ihrem eigenen Rechner vorbereitet werden)",
            ],
            "steps": [
                "Klicken Sie auf \"Starten\" und geben Sie (optional) die Fallinformationen ein",
                "Wählen Sie den Modus \"Prozessabbild\" (Speicher eines einzelnen Programms, kein "
                "Administrator nötig, schnell) oder \"Vollständig\" (gesamter Systemspeicher, "
                "benötigt Administrator + Treiber)",
                "Wählen Sie im Prozessabbild-Modus den Zielprozess aus der Liste",
                "Klicken Sie auf \"Starten\", um die Erfassung zu beginnen",
                "Nach Abschluss wird automatisch ein Bericht mit Hash-/Größen-/Dauerangaben erstellt",
            ],
            "warning": None,
        },
        "pt": {
            "title": "Aquisição de RAM (Windows, local)",
            "icon": "cpu",
            "short": "Adquire a memória deste próprio computador -- não requer conexão remota",
            "what": (
                "Adquire forensicamente a memória (RAM) deste próprio computador -- não requer "
                "conexão remota, é executado diretamente nesta máquina."
            ),
            "when": [
                "O computador que você está examinando está à sua frente e atualmente ligado, e "
                "você quer capturar os dados em memória antes de desligá-lo sem perdê-los",
            ],
            "requires": [
                "Sistema operacional Windows",
                "No modo Full (memória completa): execução como Administrador + o driver deve "
                "estar carregado com test-signing habilitado (afeta a configuração do Secure "
                "Boot, deve ser preparado com antecedência em sua própria máquina)",
            ],
            "steps": [
                "Clique em \"Iniciar\" e (opcionalmente) insira as informações do caso",
                "Escolha o modo \"Dump de Processo\" (memória de um único programa, não requer "
                "administrador, rápido) ou \"Completo\" (memória completa do sistema, requer administrador + driver)",
                "No modo Dump de Processo, selecione o processo alvo na lista",
                "Clique em \"Iniciar\" para começar a aquisição",
                "Ao terminar, um relatório com informações de hash/tamanho/duração é gerado automaticamente",
            ],
            "warning": None,
        },
        "fr": {
            "title": "Acquisition de RAM (Windows, local)",
            "icon": "cpu",
            "short": "Acquiert la mémoire propre de cette machine -- aucune connexion distante nécessaire",
            "what": (
                "Acquiert de manière forensique la mémoire (RAM) de cet ordinateur lui-même -- "
                "aucune connexion distante nécessaire, s'exécute directement sur cette machine."
            ),
            "when": [
                "L'ordinateur que vous examinez est devant vous et actuellement allumé, et vous "
                "voulez capturer les données en mémoire avant de l'éteindre sans les perdre",
            ],
            "requires": [
                "Système d'exploitation Windows",
                "En mode Complet (mémoire entière) : exécution en tant qu'Administrateur + le "
                "pilote doit être chargé avec le test-signing activé (affecte le paramètre "
                "Secure Boot, doit être préparé à l'avance sur votre propre machine)",
            ],
            "steps": [
                "Cliquez sur \"Démarrer\" et (facultatif) saisissez les informations du dossier",
                "Choisissez le mode \"Dump de Processus\" (mémoire d'un seul programme, pas "
                "besoin d'administrateur, rapide) ou \"Complet\" (mémoire système entière, "
                "nécessite administrateur + pilote)",
                "En mode Dump de Processus, sélectionnez le processus cible dans la liste",
                "Cliquez sur \"Démarrer\" pour lancer l'acquisition",
                "Une fois terminé, un rapport avec les informations de hash/taille/durée est généré automatiquement",
            ],
            "warning": None,
        },
    },
}

# Bir yontem tanitim sayfasindaki kavramsal olarak agir bir konu icin
# Bilgi Merkezi'nde detayli anlatim varsa buraya eklenir -- yontem
# sayfasinda otomatik bir "Bu ne demek?" linki cikar (bkz. _show_method_detail).
METHOD_HELP_TOPIC = {
    "tor": "tor_onion_operator_key",
    "ram": "ram_full_mode_driver",
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


class TargetKitWorker(QThread):
    """Hedef taraf sihirbazinda "Bağlantıyı Başlat"a basilinca calisir --
    gomulu Tor'u ayaga kaldirip hidden service kurmak dakikalar surebilir
    (bkz. portable_kit/tor_manager.py timeout'lari), bu yuzden UI thread'ini
    bloke etmemek icin ayri thread'de calistirilir (ayni desen:
    gui_v2.py'deki ConnectWorker)."""
    done = Signal(object)   # basarili olursa HiddenServiceHandle
    error = Signal(str)

    def __init__(self, operator_public_key, parent=None):
        super().__init__(parent)
        self.operator_public_key = operator_public_key

    def run(self):
        if PORTABLE_KIT_DIR not in sys.path:
            sys.path.insert(0, PORTABLE_KIT_DIR)
        try:
            from tor_manager import start_hidden_service
        except ImportError as exc:
            self.error.emit(f"Bağlantı modülü yüklenemedi: {exc}")
            return

        try:
            handle = start_hidden_service(self.operator_public_key)
        except Exception as exc:
            self.error.emit(f"Bağlantı kurulurken beklenmedik bir hata oldu: {exc}")
            return

        if handle is None:
            self.error.emit(
                "Bağlantı kurulamadı. Anahtarı doğru yapıştırdığınızdan emin olun ve "
                "tekrar deneyin."
            )
            return
        self.done.emit(handle)


class ChameleonWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "tr"
        self.active_nav = "home"
        # Rapor HTML'sinde UTC'nin YANINA (report.json'un kendisi hic
        # etkilenmez) eklenen, sadece okunabilirlik icin yerel saat
        # aciklamasi -- "UTC" = hic ek aciklama yok (varsayilan).
        self.display_timezone = "UTC"
        self._target_handle = None
        self._target_worker = None
        # Bir arac ekranindaki ("SSH ile Uzak Imaj Al"/"RAM Imaji Al")
        # "Bu ne demek?" linkinden Bilgi Merkezi'ne gecilince, o ekran
        # (doldurulmus form + varsa acik SSH baglantisi/worker thread ile
        # birlikte) SILINMEDEN burada canli tutulur -- bkz. _show_help_from_tool.
        self._return_page = None
        self._return_nav = None
        # Bir arac ekraninda (SSH/RAM) aktif bir islem SURERKEN kullanici
        # "Ana Sayfa"ya ya da baska bir sidebar ogesine giderse, o ekran
        # (calisan worker dahil) SILINMEDEN burada saklanir -- boylece
        # kullanici ayni yonteme (sidebar'dan) tekrar tikladiginda SIFIRDAN
        # bir tanitim sayfasi degil, KALDIGI YERDEN (log/ilerleme dahil)
        # ekran gosterilir (kullanici bildirdi: "iş sürerken dashboard'a
        # dönünce bilgi merkezinden yazılar çıkıyor, olmaması lazım").
        # Ayni anda SADECE TEK bir aktif arac ekrani takip edilir.
        self._active_tool_widget = None
        self._active_tool_kind = None  # "ssh" | "ram"
        self._set_window_icon()
        # Sadece hedef-taraf (Bu Cihaz Inceleniyor) modunu iceren, daha
        # hafif/kafa karistirmayan ayri bir .exe icin (bkz. target_kit_main.py
        # + build_target_kit.spec) -- o giris noktasi bu degiskeni import
        # etmeden ONCE ayarlar. Boyle bir exe'de operator araclarinin (SSH/RAM
        # motorlari) kodu hic PAKETLENMEDIGI icin rol secimi anlamsiz/
        # kafa karistirici olurdu -- dogrudan sihirbaz acilir.
        self.target_only = os.environ.get("CHAMELEON_TARGET_ONLY") == "1"
        if self.target_only:
            self._show_target_wizard()
        else:
            self._show_role_select()

    def closeEvent(self, event):
        """Hedef taraf sihirbazinda acik birakilmis bir Tor sureci varsa,
        pencere kapanirken orphan process kalmasin diye kapatilir. Bilgi
        Merkezi'nde bekleyen (henuz "Geri" ile donulmemis) bir arac ekrani
        varsa o da temizlenir."""
        self._target_cleanup()
        if self._return_page is not None:
            self._return_page.deleteLater()
            self._return_page = None
        super().closeEvent(event)

    # -- Pencere ikonu ----------------------------------------------------
    def _set_window_icon(self):
        if os.path.exists(ICON_PNG):
            self.setWindowIcon(QIcon(ICON_PNG))

    # -- Rol secimi (uygulama acilir acilmaz ilk ekran) ---------------------
    def _show_role_select(self):
        """
        Uygulama HER ACILISTA (kayitli bir tercih yok -- her defasinda
        farkli bir kisi kullaniyor olabilir) bunu once sorar: "Operatörüm"
        secilirse normal sidebar/launcher akisi (_build_shell + _show_home)
        acilir, hic degismedi. "Bu Cihaz Inceleniyor" secilirse -- yani bu
        makineye SAHADAKI, teknik bilgisi olmayabilecek kisi oturmussa --
        sidebar/RAM-imaji/SSH-araclari gibi operator arac seti HIC
        GOSTERILMEZ, sadece Tor kitini calistirmaya yarayan, adim adim
        anlatilmis ayri bir sihirbaz (_show_target_wizard) acilir. Boylece
        ayni .exe iki farkli kisiye iki farkli, o kisiye uygun deneyim
        sunar (bkz. kullanicinin bu konudaki geri bildirimi).
        """
        self.setWindowTitle(t("title", self.lang))
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(ui.CARD_GAP)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QHBoxLayout()
        if os.path.exists(ICON_PNG):
            logo = QLabel()
            logo.setPixmap(QPixmap(ICON_PNG).scaledToHeight(28, Qt.TransformationMode.SmoothTransformation))
            header.addWidget(logo)
        name = QLabel(t("title", self.lang))
        name.setStyleSheet(f"font-family:'{ui.FONT_UI}'; font-size:16px; font-weight:600; color:{ui.TEXT_MAIN};")
        header.addWidget(name)
        header.addStretch()
        layout.addLayout(header)
        layout.addSpacing(12)

        title = QLabel("Bu bilgisayardaki kişi kimsiniz?")
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:20px; font-weight:600;")
        layout.addWidget(title)

        subtitle = QLabel("Devam etmeden önce rolünüzü seçin -- ekranın geri kalanı buna göre değişir.")
        subtitle.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(ui.CARD_GAP)

        op_card = widgets.Card("Operatörüm (İnceleyen)")
        op_desc = BodyText(
            "Delil topluyorum -- bir hedef cihaza bağlanacağım ya da bu bilgisayarın kendi "
            "belleğini/diskini inceleyeceğim.", secondary=False
        )
        op_desc.setWordWrap(True)
        op_card.body.addWidget(op_desc)
        op_btn = widgets.PrimaryButton("Operatör Olarak Devam Et")
        op_btn.clicked.connect(self._enter_operator_mode)
        op_card.body.addWidget(op_btn)
        row.addWidget(op_card)

        tg_card = widgets.Card("Bu Cihaz İnceleniyor")
        tg_desc = BodyText(
            "Bir operatör, bu bilgisayardan uzaktan veri toplayabilmek için benden bir "
            "bağlantı kanalı açmamı istedi (Tor \"acil durum\" kiti).", secondary=False
        )
        tg_desc.setWordWrap(True)
        tg_card.body.addWidget(tg_desc)
        tg_btn = widgets.PrimaryButton("Bu Cihazla Devam Et")
        tg_btn.clicked.connect(self._show_target_wizard)
        tg_card.body.addWidget(tg_btn)
        row.addWidget(tg_card)

        layout.addLayout(row)
        layout.addStretch()

        self.setCentralWidget(central)

    def _enter_operator_mode(self):
        self._build_shell()
        self._show_home()

    # -- Hedef taraf sihirbazi (Tor "acil durum" kiti) -----------------------
    def _step_card(self, number, heading):
        """Numarali bir sihirbaz adimi icin kart + o adima ozel icerigin
        eklenecegi (baslikla ayni girintideki) dikey layout'u doner."""
        card = widgets.Card("")
        row = QHBoxLayout()
        row.addWidget(widgets.StepBadge(number), alignment=Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(8)
        heading_lbl = QLabel(heading)
        heading_lbl.setWordWrap(True)
        heading_lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px; font-weight:600;")
        col.addWidget(heading_lbl)
        row.addLayout(col, stretch=1)
        card.body.addLayout(row)
        return card, col

    @staticmethod
    def _bi(tr, en, sep="\n"):
        """Turkce + Ingilizce metni birlikte dondurur. Hedef sihirbazi
        (_show_target_wizard) icin: bu ekranda dil sececek bir Ayarlar
        sayfasi yok (ozellikle sadece-hedef "hedef kiti" exe'sinde hic
        yok) -- Turkce bilmeyen biri sahada bu ekranla karsilasirsa
        okuyabilsin diye HER iki dil BIRLIKTE gosteriliyor, tek dil
        secmek yerine."""
        return f"{tr}{sep}{en}"

    def _show_target_wizard(self):
        self.setWindowTitle(t("title", self.lang))
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(ui.CARD_GAP)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        header = QHBoxLayout()
        if not self.target_only:
            # Sadece-hedef exe'sinde donulecek bir rol secim ekrani hic
            # olmadigi icin (operator araclari paketlenmedi) bu buton
            # gosterilmez.
            back_btn = widgets.SecondaryButton("← Geri")
            back_btn.clicked.connect(self._back_from_target_wizard)
            header.addWidget(back_btn)
        title = QLabel(self._bi(
            "Bu Cihazın İncelenmesi İçin Bağlantı Kanalı Aç",
            "Open a Connection Channel for This Device's Examination",
        ))
        title.setWordWrap(True)
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_TITLE}px; font-weight:600;")
        header.addWidget(title, stretch=1)
        layout.addLayout(header)

        intro = QLabel(self._bi(
            "Bu ekran, bir operatörün bu bilgisayara UZAKTAN, güvenli bir şekilde "
            "bağlanabilmesi için gereken teknik kanalı açar. Hiçbir dosyanız/veriniz bu "
            "ekrandan paylaşılmaz -- sadece operatörün önceden size verdiği anahtarla "
            "açılan, sadece ONA açık bir bağlantı noktası oluşturulur.",
            "This screen opens the technical channel an operator needs to connect to "
            "this computer REMOTELY and securely. None of your files/data are shared "
            "from this screen -- it only creates a connection point, opened with a key "
            "the operator gave you beforehand, that only THEY can access.",
        ))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(intro)

        # Adim 1: anahtar gir
        step1, col1 = self._step_card(1, self._bi("Operatör Anahtarını Girin", "Enter the Operator Key"))
        col1.addWidget(BodyText(
            self._bi(
                "Operatörünüzden ÖNCEDEN aldığınız anahtarı (telefon/e-posta ile size iletilmiş "
                "olmalı) aşağıya yapıştırın. Bu, sadece operatörün bu kanaldan bağlanabilmesini "
                "sağlayan bir kod -- bir şifre değildir, kimseye zarar veremez.",
                "Paste below the key you received from your operator BEFOREHAND (it should "
                "have been sent to you by phone/e-mail). This is just a code that lets the "
                "operator connect through this channel -- it is not a password, it cannot "
                "harm anyone.",
            ), secondary=True
        ))
        self.target_key_input = widgets.MonoInput()
        self.target_key_input.setPlaceholderText(self._bi(
            "Operatörden aldığınız anahtarı buraya yapıştırın",
            "Paste the key you received from the operator here",
            sep=" / ",
        ))
        col1.addWidget(self.target_key_input)

        # Yapistirilan anahtarin kisa bir "parmak izi" -- sahadaki kisi bunu
        # telefonla operatore okuyup dogru anahtari yapistirdigini teyit
        # edebilsin diye (guvenlik incelemesinde bulunan gercek bir bosluk:
        # onceden yapistirilan anahtar HICBIR sekilde dogrulanmiyordu, yanlis/
        # saldirgan bir anahtar da sessizce kabul edilirdi).
        self.target_key_fingerprint = QLabel("")
        self.target_key_fingerprint.setWordWrap(True)
        self.target_key_fingerprint.setStyleSheet(
            f"color:{ui.ACCENT_TEXT}; font-family:'{ui.FONT_MONO}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;"
        )
        self.target_key_fingerprint.hide()
        col1.addWidget(self.target_key_fingerprint)
        self.target_key_input.textChanged.connect(self._update_target_key_fingerprint)

        col1.addWidget(BodyText(
            self._bi(
                "Başlatmadan önce yukarıdaki kodu telefonla operatöre okuyup, "
                "kendi ekranındaki kodla AYNI olduğunu teyit edin.",
                "Before starting, read the code above to the operator over the phone "
                "and confirm it is THE SAME as the code on their own screen.",
            ), secondary=True
        ))
        layout.addWidget(step1)

        # Adim 2: baslat
        step2, col2 = self._step_card(2, self._bi("Bağlantıyı Başlatın", "Start the Connection"))
        col2.addWidget(BodyText(
            self._bi(
                "Aşağıdaki butona basın ve bekleyin -- bu, cihazınızın bir güvenlik ağı "
                "(Tor) üzerinden geçici bir kanal açmasını sağlar; birkaç dakika sürebilir.",
                "Press the button below and wait -- this makes your device open a "
                "temporary channel through a security network (Tor); it can take a few "
                "minutes.",
            ),
            secondary=True
        ))
        self.target_start_btn = widgets.PrimaryButton(self._bi("Bağlantıyı Başlat", "Start Connection", sep=" / "))
        self.target_start_btn.clicked.connect(self._target_start)
        col2.addWidget(self.target_start_btn)
        self.target_status_label = QLabel("")
        self.target_status_label.setWordWrap(True)
        self.target_status_label.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.target_status_label.hide()
        col2.addWidget(self.target_status_label)
        layout.addWidget(step2)

        # Adim 3: adresi ilet (basarili olunca gorunur)
        step3, col3 = self._step_card(3, self._bi("Oluşan Adresi Operatöre İletin", "Send the Generated Address to the Operator"))
        col3.addWidget(BodyText(
            self._bi(
                "Aşağıda çıkan adresi KENDİ telefonunuzla fotoğraflayın/yazın ve operatöre "
                "KENDİ mesajlaşma kanalınızla (SMS, telefonla okuyarak vb.) iletin -- bu "
                "cihazın kendi ağı/uygulamaları hiç kullanılmaz.",
                "Photograph or write down the address shown below with YOUR OWN phone and "
                "send it to the operator through YOUR OWN messaging channel (SMS, reading "
                "it over the phone, etc.) -- none of this device's own network/apps are "
                "used.",
            ), secondary=True
        ))
        onion_row = QHBoxLayout()
        self.target_onion_input = widgets.MonoInput()
        self.target_onion_input.setReadOnly(True)
        onion_row.addWidget(self.target_onion_input, stretch=1)
        copy_btn = widgets.SecondaryButton(self._bi("Kopyala", "Copy", sep=" / "))
        copy_btn.clicked.connect(self._target_copy_onion)
        onion_row.addWidget(copy_btn)
        col3.addLayout(onion_row)
        stop_btn = widgets.SecondaryButton(self._bi("Bağlantıyı Kapat", "Close Connection", sep=" / "))
        stop_btn.clicked.connect(self._target_stop)
        col3.addWidget(stop_btn)
        self.target_result_card = step3
        self.target_result_card.hide()
        layout.addWidget(step3)

        layout.addStretch()
        self.setCentralWidget(central)

    def _back_from_target_wizard(self):
        self._detach_target_worker()
        self._target_cleanup()
        self._show_role_select()

    def _detach_target_worker(self):
        """Sihirbazdan (henuz "Bağlantıyı Başlat"in sonucu gelmeden) cikilirsa
        calisan TargetKitWorker durdurulamaz (start_hidden_service() stem'in
        bloke eden bir cagrisi, disaridan iptal edilemiyor) -- ama sinyalleri
        artik SILINMIS olan sihirbaz widget'larina (target_start_btn vb.)
        baglı kalirsa, sonuc gec gelince RuntimeError ile cokerdi. Sinyalleri
        koparip, basarili olursa (biz zaten ayrildiktan sonra) sahipsiz bir
        Tor sureci kalmasin diye hemen kapatacak sekilde yeniden baglıyoruz."""
        worker = self._target_worker
        if worker is None or not worker.isRunning():
            return
        try:
            worker.done.disconnect()
            worker.error.disconnect()
        except (TypeError, RuntimeError):
            pass
        worker.done.connect(lambda handle: handle.close())

    def _update_target_key_fingerprint(self, text):
        key = text.strip()
        if not key:
            self.target_key_fingerprint.hide()
            return
        kod = key_fingerprint(key)
        self.target_key_fingerprint.setText(self._bi(f"Kod: {kod}", f"Code: {kod}", sep=" / "))
        self.target_key_fingerprint.show()

    def _target_start(self):
        if self._target_handle is not None:
            return  # zaten bagli -- once "Baglantiyi Kapat" gerekir
        key = self.target_key_input.text().strip()
        if not key:
            self.target_status_label.setStyleSheet(f"color:{ui.ERROR}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
            self.target_status_label.setText(self._bi(
                "Önce operatör anahtarını girin.", "Enter the operator key first.", sep=" / "
            ))
            self.target_status_label.show()
            return

        self.target_start_btn.setEnabled(False)
        self.target_start_btn.setText(self._bi(
            "Başlatılıyor... (birkaç dakika sürebilir)",
            "Starting... (can take a few minutes)",
            sep=" / ",
        ))
        self.target_status_label.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.target_status_label.setText(self._bi(
            "Bağlantı hazırlanıyor, lütfen bekleyin...", "Preparing the connection, please wait...", sep=" / "
        ))
        self.target_status_label.show()

        self._target_worker = TargetKitWorker(key)
        self._target_worker.done.connect(self._on_target_started)
        self._target_worker.error.connect(self._on_target_error)
        self._target_worker.start()

    def _on_target_started(self, handle):
        self._target_handle = handle
        # Buton BILEREK devre disi/"Bagli" yaziyor kaliyor -- zaten aktif bir
        # baglanti varken tekrar "Baslat"a basilip ikinci bir hidden service
        # kurulmaya calisilmasin diye (once "Baglantiyi Kapat" gerekir).
        self.target_start_btn.setEnabled(False)
        self.target_start_btn.setText(self._bi("Bağlı", "Connected", sep=" / "))
        self.target_status_label.hide()
        self.target_key_input.setEnabled(False)
        self.target_onion_input.setText(f"{handle.onion_address}.onion")
        self.target_result_card.show()

    def _on_target_error(self, msg):
        self.target_start_btn.setEnabled(True)
        self.target_start_btn.setText(self._bi("Bağlantıyı Başlat", "Start Connection", sep=" / "))
        self.target_status_label.setStyleSheet(f"color:{ui.ERROR}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.target_status_label.setText(msg)
        self.target_status_label.show()

    def _target_copy_onion(self):
        QApplication.clipboard().setText(self.target_onion_input.text())

    def _target_stop(self):
        self._target_cleanup()
        self.target_start_btn.setEnabled(True)
        self.target_start_btn.setText("Bağlantıyı Başlat")
        self.target_result_card.hide()
        self.target_key_input.setEnabled(True)
        self.target_key_input.clear()
        self.target_status_label.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.target_status_label.setText("Bağlantı kapatıldı.")
        self.target_status_label.show()

    def _target_cleanup(self):
        if self._target_handle is not None:
            self._target_handle.close()
            self._target_handle = None

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
            ("home", "home", t("nav_home", lang), self._show_home),
            ("direct", "link", t("nav_direct", lang), self._show_direct_detail),
            ("vpn", "shield", t("nav_vpn", lang), self._show_vpn_detail),
            ("tor", "shield-alert", t("nav_tor", lang), self._show_tor_detail),
            ("ram", "cpu", t("nav_ram", lang), self._show_ram_detail),
            ("history", "clock", t("nav_history", lang), self._show_case_history),
            ("incomplete", "alert-triangle", t("nav_incomplete", lang), self._show_incomplete_operations),
            ("help", "info", t("nav_help", lang), self._show_help),
            ("settings", "settings", t("nav_settings", lang), self._show_settings),
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
    def _widget_has_running_worker(self, widget):
        """widget (ForensicWidget/RamEngineWidget) hala calisan bir isi
        (acq_worker/worker) tutuyor mu? DIKKAT: findChildren(QThread) burada
        ISE YARAMAZ -- worker'lar bilerek Qt parent'siz olusturuluyor (widget
        silinirken CALISAN bir thread'in Qt tarafindan da silinip programin
        cokmesi riskini onlemek icin, bkz. docs/hatalar_ve_sonuclar.md), bu
        yuzden Qt'nin parent-child agacinda widget'in "child"i SAYILMIYORLAR
        ve findChildren onlari hic BULAMAZ (bu, _release_return_page'in
        ONCEDEN kullandigi ama hicbir zaman GERCEKTE calismayan bir kontroldu
        -- ayni duzeltmeyle burada da giderildi). Bunun yerine widget'in
        KENDI worker attribute'unu (motor turune gore ismi farkli) dogrudan
        kontrol ediyoruz."""
        def _worker_of(w):
            return getattr(w, "acq_worker", None) or getattr(w, "worker", None)

        # widget dogrudan ForensicWidget/RamEngineWidget olabilir, YA DA
        # (stack_layout'a eklenen sey genelde oyle) onu SARAN bos bir
        # QWidget container olabilir (bkz. _open_ssh_engine/_open_ram_engine
        # -- page_layout.addWidget(ssh_widget)) -- ikinci durumda gercek
        # arac widget'i, container'in Qt child'i olarak findChildren ile
        # bulunabiliyor.
        adaylar = [widget] + widget.findChildren(QWidget)
        for w in adaylar:
            worker = _worker_of(w)
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    return True
            except RuntimeError:
                # Qt C++ nesnesi zaten silinmis -- bu adayi atla.
                continue
        return False

    def _clear_content(self):
        while self.stack_layout.count():
            item = self.stack_layout.takeAt(0)
            w = item.widget()
            if w:
                if w is self._active_tool_widget and self._widget_has_running_worker(w):
                    # Aktif bir islem SURERKEN kullanici baska bir sayfaya
                    # gidiyor -- ekran SILINMEDEN (deleteLater CAGIRMADAN)
                    # sadece gizlenip saklanir (bkz. self._active_tool_widget
                    # aciklamasi, __init__).
                    w.hide()
                    continue
                # deleteLater() asenkron -- hemen ardindan silinecek widget
                # bir sonraki olay dongusune kadar hala "var" sayilir (bkz.
                # ayni sinif Bilgi Merkezi bug'i, docs/hatalar_ve_sonuclar.md).
                # hide() ile gorunmez/erisilemez yapmak, silinme gerceklesene
                # kadarki bu araliktaki yan etkileri (findChildren'da eski
                # sayfanin gorunmesi, vs.) onluyor.
                w.hide()
                w.deleteLater()
                if w is self._active_tool_widget:
                    # Isi bitmis (artik calisan worker'i yok) bir arac
                    # ekrani -- artik "aktif" sayilmasin, normal tanitim
                    # akisina geri donulsun.
                    self._active_tool_widget = None
                    self._active_tool_kind = None
        page = QWidget()
        self.stack_layout.addWidget(page)
        return page

    def _resume_active_tool(self, kind):
        """Aktif ekran + running-worker araniyorsa, onu (SIFIRDAN tanitim
        sayfasi yerine) stack'e geri ekleyip True doner. Yoksa/baska
        turdeyse/isi bitmisse False doner -- cagiran taraf normal akisina
        (tanitim sayfasi) devam eder."""
        if self._active_tool_kind != kind or self._active_tool_widget is None:
            return False
        if not self._widget_has_running_worker(self._active_tool_widget):
            self._active_tool_widget = None
            self._active_tool_kind = None
            return False
        # _clear_content _COK ONEMLI: mevcut (bos) sayfayi ATMADAN once
        # cagirmiyoruz -- zaten stack'te baska bir sey yok (bu fonksiyon
        # sidebar tiklamasinin EN BASINDA cagriliyor, _clear_content HENUZ
        # calismadi). Once stack'i normal yoldan temizleyelim (bu, _active_
        # tool_widget'i TEKRAR yanlislikla silmeyecek -- kendisiyle
        # karsilastirma disinda hicbir sey stack'te degil zaten).
        self._clear_content()
        self.stack_layout.addWidget(self._active_tool_widget)
        self._active_tool_widget.show()
        return True

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
        body.addWidget(BodyText(t("home_intro", lang)))

        recent_card = self._recent_case_card()
        if recent_card is not None:
            body.addWidget(recent_card)

        for key, handler in [
            ("direct", self._show_direct_detail), ("vpn", self._show_vpn_detail),
            ("tor", self._show_tor_detail), ("ram", self._show_ram_detail),
        ]:
            info = METHOD_INFO[key][self.lang]
            body.addWidget(self._home_card(info, handler))
        body.addStretch()

    def _recent_case_card(self):
        """Ana Sayfa'da, Vaka Geçmişi'ndeki EN SON kaydı gösteren kısa bir
        kısayol karti -- operatör her seferinde sidebar'dan "Vaka Geçmişi"ne
        gidip listeyi taramadan, az önce bitirdiği işin raporunu tek
        tıkla açabilsin diye. Geçmiş boşsa (ilk çalıştırma) ya da
        forensic_report import edilemezse (bkz. _show_case_history'deki
        AYNI hata durumu) sessizce None döner -- Ana Sayfa'da hata yerine
        sadece bu kart hiç görünmez."""
        if SSH_ENGINE_DIR not in sys.path:
            sys.path.insert(0, SSH_ENGINE_DIR)
        try:
            import forensic_report
        except ImportError:
            return None
        entries = forensic_report.read_history()
        if not entries:
            return None

        entry = entries[0]
        lang = self.lang
        status_renk = {"success": ui.SUCCESS, "partial": ui.WARNING, "failed": ui.ERROR}

        card = widgets.Card(t("home_recent_case_title", lang))
        row = QHBoxLayout()

        info_col = QVBoxLayout()
        baslik = entry.get("case_id") or t("case_history_no_case_id", lang)
        case_lbl = QLabel(baslik)
        case_lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:14px; font-weight:600;")
        info_col.addWidget(case_lbl)
        durum = entry.get("status") or "—"
        detay = QLabel(f"{entry.get('start_time_utc') or '—'}  ·  {durum}")
        detay.setStyleSheet(
            f"color:{status_renk.get(durum, ui.TEXT_SECONDARY)}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;"
        )
        info_col.addWidget(detay)
        row.addLayout(info_col, stretch=1)

        html_path = entry.get("html_path")
        if html_path and os.path.isfile(html_path):
            open_btn = widgets.SecondaryButton(t("btn_open_report", lang))
            open_btn.clicked.connect(lambda _checked=False, p=html_path: os.startfile(p))
            row.addWidget(open_btn)

        view_all_btn = widgets.SecondaryButton(t("btn_view_all_cases", lang))
        view_all_btn.clicked.connect(self._show_case_history)
        row.addWidget(view_all_btn)

        card.body.addLayout(row)
        return card

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

        open_btn = widgets.SecondaryButton(t("btn_open", self.lang))
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

        topic_key = METHOD_HELP_TOPIC.get(nav_key)
        if topic_key:
            body.addWidget(self._help_link(topic_key, t("btn_read_in_help_center", lang)))

        body.addWidget(self._info_section(t("method_when_heading", lang), info["when"]))
        body.addWidget(self._info_section(t("method_requires_heading", lang), info["requires"], numbered=True))
        body.addWidget(self._info_section(t("method_steps_heading", lang), info["steps"], numbered=True))

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

        start_btn = widgets.PrimaryButton(t("btn_start", lang))
        start_btn.clicked.connect(start_command)
        row = QHBoxLayout()
        row.addWidget(start_btn)
        row.addStretch()
        row_w = QWidget()
        row_w.setLayout(row)
        body.addWidget(row_w)
        body.addStretch()

    def _help_link(self, topic_key, label=None):
        """Bilgi Merkezi'ndeki bir konuya dogrudan goturen, mavi metin
        gorunumlu kucuk bir buton -- shared/help_content.py'deki basligi
        varsayilan etiket olarak kullanir."""
        topic = get_topic(topic_key, self.lang)
        if topic is None:
            return QLabel("")
        btn = QPushButton(label or t("what_does_this_mean_titled", self.lang, title=topic['title']))
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color:{ui.ACCENT_TEXT}; background:transparent; border:none; "
            f"text-align:left; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; "
            f"padding:2px 0; }} QPushButton:hover {{ color:{ui.ACCENT_HOVER}; }}"
        )
        btn.clicked.connect(lambda: self._show_help(topic_key))
        return btn

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
        if self._resume_active_tool("ssh"):
            return
        self._show_method_detail("direct", lambda: self._show_case_info(lambda case: self._open_ssh_engine("direct", case)))

    def _show_vpn_detail(self):
        if self._resume_active_tool("ssh"):
            return
        self._show_method_detail("vpn", lambda: self._show_case_info(lambda case: self._open_ssh_engine("vpn", case)))

    def _show_tor_detail(self):
        if self._resume_active_tool("ssh"):
            return
        self._show_method_detail("tor", lambda: self._show_case_info(lambda case: self._open_ssh_engine("tor", case)))

    def _show_ram_detail(self):
        if self._resume_active_tool("ram"):
            return
        self._show_method_detail("ram", lambda: self._show_case_info(lambda case: self._open_ram_engine(case)))

    # -- Vaka Bilgileri ----------------------------------------------------
    def _show_case_info(self, on_continue):
        page = self._clear_content()
        body = self._scrollable(page)
        lang = self.lang

        title = QLabel(t("case_info_title", lang))
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_TITLE}px; font-weight:600;")
        body.addWidget(title)

        card = widgets.Card()
        card.setMaximumWidth(640)
        note = QLabel(t("case_info_note", lang))
        note.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style:italic;")
        card.body.addWidget(note)

        entries = {}
        for key, label in [
            ("case_id", t("field_case_id", lang)),
            ("examiner", t("field_examiner", lang)),
            ("custodian", t("field_custodian", lang)),
            ("organization", t("field_organization", lang)),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(190)
            row.addWidget(lbl)
            entry = widgets.Input()
            row.addWidget(entry)
            card.body.addLayout(row)
            entries[key] = entry

        tz_row = QHBoxLayout()
        tz_lbl = QLabel(t("settings_timezone_row_label", lang))
        tz_lbl.setFixedWidth(190)
        tz_row.addWidget(tz_lbl)
        tz_combo = QComboBox()
        tz_combo.setStyleSheet(f"""
            QComboBox {{ background-color:{ui.BG_LAYER2}; color:{ui.TEXT_MAIN};
                border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; padding:4px 8px; }}
        """)
        tz_combo.addItem(t("settings_timezone_utc_option", lang), "UTC")
        for key, label in tz_display.common_timezones():
            if key == "UTC":
                continue
            tz_combo.addItem(label, key)
        current_index = tz_combo.findData(self.display_timezone)
        tz_combo.setCurrentIndex(current_index if current_index >= 0 else 0)
        tz_combo.currentIndexChanged.connect(
            lambda i: setattr(self, "display_timezone", tz_combo.itemData(i))
        )
        tz_row.addWidget(tz_combo)
        tz_row.addStretch()
        card.body.addLayout(tz_row)

        def _continue():
            on_continue({k: e.text().strip() for k, e in entries.items()})

        cont_btn = widgets.PrimaryButton(t("btn_continue", lang))
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

    # -- Bilgi Merkezi ------------------------------------------------------
    def _show_help(self, topic_key=None):
        """Uygulama icindeki cesitli secim/kavramlarin (orn. host key
        dogrulama, Live/Offline, Tor/.onion) detayli anlatildigi ayri sayfa --
        icerik shared/help_content.py'den okunur, arac ekranlarindaki "Bu ne
        demek?" linkleriyle AYNI kaynaktir (bkz. help_content.py).

        topic_key verilirse (bir arac ekranindaki linkten gelindiyse), o
        konunun kartina otomatik kaydirilir -- QTimer.singleShot(0, ...) ile,
        cunku scroll alani ilk anda henuz boyutlandirilmamis oluyor, bir
        sonraki event loop turunda (layout hesaplandiktan sonra) calismasi
        gerekiyor."""
        self._set_active_nav("help")
        page = self._clear_content()
        lang = self.lang

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

        if self._return_page is not None:
            back_btn = widgets.SecondaryButton(t("help_back_to_tool", lang))
            back_btn.clicked.connect(self._return_from_help)
            inner_layout.addWidget(back_btn)

        title = QLabel(t("help_center_title", lang))
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:18px; font-weight:600;")
        inner_layout.addWidget(title)

        intro = QLabel(t("help_center_intro", lang))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        inner_layout.addWidget(intro)

        topic_cards = {}
        for topic in HELP_TOPICS:
            card = widgets.Card(topic["title"].get(lang, topic["title"]["tr"]))
            text = QLabel(topic["body"].get(lang, topic["body"]["tr"]))
            text.setWordWrap(True)
            text.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px;")
            card.body.addWidget(text)
            inner_layout.addWidget(card)
            topic_cards[topic["key"]] = card

        inner_layout.addStretch()

        if topic_key and topic_key in topic_cards:
            target = topic_cards[topic_key]
            # ensureWidgetVisible() SADECE kart kismen bile olsa viewport'ta
            # goruniyorsa neredeyse hic kaydirmiyor (kartin gorunmesi icin
            # "yeterli" gordugu icin) -- kart sayfanin altlarina yakinsa bu,
            # kaydirmanin hicbir seye yaramamis gibi hissettiriyor (bkz.
            # kullanicinin "sanki sayfanin basina atiyor" geri bildirimi).
            # Bunun yerine kartin USTUNU aciktan viewport'un ustune tasiyoruz
            # -- "buraya geldin" hissi net olsun diye.
            def _scroll_to_target(t=target):
                scroll.verticalScrollBar().setValue(max(0, t.y() - 16))
            QTimer.singleShot(0, _scroll_to_target)

    def _release_return_page(self):
        """_return_page'i (varsa) birakir. Icinde HALA CALISAN bir worker
        (orn. devam eden bir SSH imaj alma islemi) varsa ONU SESSIZCE
        SILMEZ -- bir adli bilisim aracinda yari yolda kesilen bir alma
        islemi, ekranda gorunmeyen bir sayfada saklı kalmasindan cok daha
        kotu bir sonuc olurdu. Boyle bir durumda sayfa OLDUGU GIBI birakilir,
        is bitene kadar bir sonraki cagrida tekrar kontrol edilir.

        NOT: onceden findChildren(QThread) ile generic bir arama yapiliyordu
        ama bu HICBIR ZAMAN GERCEKTE calismiyordu -- worker'lar (acq_worker/
        worker) BILEREK Qt parent'siz olusturuluyor (bkz.
        _widget_has_running_worker docstring'i), bu yuzden Qt'nin parent-
        child agacinda hic gorunmuyorlar ve findChildren onlari asla
        BULAMIYORDU (any(...) hep False donuyordu, "hala calisiyor" kontrolu
        FIILEN hicbir zaman calismamis oldu -- gercek bir bug, bkz.
        docs/hatalar_ve_sonuclar.md). Duzeltme: findChildren(QWidget) ile
        ICERIDEKI arac widget'larini (ForensicWidget/RamEngineWidget) bulup
        HER birinin KENDI worker attribute'unu _widget_has_running_worker
        ile kontrol ediyoruz."""
        if self._return_page is None:
            return
        if any(self._widget_has_running_worker(w) for w in self._return_page.findChildren(QWidget)):
            return
        self._return_page.deleteLater()
        self._return_page = None

    def _show_help_from_tool(self, topic_key):
        """SSH/RAM arac ekranlarindaki "Bu ne demek?" linklerinin
        cagirdigi giris noktasi (on_show_help). Duz _show_help'ten farki:
        Bilgi Merkezi'ne gecmeden ONCE, o an ekranda duran arac ekranini
        (doldurulmus form alanlari + varsa acik SSH baglantisi/worker
        thread dahil) SILMEDEN stack'ten cikarip saklar -- boylece
        "Kaldığınız yere dön" ile hicbir bilgi kaybetmeden aynen kaldigi
        yere donulebiliyor (bkz. kullanicinin "bosluklari tekrar
        doldurmak gerekiyor" geri bildirimi)."""
        # Daha once "Geri" ile donulmemis, unutulmus bir sayfa varsa (orn.
        # kullanici Bilgi Merkezi'ndeyken baska bir sidebar ogesine
        # tikladiysa) onu simdi birak.
        self._release_return_page()

        if self.stack_layout.count():
            item = self.stack_layout.takeAt(0)
            self._return_page = item.widget()
        self._return_nav = self.active_nav
        self._show_help(topic_key)

    def _return_from_help(self):
        if self._return_page is None:
            return
        while self.stack_layout.count():
            old = self.stack_layout.takeAt(0)
            w = old.widget()
            if w:
                # hide() hemen (senkron) etkili olur; deleteLater() bir
                # sonraki event loop turunu bekledigi icin, sadece ona
                # guvenmek Bilgi Merkezi sayfasinin bir an icin donen
                # sayfanin ustunde/altinda kalip gorunmeye devam etmesine
                # yol aciyordu (headless testte yakalandi).
                w.hide()
                w.deleteLater()
        self.stack_layout.addWidget(self._return_page)
        self._return_page.show()
        self._return_page = None
        self._set_active_nav(self._return_nav)

    # -- Ayarlar ----------------------------------------------------------
    def _show_settings(self):
        self._set_active_nav("settings")
        page = self._clear_content()
        body = self._scrollable(page)
        lang = self.lang

        title = QLabel(t("settings_title", lang))
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:18px; font-weight:600;")
        body.addWidget(title)

        lang_card = widgets.Card(t("settings_language_card", lang))
        lang_row = QHBoxLayout()
        lang_group = QButtonGroup(lang_card)
        for code, native_name in LANGUAGES:
            r = widgets.RadioButton(f"{code.upper()}  {native_name}")
            r.setChecked(lang == code)
            lang_group.addButton(r)
            lang_row.addWidget(r)
            r.toggled.connect(lambda checked, c=code: checked and self._apply_lang(c))
        lang_row.addStretch()
        lang_card.body.addLayout(lang_row)
        body.addWidget(lang_card)

        theme_card = widgets.Card(t("settings_theme_card", lang))
        theme_row = QHBoxLayout()
        theme_group = QButtonGroup(theme_card)
        current_mode = ui.get_mode()
        radio_dark = widgets.RadioButton(t("theme_dark", lang))
        radio_light = widgets.RadioButton(t("theme_light", lang))
        radio_dark.setChecked(current_mode == "dark")
        radio_light.setChecked(current_mode == "light")
        for r, mode in [(radio_dark, "dark"), (radio_light, "light")]:
            theme_group.addButton(r)
            theme_row.addWidget(r)
            r.toggled.connect(lambda checked, m=mode: checked and self._apply_theme(m))
        theme_row.addStretch()
        theme_card.body.addLayout(theme_row)
        body.addWidget(theme_card)

        tz_card = widgets.Card(t("settings_timezone_card", lang))
        tz_note = BodyText(t("settings_timezone_note", lang))
        tz_card.body.addWidget(tz_note)
        tz_row = QHBoxLayout()
        tz_row.addWidget(QLabel(t("settings_timezone_row_label", lang)))
        tz_combo = QComboBox()
        tz_combo.setMinimumWidth(280)
        tz_combo.setStyleSheet(f"""
            QComboBox {{ background-color:{ui.BG_LAYER2}; color:{ui.TEXT_MAIN};
                border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; padding:4px 8px; }}
        """)
        tz_combo.addItem(t("settings_timezone_utc_option", lang), "UTC")
        for key, label in tz_display.common_timezones():
            if key == "UTC":
                continue
            tz_combo.addItem(label, key)
        current_index = tz_combo.findData(self.display_timezone)
        tz_combo.setCurrentIndex(current_index if current_index >= 0 else 0)
        tz_combo.currentIndexChanged.connect(
            lambda i: setattr(self, "display_timezone", tz_combo.itemData(i))
        )
        tz_row.addWidget(tz_combo)
        tz_row.addStretch()
        tz_card.body.addLayout(tz_row)
        body.addWidget(tz_card)

        body.addWidget(BodyText(f"Chameleon v{version.VERSION}"))
        body.addStretch()

    # -- Vaka Gecmisi -----------------------------------------------------
    def _show_case_history(self):
        """
        forensic_report.read_history()'nin okudugu shared/data/case_history.json
        listesini gosterir -- her motor/oturumdan alinan tum imajlarin ozeti.
        Bu dosyaya HER rapor kaydedildiginde zaten yaziliyordu (bkz.
        ForensicReport._append_to_history), sadece bunu gosteren bir sayfa
        eksikti (bkz. docs/hatalar_ve_sonuclar.md).
        """
        self._set_active_nav("history")
        page = self._clear_content()
        body = self._scrollable(page)
        lang = self.lang

        header = QHBoxLayout()
        title = QLabel(t("case_history_title", lang))
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:18px; font-weight:600;")
        header.addWidget(title)
        header.addStretch()

        if SSH_ENGINE_DIR not in sys.path:
            sys.path.insert(0, SSH_ENGINE_DIR)
        try:
            import forensic_report
        except ImportError as exc:
            body.addLayout(header)
            body.addWidget(BodyText(t("case_history_load_error", lang, exc=exc)))
            body.addStretch()
            return

        entries = forensic_report.read_history()

        export_btn = widgets.SecondaryButton(t("case_history_export_csv", lang))
        export_btn.setEnabled(bool(entries))
        export_btn.clicked.connect(lambda: self._export_case_history_csv(entries))
        header.addWidget(export_btn)
        body.addLayout(header)

        self._history_status = BodyText("")
        body.addWidget(self._history_status)

        if not entries:
            body.addWidget(BodyText(t("case_history_empty", lang)))
            body.addStretch()
            return

        search_input = widgets.Input(t("case_history_search_placeholder", lang))
        body.addWidget(search_input)

        cards_container = QWidget()
        cards_layout = QVBoxLayout(cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(ui.CARD_GAP)
        body.addWidget(cards_container)
        body.addStretch()

        status_renk = {"success": ui.SUCCESS, "partial": ui.WARNING, "failed": ui.ERROR}
        engine_adi = {"ssh_engine": t("engine_ssh", lang),
                      "ram_engine": t("engine_ram", lang)}
        tags = forensic_report.read_tags()

        def _matches(entry, needle):
            if not needle:
                return True
            needle = needle.lower()
            haystack = " ".join(str(entry.get(k) or "") for k in (
                "case_id", "examiner", "custodian", "organization",
                "target_host", "source_identifier",
            )).lower()
            return needle in haystack

        def _save_tag(report_path, edit):
            forensic_report.set_tag(report_path, edit.text())

        def _section_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color:{ui.ACCENT_TEXT}; font-family:'{ui.FONT_UI}'; "
                f"font-size:{ui.SIZE_BODY}px; font-weight:600;"
            )
            return lbl

        def _build_entry_card(entry):
            baslik = entry.get("case_id") or t("case_history_no_case_id", lang)
            card = widgets.Card(baslik)
            satirlar = [
                (t("label_engine", lang), engine_adi.get(entry.get("engine"), entry.get("engine") or "—")),
                (t("label_target", lang), entry.get("target_host") or entry.get("source_identifier") or "—"),
                (t("label_examiner", lang), entry.get("examiner") or "—"),
                (t("label_custodian", lang), entry.get("custodian") or "—"),
                (t("label_organization", lang), entry.get("organization") or "—"),
                (t("label_date", lang), entry.get("start_time_utc") or "—"),
            ]
            for etiket, deger in satirlar:
                row = QHBoxLayout()
                lbl = QLabel(f"{etiket}:")
                lbl.setFixedWidth(120)
                lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
                row.addWidget(lbl)
                val = QLabel(str(deger))
                val.setWordWrap(True)
                val.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
                row.addWidget(val, stretch=1)
                card.body.addLayout(row)

            report_path = entry.get("report_path")
            if report_path:
                tag_row = QHBoxLayout()
                tag_lbl = QLabel(f"{t('case_history_tag_label', lang)}:")
                tag_lbl.setFixedWidth(120)
                tag_lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
                tag_row.addWidget(tag_lbl)
                tag_edit = widgets.Input(t("case_history_tag_placeholder", lang))
                tag_edit.setText(tags.get(report_path, ""))
                tag_edit.editingFinished.connect(
                    lambda p=report_path, e=tag_edit: _save_tag(p, e)
                )
                tag_row.addWidget(tag_edit, stretch=1)
                card.body.addLayout(tag_row)

            footer = QHBoxLayout()
            durum = entry.get("status") or "—"
            durum_lbl = QLabel(durum)
            durum_lbl.setStyleSheet(
                f"color:{status_renk.get(durum, ui.TEXT_SECONDARY)}; font-family:'{ui.FONT_UI}'; "
                f"font-size:{ui.SIZE_HELPER}px; font-weight:600;"
            )
            footer.addWidget(durum_lbl)
            footer.addStretch()

            html_path = entry.get("html_path")
            if html_path and os.path.isfile(html_path):
                open_btn = widgets.SecondaryButton(t("btn_open_report", lang))
                open_btn.clicked.connect(lambda _checked=False, p=html_path: os.startfile(p))
                footer.addWidget(open_btn)
            if report_path and os.path.isfile(report_path):
                pdf_btn = widgets.SecondaryButton(t("btn_export_pdf", lang))
                pdf_btn.clicked.connect(lambda _checked=False, p=report_path: self._export_report_pdf(p))
                footer.addWidget(pdf_btn)
            card.body.addLayout(footer)
            return card

        def _render(needle=""):
            while cards_layout.count():
                item = cards_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    # takeAt() widget'i layout'tan cikarir ama GORUNMEZ
                    # yapmaz -- deleteLater() de asenkron oldugu icin
                    # widget bir sonraki event loop turuna kadar hala
                    # "gorunur" sayilir (ayni sinif sorun _clear_content()'te
                    # de vardi, bkz. docs/hatalar_ve_sonuclar.md). hide()
                    # olmadan hizli ardisik aramalarda eski kartlar bir an
                    # icin ekranda kalirdi.
                    w.hide()
                    w.deleteLater()

            # Oxygen Forensic Detective'in "Cases" listesinden esinlenildi
            # (bir vaka altinda birden fazla extraction bir arada gosteriliyor):
            # ayni vaka numarasina sahip kayitlar tek baslik altinda
            # gruplanir, vaka no'suz kayitlar ayri bir bolumde (Oxygen'daki
            # "Unassigned extractions" karsiligi) toplanir. Tek kayitli bir
            # vaka icin grup basligi eklenmez -- yaygin/basit durumda
            # (vaka basina tek imaj) gorsel gurultu yaratmasin diye.
            by_case = {}
            no_case = []
            for entry in entries:
                if not _matches(entry, needle):
                    continue
                case_id = entry.get("case_id")
                if case_id:
                    by_case.setdefault(case_id, []).append(entry)
                else:
                    no_case.append(entry)

            for case_id, group in by_case.items():
                if len(group) > 1:
                    cards_layout.addWidget(_section_label(
                        f"{case_id} — {t('case_history_group_count', lang, count=len(group))}"
                    ))
                for entry in group:
                    cards_layout.addWidget(_build_entry_card(entry))

            if no_case:
                if by_case:
                    cards_layout.addWidget(_section_label(t("case_history_no_case_id", lang)))
                for entry in no_case:
                    cards_layout.addWidget(_build_entry_card(entry))

        search_input.textChanged.connect(_render)
        _render()

    def _export_report_pdf(self, report_path):
        lang = self.lang
        default_name = os.path.splitext(os.path.basename(report_path))[0] + ".pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, t("pdf_save_dialog_title", lang), default_name, "PDF (*.pdf)",
        )
        if not path:
            return
        if SSH_ENGINE_DIR not in sys.path:
            sys.path.insert(0, SSH_ENGINE_DIR)
        import forensic_report
        try:
            forensic_report.export_pdf(report_path, path)
        except Exception as exc:
            self._history_status.setText(t("pdf_export_error", lang, exc=exc))
            return
        self._history_status.setText(t("pdf_export_success", lang, path=path))

    def _show_incomplete_operations(self):
        """
        docs/roadmap.md madde 0.2 -- "Yarim Kalanlar" sayfasi. Iki ayri
        kaynagi birlestirip gosterir:
          - SSH tam disk imajlama: image_acquirer.list_incomplete_manifests()
            (gercek chunk-bazli resume altyapisi zaten var, bkz. madde 0.1)
          - RAM motoru: incomplete_ops.list_incomplete() (gercek resume
            MUMKUN DEGIL -- sadece "basladi, bitirmedi" kaydi + "yeniden
            baslat" kolayligi, bkz. shared/incomplete_ops.py)
        SSH dosya/klasor modu (madde 0.4) henuz bu listeye dahil degil --
        o mod icin kalici bir devam noktasi henuz yazilmadi.
        """
        self._set_active_nav("incomplete")
        page = self._clear_content()
        body = self._scrollable(page)
        lang = self.lang

        title = QLabel(t("incomplete_title", lang))
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:18px; font-weight:600;")
        body.addWidget(title)

        note = BodyText(t("incomplete_intro", lang))
        body.addWidget(note)

        if SSH_ENGINE_DIR not in sys.path:
            sys.path.insert(0, SSH_ENGINE_DIR)
        if SHARED_DIR not in sys.path:
            sys.path.insert(0, SHARED_DIR)

        kartlar = []
        try:
            import image_acquirer
            for manifest_path, veri in image_acquirer.list_incomplete_manifests():
                kartlar.append(("ssh_disk", manifest_path, veri))
            for manifest_path, veri in image_acquirer.list_incomplete_tree_manifests():
                kartlar.append(("ssh_tree", manifest_path, veri))
        except ImportError:
            pass
        try:
            import incomplete_ops
            for op_id, veri in incomplete_ops.list_incomplete():
                kartlar.append(("ram", op_id, veri))
        except ImportError:
            pass

        if not kartlar:
            body.addWidget(BodyText(t("incomplete_empty", lang)))
            body.addStretch()
            return

        for kind, ref, veri in kartlar:
            if kind == "ssh_disk":
                completed = len(veri.get("acquired_blocks", []))
                total = veri.get("total_blocks", 0)
                baslik = veri.get("disk_path") or "—"
                card = widgets.Card(baslik)
                satirlar = [
                    (t("label_type", lang), t("type_ssh_full_disk", lang)),
                    (t("label_target", lang), veri.get("host") or "—"),
                    (t("label_progress", lang), t("progress_blocks", lang, completed=completed, total=total)),
                    (t("label_started", lang), veri.get("started_at_utc") or "—"),
                ]
                devam_metni = t("incomplete_resume_hint_disk", lang)
            elif kind == "ssh_tree":
                completed = len(veri.get("acquired_files", []))
                total = veri.get("total_files", 0)
                baslik = veri.get("remote_root") or "—"
                card = widgets.Card(baslik)
                satirlar = [
                    (t("label_type", lang), t("type_ssh_file_folder", lang)),
                    (t("label_target", lang), veri.get("host") or "—"),
                    (t("label_progress", lang), t("progress_files", lang, completed=completed, total=total)),
                    (t("label_started", lang), veri.get("started_at_utc") or "—"),
                ]
                devam_metni = t("incomplete_resume_hint_tree", lang)
            else:
                baslik = veri.get("label") or "—"
                card = widgets.Card(baslik)
                kind_map = {"ram_process": t("type_ram_process", lang), "ram_full": t("type_ram_full", lang)}
                kind_adi = kind_map.get(veri.get("kind"), veri.get("kind") or "—")
                satirlar = [
                    (t("label_type", lang), kind_adi),
                    (t("label_started", lang), veri.get("started_at_utc") or "—"),
                ]
                devam_metni = t("incomplete_resume_hint_ram", lang)

            for etiket, deger in satirlar:
                row = QHBoxLayout()
                lbl = QLabel(f"{etiket}:")
                lbl.setFixedWidth(120)
                lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
                row.addWidget(lbl)
                val = QLabel(str(deger))
                val.setWordWrap(True)
                val.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
                row.addWidget(val, stretch=1)
                card.body.addLayout(row)

            hint = QLabel(devam_metni)
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style:italic;")
            card.body.addWidget(hint)

            footer = QHBoxLayout()
            footer.addStretch()
            if kind in ("ssh_disk", "ssh_tree"):
                goto_btn = widgets.SecondaryButton(t("btn_goto_ssh_screen", lang))
                goto_btn.clicked.connect(self._show_home)
            else:
                details = veri.get("details", {})
                case_prefill = {
                    "case_id": details.get("case_id", ""), "examiner": details.get("examiner", ""),
                    "custodian": details.get("custodian", ""), "organization": details.get("organization", ""),
                }
                goto_btn = widgets.SecondaryButton(t("btn_reopen_ram_screen", lang))
                goto_btn.clicked.connect(lambda _checked=False, c=case_prefill: self._open_ram_engine(c))
            footer.addWidget(goto_btn)
            card.body.addLayout(footer)

            body.addWidget(card)

        body.addStretch()

    def _export_case_history_csv(self, entries):
        lang = self.lang
        default_name = t("csv_save_default_name", lang)
        path, _ = QFileDialog.getSaveFileName(
            self, t("csv_save_dialog_title", lang),
            default_name, "CSV (*.csv)",
        )
        if not path:
            return

        columns = [
            "case_id", "examiner", "custodian", "organization", "engine", "method", "target_os",
            "target_host", "source_identifier", "connection_method", "status",
            "start_time_utc", "end_time_utc", "report_path",
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                for entry in entries:
                    writer.writerow(entry)
        except OSError as exc:
            self._history_status.setText(t("csv_write_error", lang, exc=exc))
            return

        self._history_status.setText(t("csv_saved", lang, path=path))

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
            on_back=self._show_home, on_show_help=self._show_help_from_tool,
            initial_case_id=case.get("case_id", ""), initial_examiner=case.get("examiner", ""),
            initial_custodian=case.get("custodian", ""), initial_organization=case.get("organization", ""),
            initial_connection_method=connection_method, display_timezone=self.display_timezone,
        )
        page_layout.addWidget(ssh_widget)
        self._active_tool_widget = page
        self._active_tool_kind = "ssh"

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
            on_back=self._show_home, on_show_help=self._show_help_from_tool,
            initial_case_id=case.get("case_id", ""), initial_examiner=case.get("examiner", ""),
            initial_custodian=case.get("custodian", ""), initial_organization=case.get("organization", ""),
            display_timezone=self.display_timezone,
        )
        page_layout.addWidget(ram_widget)
        self._active_tool_widget = page
        self._active_tool_kind = "ram"

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


def main():
    app = QApplication([])
    fonts.register_fonts()
    app.setStyleSheet(ui.base_stylesheet())

    window = ChameleonWindow()

    def _start_main():
        window.resize(1100, 720)
        window.show()

    splash, _kept_alive = show_splash(_start_main)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
