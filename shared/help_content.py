"""
help_content.py
Uygulama icindeki "Bilgi Merkezi" sayfasinin (launcher/chameleon_gui.py)
ve arac ekranlarindaki ("Bu ne demek?" linkleri, gui_v2.py) AYNI kaynaktan
okudugu konu anlatimlari. Icerik burada TEK yerde tutulur ki iki yerde
ayni metnin farkli kopyalari birbirinden kopmasin.

Yeni bir konu eklemek icin HELP_TOPICS listesine {"key", "title", "body"}
seklinde bir sozluk eklemek yeterli -- hem Bilgi Merkezi hem de o konuyu
gosteren herhangi bir "Bu ne demek?" linki otomatik olarak kullanir.
"""

HELP_TOPICS = [
    {
        "key": "host_key_verification",
        "title": "Sunucu Kimlik Doğrulama (Host Key) Nedir?",
        "body": (
            "SSH ile bağlandığınızda sunucu size kendini tanıtan bir dijital kimlik "
            "(host key) sunar -- bu her bağlantıda otomatik olur, sizin/bizim "
            "müdahale ettiğimiz bir şey değildir.\n\n"
            "Bu sunucuya bilgisayarınızdan daha önce hiç bağlanılmadıysa, bu kimliğin "
            "gerçekten hedeflediğiniz cihaza mı yoksa ağ üzerinde onun yerine cevap "
            "veren başka bir cihaza mı ait olduğu tek başına bilinemez. Kullanıcı "
            "adı/şifrenin doğru olması sadece o cihaza giriş yapma yetkiniz "
            "olduğunu gösterir, karşıdaki cihazın kimliğini değil.\n\n"
            "Alınan verinin bütünlüğü ayrıca hash karşılaştırmasıyla da kontrol "
            "edilir, ama bu farklı bir şeyi kanıtlar: verinin aktarım sırasında "
            "bozulmadığını -- hangi cihazdan geldiğini değil. Bu yüzden iki kontrol "
            "birbirinin yerine geçmez (bkz. \"Hash / Bütünlük Doğrulaması Nedir?\").\n\n"
            "\"Sıkı doğrula\" seçiliyken, kimliği önceden doğrulanmamış bir sunucuya "
            "bağlanmak reddedilir. \"Doğrulamayı atla\" seçildiğinde (örn. şahsa "
            "ait, ilk kez bağlanılan bir cihazda) kontrol tamamen KAPANMAZ: "
            "Chameleon, ilk bağlantıda sunucunun kimliğini kendi kaydına alır; "
            "aynı cihaza tekrar bağlandığınızda bu kayıtla karşılaştırır. Kayıtla "
            "eşleşmeyen bir kimlik gelirse (sunucu değişmiş ya da araya biri "
            "girmiş olabilir) bağlantı yine reddedilir -- \"atla\" sadece İLK "
            "bağlantıdaki bilinmezliği kabul eder, sonrasında tutarlılığı takip "
            "etmeye devam eder. Bu tercih delil zincirine ayrıca kaydedilir; "
            "böylece ileride \"bu görüntünün gerçekten o cihazdan alındığı nasıl "
            "biliniyor?\" sorusuna, hangi kontrollerin yapıldığı açıkça gösterilerek cevap "
            "verilebilir."
        ),
    },
    {
        "key": "live_vs_offline_acquisition",
        "title": "Live ve Offline Acquisition (Yazma Engelleme) Nedir?",
        "body": (
            "Hedef diski görüntülerken iki moddan biri seçilir:\n\n"
            "Live Acquisition: hedef disk o anda aktif kullanımdadır (örn. üzerinde "
            "çalışan, kapatılamayan bir sistem). Disk OLDUĞU GİBİ, kilitlenmeden "
            "okunur -- zaten aktif kullanımda olduğu için başka türlü bir seçenek "
            "yoktur.\n\n"
            "Offline Acquisition: disk o anda aktif kullanımda DEĞİLDİR (örn. bağlı "
            "ama kullanılmayan bir sürücü, kapatılmış bir sistemin diski). Bu modda "
            "Chameleon, imaj almadan ÖNCE diski salt-okunur (read-only) kilitler -- "
            "\"write-blocker\" denen bu adım, imaj alma işleminin KENDİSİNİN diskte "
            "hiçbir değişikliğe sebep olmadığını ispatlanabilir şekilde garanti "
            "eder.\n\n"
            "Hangi modun seçildiği ve yazma engellemenin uygulanıp uygulanmadığı, "
            "rapora ve delil zincirine otomatik olarak kaydedilir. Emin değilseniz: "
            "disk hâlâ çalışan bir sistemin parçasıysa Live, değilse Offline "
            "seçilmelidir -- Offline, ekstra bir bütünlük garantisi sağladığı için "
            "mümkün olduğunda tercih edilir.\n\n"
            "Live Acquisition'ın bir sınırı var: diskin blokları TEK SEFERDE "
            "değil, sırayla (bir süreye yayılarak) okunur. Disk bu süre boyunca "
            "aktif kullanımda olduğu için, imajın farklı kısımları diskin farklı "
            "ANLARINA ait olabilir -- yani tek bir dondurulmuş kareye değil, "
            "alma süresince değişmiş olabilecek bir duruma karşılık gelir. Bu, "
            "anlık bir kopya (snapshot) alan araçların önlediği, ama Live modun "
            "doğası gereği önleyemediği bir durumdur."
        ),
    },
    {
        "key": "chain_of_custody",
        "title": "Delil Zinciri (Chain of Custody) Nedir?",
        "body": (
            "Delil zinciri, bir dijital delilin ele geçirildiği andan rapora/"
            "mahkemeye sunulana kadar kimin, ne zaman, hangi işlemi yaptığının "
            "kesintisiz kaydıdır. Amacı, ileride \"bu delil değiştirilmiş olabilir "
            "mi, kim müdahale etti?\" sorusuna net cevap verebilmektir.\n\n"
            "Chameleon, imaj alma sırasında yaptığı HER işlemi (bağlantı kuruldu, "
            "disk kilitlendi/kilitlenmedi, hangi blok alındı, hash doğrulandı, "
            "bağlantı koptu/devam edildi, hangi ağ yöntemi kullanıldı vb.) otomatik "
            "olarak zaman damgasıyla bir log dosyasına yazar. Bu log, işlem bitince "
            "oluşturulan rapora dahil edilir.\n\n"
            "Bazı adımlarda sizin yaptığınız bir TERCİH de bu zincire kaydedilir "
            "(örn. sunucu kimlik doğrulamasının atlanması, VPN/Tor kullanımı). Bu, "
            "\"gizli/yanlış bir şey yapıldı\" anlamına gelmez -- tam tersine, hangi "
            "güvenlik kontrollerinin o alma işleminde aktif olup olmadığının "
            "şeffaf bir kaydıdır."
        ),
    },
    {
        "key": "hash_verification",
        "title": "Hash / Bütünlük Doğrulaması Nedir?",
        "body": (
            "Hash, bir verinin (dosya, disk bloğu) içeriğinden matematiksel olarak "
            "üretilen, o veriye özgü kısa bir \"parmak izi\"dir (Chameleon SHA-256 "
            "kullanır). Verinin tek bir baytı bile değişse, hash tamamen farklı "
            "çıkar.\n\n"
            "Chameleon, aldığı her parçanın hash'ini hem hedef cihazda hem kendi "
            "bilgisayarınızda ayrı ayrı hesaplar ve karşılaştırır. İkisi "
            "eşleşiyorsa, verinin aktarım sırasında bozulmadan/değişmeden geldiği "
            "kanıtlanmış olur. İmaj tamamlanınca bütün dosyanın hash'i de "
            "hesaplanıp rapora yazılır -- ileride birinin \"bu imaj dosyası "
            "orijinal alınan veriyle aynı mı?\" sorusunu, imajı yeniden hesaplayıp "
            "rapordaki hash'le karşılaştırarak objektif şekilde cevaplamasını "
            "sağlar.\n\n"
            "Not: hash, verinin aktarım sırasında bozulup bozulmadığını kanıtlar -- "
            "verinin gerçekten hangi cihazdan geldiğini değil (bkz. \"Sunucu Kimlik "
            "Doğrulama\")."
        ),
    },
    {
        "key": "ram_full_mode_driver",
        "title": "RAM 'Full' Modu: Yönetici, Sürücü ve Secure Boot Ne Demek?",
        "body": (
            "RAM İmajı Al ekranında iki mod vardır:\n\n"
            "Process Dump: sadece TEK BİR programın o anki bellek kullanımını "
            "alır. Yönetici yetkisi gerekmez, hızlıdır.\n\n"
            "Full: bilgisayarın TÜM sistem belleğini alır -- açık tüm programların "
            "ve işletim sisteminin o anki tam görüntüsü. Bunun için Windows'un "
            "normalde izin vermediği düşük seviyeli bir erişim gerekir; bu erişimi "
            "sağlayan küçük yazılım parçasına \"sürücü\" (driver) denir.\n\n"
            "Windows, güvenlik için resmi olarak imzalanmamış (test amaçlı) "
            "sürücülerin yüklenmesini varsayılan olarak engeller. \"Test-signing\" "
            "bu engeli açan bir Windows ayarıdır -- açıldığında bilgisayar bunu "
            "ekranda bir filigranla gösterir. Bu ayar, bilgisayarın başka bir "
            "güvenlik özelliği olan \"Secure Boot\"un (açılış sırasında sadece "
            "güvenilir/imzalı yazılımların çalışmasını sağlayan koruma) "
            "kapatılmasını gerektirebilir.\n\n"
            "Bu yüzden Full mod, inceleyeceğiniz bilgisayarda DEĞİL, KENDİ "
            "makinenizde önceden hazırlanmalıdır -- rastgele bir hedef cihazda bu "
            "ayarları değiştirmek pratikte çoğu zaman mümkün olmaz ve delil "
            "bütünlüğünü riske atar."
        ),
    },
    {
        "key": "tor_onion_operator_key",
        "title": "Tor, .onion Adresi ve Operatör Anahtarı Nasıl Çalışır?",
        "body": (
            "Tor, internet trafiğini tek bir doğrudan bağlantı yerine, dünya "
            "genelinde gönüllülerin çalıştırdığı birden fazla sunucu (röle) "
            "üzerinden şifreli katmanlar hâlinde yönlendiren bir ağdır -- bu "
            "sayede trafiğin nereden nereye gittiği ağ üzerinde izlenemez. Bedeli: "
            "birden fazla sunucudan geçtiği için gecikme yüksek, hız düşüktür.\n\n"
            "\".onion\" adresi normal bir internet adresi (IP/alan adı) DEĞİLDİR -- "
            "sadece Tor ağı içinde anlam ifade eden, dışarıdan bulunamayan bir "
            "adrestir. Taşınabilir kit hedef cihazda çalıştırıldığında bu adresi "
            "kendiliğinden üretir; hiçbir merkezi sunucuya kayıt yapılmaz, adres "
            "SADECE o kit çalıştığı sürece var olur.\n\n"
            "Operatör anahtarı, bu .onion adresine sadece SİZİN bağlanabilmenizi "
            "sağlayan bir kimlik doğrulama anahtarıdır. Adresi ele geçiren biri "
            "bile bu anahtar olmadan bağlanamaz -- yani güvenlik \"adres gizli "
            "kalsın\" değil, \"adres bilinse bile anahtarsız işe yaramasın\" "
            "prensibine dayanır. Bu yüzden operatör anahtarınızı saha "
            "ziyaretinden ÖNCE, kiti hazırlayacak/götürecek kişiye güvenli bir "
            "şekilde iletmeniz gerekir."
        ),
    },
]


def get_topic(key):
    """key'e karsilik gelen konuyu doner; yoksa None."""
    for topic in HELP_TOPICS:
        if topic["key"] == key:
            return topic
    return None
