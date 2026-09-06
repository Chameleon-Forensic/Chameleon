# Yasal ve Etik Kullanım

Bu proje, adli bilişim (digital forensics) ve olay müdahale (incident response)
eğitimi/uygulaması amacıyla hazırlanmış bir **fiziksel bellek görüntüleme** aracıdır.
FTK Imager, WinPmem, Magnet RAM Capture gibi ticari/açık kaynak araçlarla aynı
teknik prensipleri (kernel sürücü + `MmCopyMemory`) kullanır.

## Kullanım koşulları

- Yalnızca **üzerinde açık, yazılı yetkiniz olan** sistemlerde kullanın (kendi
  test makineniz, laboratuvar ortamınız veya müşterinizin yetki verdiği bir
  olay müdahale görevi).
- Kurumsal ortamlarda kullanmadan önce BT güvenlik ve hukuk birimlerinden onay alın.
- Yakalanan RAM görüntüsü; parolalar, şifreleme anahtarları, kişisel veriler gibi
  son derece hassas bilgiler içerebilir. Görüntüleri şifreli depolama alanlarında
  saklayın, erişimi sınırlayın ve chain-of-custody (delil zinciri) kayıtlarını tutun.
- Bu aracı başkasına ait bir sisteme yetkisiz erişim, casusluk veya veri hırsızlığı
  amacıyla **kullanmayın**. Bu tür kullanım, bulunduğunuz ülkenin bilişim suçları
  mevzuatına (örn. TCK md. 243-244, CFAA, Computer Misuse Act vb.) aykırıdır.
- Sürücü, yalnızca SYSTEM ve yerel Administrators grubu tarafından açılabilecek
  şekilde kısıtlanmıştır (bkz. `driver/src/driver.c`), ancak bu, aracın yetkisiz
  ortamlarda kullanılmasını meşrulaştırmaz.

## Sorumluluk reddi

Bu kod "olduğu gibi" sağlanmıştır. Yazarlar, aracın kötüye kullanımından doğacak
hiçbir zarardan sorumlu tutulamaz. Üretim/gerçek delil toplama senaryolarında
kullanmadan önce kendi ortamınızda doğrulama (validation) ve hash tabanlı
bütünlük testleri yapın.
