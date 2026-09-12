"""
strings.py
Chameleon launcher'i (launcher/chameleon_gui.py) icin merkezi dil tablosu.
Motorlerin (ssh_engine, ram_engine) kendi ic arayuz metinleri HENUZ buna
bagli degil -- bilincli bir kapsam siniri (bkz. CLAUDE.md).

Onceden launcher'daki her metin ayri ayri `"..." if lang == "tr" else "..."`
seklinde SATIR ICINDE yaziliyordu (69 ayri yerde) -- yeni bir dil eklemek
her seferinde TUM dosyayi taramayi gerektiriyordu. Bu modul, TUM metinleri
tek bir STRINGS sozlugunde, anahtar bazinda topluyor; chameleon_gui.py
artik SADECE t("anahtar", lang) cagiriyor. Tekrarlanan kisa etiketler
(orn. "Hedef"/"Target", "Basladi"/"Started") BIRLESIK anahtarlar altinda
tutuluyor -- ayni etiket 3 farkli yerde ayri ayri cevrilmiyor.

Desteklenen diller: tr, en, es, de, pt, fr. Terminoloji (ozellikle "chain
of custody"/"write-blocker"/"hash dogrulama" gibi adli bilisim terimleri)
gercek adli bilisim yazilimlarindan/resmi terminoloji kaynaklarindan
dogrulanarak secildi (bkz. docs/oturum_ozeti.md):
  - Ispanyolca: "cadena de custodia" (INTERPOL/adli bilisim literaturu)
  - Almanca: "Beweismittelkette"/"Kette der Verwahrung" (BSI/adli bilisim)
  - Portekizce (BR): "cadeia de custodia" (POP de Informatica Forense)
  - Fransizca: "chaine de possession" (OQLF/GDT resmi terminoloji)
"""

STRINGS = {
    "tr": {
        # -- Genel --
        "title": "Chameleon",
        "subtitle": "Digital Forensics Acquisition Engine",
        "choose_language": "Dil",
        "choose_engine": "Yöntem seç",
        "ssh_engine": "SSH ile uzak imaj al",
        "ssh_engine_desc": "Linux veya Windows hedefe SSH ile bağlanıp disk/dosya imajı alır",
        "ram_engine": "RAM imajı al (Windows, yerel)",
        "ram_engine_desc": "Bu makinede çalışır, uzak bağlantı gerekmez",
        "launched": "açıldı.",
        "error_launch": "Başlatılamadı, dosya bulunamadı mı diye kontrol et:",
        "missing_file": "Bu dosya olması gereken yerde değil:",

        # -- Sidebar / nav --
        "nav_home": "Ana Sayfa",
        "nav_direct": "Doğrudan / Port Yönlendirme",
        "nav_vpn": "VPN",
        "nav_tor": "Tor (Acil Durum)",
        "nav_ram": "RAM İmajı Al",
        "nav_history": "Vaka Geçmişi",
        "nav_incomplete": "Yarım Kalanlar",
        "nav_help": "Bilgi Merkezi",
        "nav_settings": "Ayarlar",

        "home_intro": "Bir yöntem seçin -- her birinin ne yaptığını ve nasıl kullanılacağını açan sayfada görebilirsiniz.",
        "home_recent_case_title": "Son Vaka",
        "btn_view_all_cases": "Tüm Vakaları Gör",

        # -- Yontem tanitim sayfasi (_show_method_detail) --
        "method_when_heading": "Ne zaman kullanılır?",
        "method_requires_heading": "Gerekenler (sırasıyla)",
        "method_steps_heading": "Adım adım kullanım",
        "btn_start": "Başlat",
        "btn_open": "Aç",

        # -- Vaka Bilgileri on-ekrani --
        "case_info_title": "Vaka Bilgileri",
        "case_info_note": "(İsteğe bağlı -- rapor üretmiyorsanız boş bırakabilirsiniz)",
        "field_case_id": "Vaka No",
        "field_examiner": "İnceleyen",
        "field_custodian": "Cihaz Sahibi / Yetkili Kişi",
        "field_organization": "Organizasyon",
        "btn_continue": "Devam Et",

        # -- Bilgi Merkezi --
        "help_back_to_tool": "← Kaldığınız yere dön",
        "help_center_title": "Bilgi Merkezi",
        "help_center_intro": "Uygulama içindeki bazı seçeneklerin ne işe yaradığı ve neden var olduğu burada daha ayrıntılı anlatılır.",
        "what_does_this_mean_titled": "Bu ne demek? ({title})",
        "btn_read_in_help_center": "Bu ne demek? (Bilgi Merkezi'nde oku)",

        # -- Ayarlar --
        "settings_title": "Ayarlar",
        "settings_language_card": "Dil",
        "settings_theme_card": "Tema",
        "theme_dark": "Koyu",
        "theme_light": "Açık",
        "settings_timezone_card": "Saat Dilimi (Görüntüleme)",
        "settings_timezone_note": (
            "Raporlardaki UTC zaman damgalarının yanına, sadece okunabilirlik için yerel saat "
            "karşılığı eklenir -- delil olarak geçerli olan değer her zaman UTC'dir, bu seçim "
            "report.json'un kendisini etkilemez."
        ),
        "settings_timezone_row_label": "Saat Dilimi:",
        "settings_timezone_utc_option": "UTC (yerel karşılık gösterilmez)",

        # -- Vaka Gecmisi --
        "case_history_title": "Vaka Geçmişi",
        "case_history_load_error": "Vaka geçmişi yüklenemedi: {exc}",
        "case_history_export_csv": "CSV Olarak Dışa Aktar",
        "case_history_search_placeholder": "Vaka no, inceleyen, hedef... ile filtrele",
        "case_history_tag_label": "Etiket",
        "case_history_tag_placeholder": "Etiket ekle (örn. takip gerekiyor)",
        "case_history_group_count": "{count} kayıt",
        "btn_export_pdf": "PDF Olarak Kaydet",
        "pdf_save_dialog_title": "PDF Olarak Kaydet",
        "pdf_export_error": "PDF oluşturulamadı: {exc}",
        "pdf_export_success": "PDF kaydedildi: {path}",
        "case_history_empty": "Henüz kayıtlı bir vaka yok -- bir imaj alma işlemi tamamlandığında burada görünecek.",
        "engine_ssh": "SSH Motoru",
        "engine_ram": "RAM Motoru",
        "case_history_no_case_id": "Vaka No Girilmedi",
        "label_engine": "Motor",
        "label_target": "Hedef",
        "label_custodian": "Yetkili Kişi",
        "label_examiner": "İnceleyen",
        "label_organization": "Organizasyon",
        "label_date": "Tarih",
        "btn_open_report": "Raporu Aç",
        "csv_save_default_name": "vaka_gecmisi.csv",
        "csv_save_dialog_title": "CSV Olarak Kaydet",
        "csv_write_error": "CSV yazılamadı: {exc}",
        "csv_saved": "CSV kaydedildi: {path}",

        # -- Yarim Kalanlar --
        "incomplete_title": "Yarım Kalanlar",
        "incomplete_intro": "Bağlantı koptuğu ya da uygulama kapandığı için yarım kalmış işlemler burada listelenir.",
        "incomplete_empty": "Yarım kalmış bir işlem yok.",
        "label_type": "Tür",
        "label_progress": "İlerleme",
        "label_started": "Başladı",
        "type_ssh_full_disk": "SSH Tam Disk",
        "type_ssh_file_folder": "SSH Dosya/Klasör",
        "type_ram_process": "RAM (Process Dump)",
        "type_ram_full": "RAM (Tam Bellek)",
        "progress_blocks": "{completed}/{total} blok",
        "progress_files": "{completed}/{total} dosya",
        "incomplete_resume_hint_disk": (
            "Devam etmek için ilgili bağlantı ekranına gidip aynı hedefe/diske bağlanın -- "
            "kaldığı yerden devam etmek isteyip istemediğiniz sorulacak."
        ),
        "incomplete_resume_hint_tree": (
            "Devam etmek için ilgili bağlantı ekranına gidip aynı hedefe/dosyaya bağlanın -- "
            "kaldığı yerden devam etmek isteyip istemediğiniz sorulacak."
        ),
        "incomplete_resume_hint_ram": (
            "Gerçek bir devam etme (resume) mümkün değil -- RAM anlık görüntüsü tek seferliktir. "
            "Aşağıdaki buton RAM ekranını, aynı vaka bilgileriyle yeniden başlatmak için açar."
        ),
        "btn_goto_ssh_screen": "Doğrudan/VPN/Tor Ekranına Git",
        "btn_reopen_ram_screen": "RAM Ekranını Yeniden Aç",
    },
    "en": {
        "title": "Chameleon",
        "subtitle": "Digital Forensics Acquisition Engine",
        "choose_language": "Language",
        "choose_engine": "Choose method",
        "ssh_engine": "Remote image over SSH",
        "ssh_engine_desc": "Connects to a Linux or Windows target over SSH, images disk/files",
        "ram_engine": "RAM image (Windows, local)",
        "ram_engine_desc": "Runs on this machine, no remote connection needed",
        "launched": "started.",
        "error_launch": "Couldn't start it, check if the file is missing:",
        "missing_file": "This file isn't where it should be:",

        "nav_home": "Home",
        "nav_direct": "Direct / Port Forward",
        "nav_vpn": "VPN",
        "nav_tor": "Tor (Emergency)",
        "nav_ram": "RAM Image",
        "nav_history": "Case History",
        "nav_incomplete": "Unfinished",
        "nav_help": "Help Center",
        "nav_settings": "Settings",

        "home_intro": "Choose a method -- the page for each explains what it does and how to use it.",
        "home_recent_case_title": "Most Recent Case",
        "btn_view_all_cases": "View All Cases",

        "method_when_heading": "When to use it?",
        "method_requires_heading": "Requirements (in order)",
        "method_steps_heading": "Step by step",
        "btn_start": "Start",
        "btn_open": "Open",

        "case_info_title": "Case Information",
        "case_info_note": "(Optional -- leave blank if you're not producing a report)",
        "field_case_id": "Case No",
        "field_examiner": "Examiner",
        "field_custodian": "Device Owner / Custodian",
        "field_organization": "Organization",
        "btn_continue": "Continue",

        "help_back_to_tool": "← Back to where you were",
        "help_center_title": "Help Center",
        "help_center_intro": "Detailed explanations for some of the choices in the app live here.",
        "what_does_this_mean_titled": "What does this mean? ({title})",
        "btn_read_in_help_center": "What does this mean? (read in Help Center)",

        "settings_title": "Settings",
        "settings_language_card": "Language",
        "settings_theme_card": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "settings_timezone_card": "Time Zone (Display)",
        "settings_timezone_note": (
            "A local-time equivalent is added next to the UTC timestamps in reports, for "
            "readability only -- the value that counts as evidence is always UTC, this choice "
            "never affects report.json itself."
        ),
        "settings_timezone_row_label": "Time Zone:",
        "settings_timezone_utc_option": "UTC (no local equivalent shown)",

        "case_history_title": "Case History",
        "case_history_load_error": "Could not load case history: {exc}",
        "case_history_export_csv": "Export as CSV",
        "case_history_search_placeholder": "Filter by case no, examiner, target...",
        "case_history_tag_label": "Tag",
        "case_history_tag_placeholder": "Add a tag (e.g. needs follow-up)",
        "case_history_group_count": "{count} records",
        "btn_export_pdf": "Save as PDF",
        "pdf_save_dialog_title": "Save as PDF",
        "pdf_export_error": "Could not create PDF: {exc}",
        "pdf_export_success": "PDF saved: {path}",
        "case_history_empty": "No cases recorded yet -- one will appear here once an acquisition completes.",
        "engine_ssh": "SSH Engine",
        "engine_ram": "RAM Engine",
        "case_history_no_case_id": "No Case ID",
        "label_engine": "Engine",
        "label_target": "Target",
        "label_custodian": "Custodian",
        "label_examiner": "Examiner",
        "label_organization": "Organization",
        "label_date": "Date",
        "btn_open_report": "Open Report",
        "csv_save_default_name": "case_history.csv",
        "csv_save_dialog_title": "Save as CSV",
        "csv_write_error": "Could not write CSV: {exc}",
        "csv_saved": "CSV saved: {path}",

        "incomplete_title": "Unfinished Operations",
        "incomplete_intro": "Operations left unfinished because a connection dropped or the app closed are listed here.",
        "incomplete_empty": "No unfinished operations.",
        "label_type": "Type",
        "label_progress": "Progress",
        "label_started": "Started",
        "type_ssh_full_disk": "SSH Full Disk",
        "type_ssh_file_folder": "SSH File/Folder",
        "type_ram_process": "RAM (Process Dump)",
        "type_ram_full": "RAM (Full Memory)",
        "progress_blocks": "{completed}/{total} blocks",
        "progress_files": "{completed}/{total} files",
        "incomplete_resume_hint_disk": (
            "To continue, go to the connection screen and connect to the same target/disk again -- "
            "you'll be asked whether to resume."
        ),
        "incomplete_resume_hint_tree": (
            "To continue, go to the connection screen and connect to the same target/path again -- "
            "you'll be asked whether to resume."
        ),
        "incomplete_resume_hint_ram": (
            "A real resume isn't possible -- a RAM snapshot is a one-shot operation. The button "
            "below reopens the RAM screen with the same case info to start over."
        ),
        "btn_goto_ssh_screen": "Go to Direct/VPN/Tor Screen",
        "btn_reopen_ram_screen": "Reopen RAM Screen",
    },
    "es": {
        "title": "Chameleon",
        "subtitle": "Motor de Adquisición Forense Digital",
        "choose_language": "Idioma",
        "choose_engine": "Elegir método",
        "ssh_engine": "Imagen remota por SSH",
        "ssh_engine_desc": "Se conecta a un destino Linux o Windows por SSH y crea una imagen de disco/archivos",
        "ram_engine": "Imagen de RAM (Windows, local)",
        "ram_engine_desc": "Se ejecuta en este equipo, no requiere conexión remota",
        "launched": "iniciado.",
        "error_launch": "No se pudo iniciar, comprueba si falta el archivo:",
        "missing_file": "Este archivo no está donde debería estar:",

        "nav_home": "Inicio",
        "nav_direct": "Directo / Redirección de Puerto",
        "nav_vpn": "VPN",
        "nav_tor": "Tor (Emergencia)",
        "nav_ram": "Imagen de RAM",
        "nav_history": "Historial de Casos",
        "nav_incomplete": "Inconclusos",
        "nav_help": "Centro de Ayuda",
        "nav_settings": "Configuración",

        "home_intro": "Elija un método -- la página de cada uno explica qué hace y cómo usarlo.",
        "home_recent_case_title": "Caso Más Reciente",
        "btn_view_all_cases": "Ver Todos los Casos",

        "method_when_heading": "¿Cuándo usarlo?",
        "method_requires_heading": "Requisitos (en orden)",
        "method_steps_heading": "Paso a paso",
        "btn_start": "Iniciar",
        "btn_open": "Abrir",

        "case_info_title": "Información del Caso",
        "case_info_note": "(Opcional -- déjelo en blanco si no va a generar un informe)",
        "field_case_id": "N.º de Caso",
        "field_examiner": "Examinador",
        "field_custodian": "Propietario del Dispositivo / Custodio",
        "field_organization": "Organización",
        "btn_continue": "Continuar",

        "help_back_to_tool": "← Volver a donde estaba",
        "help_center_title": "Centro de Ayuda",
        "help_center_intro": "Aquí se explican en más detalle algunas de las opciones de la aplicación y por qué existen.",
        "what_does_this_mean_titled": "¿Qué significa esto? ({title})",
        "btn_read_in_help_center": "¿Qué significa esto? (leer en el Centro de Ayuda)",

        "settings_title": "Configuración",
        "settings_language_card": "Idioma",
        "settings_theme_card": "Tema",
        "theme_dark": "Oscuro",
        "theme_light": "Claro",
        "settings_timezone_card": "Zona Horaria (Visualización)",
        "settings_timezone_note": (
            "Se añade un equivalente en hora local junto a las marcas de tiempo UTC de los "
            "informes, solo por legibilidad -- el valor que cuenta como evidencia es siempre "
            "UTC, esta elección nunca afecta al report.json en sí."
        ),
        "settings_timezone_row_label": "Zona Horaria:",
        "settings_timezone_utc_option": "UTC (sin equivalente local)",

        "case_history_title": "Historial de Casos",
        "case_history_load_error": "No se pudo cargar el historial de casos: {exc}",
        "case_history_export_csv": "Exportar como CSV",
        "case_history_search_placeholder": "Filtrar por N.º de caso, examinador, destino...",
        "case_history_tag_label": "Etiqueta",
        "case_history_tag_placeholder": "Añadir una etiqueta (p. ej. requiere seguimiento)",
        "case_history_group_count": "{count} registros",
        "btn_export_pdf": "Guardar como PDF",
        "pdf_save_dialog_title": "Guardar como PDF",
        "pdf_export_error": "No se pudo crear el PDF: {exc}",
        "pdf_export_success": "PDF guardado: {path}",
        "case_history_empty": "Aún no hay casos registrados -- aparecerán aquí al completarse una adquisición.",
        "engine_ssh": "Motor SSH",
        "engine_ram": "Motor RAM",
        "case_history_no_case_id": "Sin N.º de Caso",
        "label_engine": "Motor",
        "label_target": "Destino",
        "label_custodian": "Custodio",
        "label_examiner": "Examinador",
        "label_organization": "Organización",
        "label_date": "Fecha",
        "btn_open_report": "Abrir Informe",
        "csv_save_default_name": "historial_de_casos.csv",
        "csv_save_dialog_title": "Guardar como CSV",
        "csv_write_error": "No se pudo escribir el CSV: {exc}",
        "csv_saved": "CSV guardado: {path}",

        "incomplete_title": "Operaciones Inconclusas",
        "incomplete_intro": "Aquí se listan las operaciones que quedaron inconclusas porque se perdió la conexión o se cerró la aplicación.",
        "incomplete_empty": "No hay operaciones inconclusas.",
        "label_type": "Tipo",
        "label_progress": "Progreso",
        "label_started": "Iniciado",
        "type_ssh_full_disk": "SSH Disco Completo",
        "type_ssh_file_folder": "SSH Archivo/Carpeta",
        "type_ram_process": "RAM (Volcado de Proceso)",
        "type_ram_full": "RAM (Memoria Completa)",
        "progress_blocks": "{completed}/{total} bloques",
        "progress_files": "{completed}/{total} archivos",
        "incomplete_resume_hint_disk": (
            "Para continuar, vaya a la pantalla de conexión y conéctese de nuevo al mismo "
            "destino/disco -- se le preguntará si desea reanudar."
        ),
        "incomplete_resume_hint_tree": (
            "Para continuar, vaya a la pantalla de conexión y conéctese de nuevo a la misma "
            "ruta/destino -- se le preguntará si desea reanudar."
        ),
        "incomplete_resume_hint_ram": (
            "No es posible una reanudación real -- una instantánea de RAM es una operación de "
            "una sola vez. El botón de abajo vuelve a abrir la pantalla de RAM con la misma "
            "información del caso para empezar de nuevo."
        ),
        "btn_goto_ssh_screen": "Ir a Pantalla Directo/VPN/Tor",
        "btn_reopen_ram_screen": "Reabrir Pantalla de RAM",
    },
    "de": {
        "title": "Chameleon",
        "subtitle": "Digital-Forensik-Erfassungswerkzeug",
        "choose_language": "Sprache",
        "choose_engine": "Methode wählen",
        "ssh_engine": "Remote-Image über SSH",
        "ssh_engine_desc": "Verbindet sich per SSH mit einem Linux- oder Windows-Ziel und erstellt ein Disk-/Datei-Image",
        "ram_engine": "RAM-Image (Windows, lokal)",
        "ram_engine_desc": "Läuft auf diesem Rechner, keine Remote-Verbindung nötig",
        "launched": "gestartet.",
        "error_launch": "Konnte nicht gestartet werden, prüfen Sie, ob die Datei fehlt:",
        "missing_file": "Diese Datei befindet sich nicht am erwarteten Ort:",

        "nav_home": "Startseite",
        "nav_direct": "Direkt / Portweiterleitung",
        "nav_vpn": "VPN",
        "nav_tor": "Tor (Notfall)",
        "nav_ram": "RAM-Image",
        "nav_history": "Fallverlauf",
        "nav_incomplete": "Unvollständig",
        "nav_help": "Infocenter",
        "nav_settings": "Einstellungen",

        "home_intro": "Wählen Sie eine Methode -- die jeweilige Seite erklärt, was sie tut und wie man sie verwendet.",
        "home_recent_case_title": "Zuletzt Bearbeiteter Fall",
        "btn_view_all_cases": "Alle Fälle Anzeigen",

        "method_when_heading": "Wann wird es verwendet?",
        "method_requires_heading": "Voraussetzungen (in Reihenfolge)",
        "method_steps_heading": "Schritt für Schritt",
        "btn_start": "Starten",
        "btn_open": "Öffnen",

        "case_info_title": "Fallinformationen",
        "case_info_note": "(Optional -- leer lassen, wenn Sie keinen Bericht erstellen)",
        "field_case_id": "Fallnummer",
        "field_examiner": "Ermittler",
        "field_custodian": "Geräteeigentümer / Verwahrer",
        "field_organization": "Organisation",
        "btn_continue": "Weiter",

        "help_back_to_tool": "← Zurück zur vorherigen Ansicht",
        "help_center_title": "Infocenter",
        "help_center_intro": "Hier werden einige der Optionen in der Anwendung genauer erklärt -- was sie bewirken und warum es sie gibt.",
        "what_does_this_mean_titled": "Was bedeutet das? ({title})",
        "btn_read_in_help_center": "Was bedeutet das? (im Infocenter lesen)",

        "settings_title": "Einstellungen",
        "settings_language_card": "Sprache",
        "settings_theme_card": "Design",
        "theme_dark": "Dunkel",
        "theme_light": "Hell",
        "settings_timezone_card": "Zeitzone (Anzeige)",
        "settings_timezone_note": (
            "Neben den UTC-Zeitstempeln in Berichten wird nur zur besseren Lesbarkeit eine "
            "Ortszeit-Entsprechung angezeigt -- der beweisrelevante Wert ist immer UTC, diese "
            "Auswahl wirkt sich nie auf die report.json selbst aus."
        ),
        "settings_timezone_row_label": "Zeitzone:",
        "settings_timezone_utc_option": "UTC (keine Ortszeit angezeigt)",

        "case_history_title": "Fallverlauf",
        "case_history_load_error": "Fallverlauf konnte nicht geladen werden: {exc}",
        "case_history_export_csv": "Als CSV exportieren",
        "case_history_search_placeholder": "Nach Fallnummer, Ermittler, Ziel filtern...",
        "case_history_tag_label": "Tag",
        "case_history_tag_placeholder": "Tag hinzufügen (z. B. Nachverfolgung nötig)",
        "case_history_group_count": "{count} Einträge",
        "btn_export_pdf": "Als PDF speichern",
        "pdf_save_dialog_title": "Als PDF speichern",
        "pdf_export_error": "PDF konnte nicht erstellt werden: {exc}",
        "pdf_export_success": "PDF gespeichert: {path}",
        "case_history_empty": "Noch keine Fälle erfasst -- sie erscheinen hier, sobald eine Erfassung abgeschlossen ist.",
        "engine_ssh": "SSH-Engine",
        "engine_ram": "RAM-Engine",
        "case_history_no_case_id": "Keine Fallnummer",
        "label_engine": "Engine",
        "label_target": "Ziel",
        "label_custodian": "Verwahrer",
        "label_examiner": "Ermittler",
        "label_organization": "Organisation",
        "label_date": "Datum",
        "btn_open_report": "Bericht öffnen",
        "csv_save_default_name": "fallverlauf.csv",
        "csv_save_dialog_title": "Als CSV speichern",
        "csv_write_error": "CSV konnte nicht geschrieben werden: {exc}",
        "csv_saved": "CSV gespeichert: {path}",

        "incomplete_title": "Unvollständige Vorgänge",
        "incomplete_intro": "Hier werden Vorgänge aufgelistet, die durch einen Verbindungsabbruch oder das Schließen der Anwendung unvollständig blieben.",
        "incomplete_empty": "Keine unvollständigen Vorgänge.",
        "label_type": "Art",
        "label_progress": "Fortschritt",
        "label_started": "Gestartet",
        "type_ssh_full_disk": "SSH Vollständige Festplatte",
        "type_ssh_file_folder": "SSH Datei/Ordner",
        "type_ram_process": "RAM (Prozessabbild)",
        "type_ram_full": "RAM (Vollständiger Speicher)",
        "progress_blocks": "{completed}/{total} Blöcke",
        "progress_files": "{completed}/{total} Dateien",
        "incomplete_resume_hint_disk": (
            "Um fortzufahren, öffnen Sie den Verbindungsbildschirm und verbinden sich erneut "
            "mit demselben Ziel/derselben Festplatte -- Sie werden gefragt, ob fortgesetzt "
            "werden soll."
        ),
        "incomplete_resume_hint_tree": (
            "Um fortzufahren, öffnen Sie den Verbindungsbildschirm und verbinden sich erneut "
            "mit demselben Ziel/Pfad -- Sie werden gefragt, ob fortgesetzt werden soll."
        ),
        "incomplete_resume_hint_ram": (
            "Ein echtes Fortsetzen ist nicht möglich -- eine RAM-Momentaufnahme ist ein "
            "einmaliger Vorgang. Die Schaltfläche unten öffnet den RAM-Bildschirm erneut mit "
            "denselben Fallinformationen, um von vorn zu beginnen."
        ),
        "btn_goto_ssh_screen": "Zu Direkt/VPN/Tor wechseln",
        "btn_reopen_ram_screen": "RAM-Bildschirm erneut öffnen",
    },
    "pt": {
        "title": "Chameleon",
        "subtitle": "Motor de Aquisição Forense Digital",
        "choose_language": "Idioma",
        "choose_engine": "Escolher método",
        "ssh_engine": "Imagem remota via SSH",
        "ssh_engine_desc": "Conecta-se a um alvo Linux ou Windows via SSH e obtém uma imagem de disco/arquivos",
        "ram_engine": "Imagem de RAM (Windows, local)",
        "ram_engine_desc": "Executa nesta máquina, não requer conexão remota",
        "launched": "iniciado.",
        "error_launch": "Não foi possível iniciar, verifique se o arquivo está ausente:",
        "missing_file": "Este arquivo não está onde deveria estar:",

        "nav_home": "Início",
        "nav_direct": "Direto / Encaminhamento de Porta",
        "nav_vpn": "VPN",
        "nav_tor": "Tor (Emergência)",
        "nav_ram": "Imagem de RAM",
        "nav_history": "Histórico de Casos",
        "nav_incomplete": "Inconclusos",
        "nav_help": "Central de Ajuda",
        "nav_settings": "Configurações",

        "home_intro": "Escolha um método -- a página de cada um explica o que faz e como usar.",
        "home_recent_case_title": "Caso Mais Recente",
        "btn_view_all_cases": "Ver Todos os Casos",

        "method_when_heading": "Quando usar?",
        "method_requires_heading": "Requisitos (em ordem)",
        "method_steps_heading": "Passo a passo",
        "btn_start": "Iniciar",
        "btn_open": "Abrir",

        "case_info_title": "Informações do Caso",
        "case_info_note": "(Opcional -- deixe em branco se não for gerar um laudo)",
        "field_case_id": "N.º do Caso",
        "field_examiner": "Perito",
        "field_custodian": "Proprietário do Dispositivo / Custodiante",
        "field_organization": "Organização",
        "btn_continue": "Continuar",

        "help_back_to_tool": "← Voltar para onde estava",
        "help_center_title": "Central de Ajuda",
        "help_center_intro": "Aqui há explicações mais detalhadas sobre algumas das opções do aplicativo e por que elas existem.",
        "what_does_this_mean_titled": "O que isso significa? ({title})",
        "btn_read_in_help_center": "O que isso significa? (ler na Central de Ajuda)",

        "settings_title": "Configurações",
        "settings_language_card": "Idioma",
        "settings_theme_card": "Tema",
        "theme_dark": "Escuro",
        "theme_light": "Claro",
        "settings_timezone_card": "Fuso Horário (Exibição)",
        "settings_timezone_note": (
            "Um equivalente em horário local é adicionado ao lado dos registros de data/hora "
            "UTC nos laudos, apenas para legibilidade -- o valor que conta como evidência é "
            "sempre UTC, esta escolha nunca afeta o report.json em si."
        ),
        "settings_timezone_row_label": "Fuso Horário:",
        "settings_timezone_utc_option": "UTC (sem equivalente local exibido)",

        "case_history_title": "Histórico de Casos",
        "case_history_load_error": "Não foi possível carregar o histórico de casos: {exc}",
        "case_history_export_csv": "Exportar como CSV",
        "case_history_search_placeholder": "Filtrar por N.º de caso, perito, alvo...",
        "case_history_tag_label": "Etiqueta",
        "case_history_tag_placeholder": "Adicionar etiqueta (ex.: precisa de acompanhamento)",
        "case_history_group_count": "{count} registros",
        "btn_export_pdf": "Salvar como PDF",
        "pdf_save_dialog_title": "Salvar como PDF",
        "pdf_export_error": "Não foi possível criar o PDF: {exc}",
        "pdf_export_success": "PDF salvo: {path}",
        "case_history_empty": "Ainda não há casos registrados -- eles aparecerão aqui quando uma aquisição for concluída.",
        "engine_ssh": "Motor SSH",
        "engine_ram": "Motor RAM",
        "case_history_no_case_id": "Sem N.º de Caso",
        "label_engine": "Motor",
        "label_target": "Alvo",
        "label_custodian": "Custodiante",
        "label_examiner": "Perito",
        "label_organization": "Organização",
        "label_date": "Data",
        "btn_open_report": "Abrir Laudo",
        "csv_save_default_name": "historico_de_casos.csv",
        "csv_save_dialog_title": "Salvar como CSV",
        "csv_write_error": "Não foi possível gravar o CSV: {exc}",
        "csv_saved": "CSV salvo: {path}",

        "incomplete_title": "Operações Inconclusas",
        "incomplete_intro": "Operações que ficaram inconclusas porque a conexão caiu ou o aplicativo foi fechado são listadas aqui.",
        "incomplete_empty": "Não há operações inconclusas.",
        "label_type": "Tipo",
        "label_progress": "Progresso",
        "label_started": "Iniciado",
        "type_ssh_full_disk": "SSH Disco Completo",
        "type_ssh_file_folder": "SSH Arquivo/Pasta",
        "type_ram_process": "RAM (Dump de Processo)",
        "type_ram_full": "RAM (Memória Completa)",
        "progress_blocks": "{completed}/{total} blocos",
        "progress_files": "{completed}/{total} arquivos",
        "incomplete_resume_hint_disk": (
            "Para continuar, vá até a tela de conexão e conecte-se novamente ao mesmo "
            "alvo/disco -- você será perguntado se deseja retomar."
        ),
        "incomplete_resume_hint_tree": (
            "Para continuar, vá até a tela de conexão e conecte-se novamente ao mesmo "
            "alvo/caminho -- você será perguntado se deseja retomar."
        ),
        "incomplete_resume_hint_ram": (
            "Uma retomada real não é possível -- uma captura de RAM é uma operação única. "
            "O botão abaixo reabre a tela de RAM com as mesmas informações do caso para "
            "recomeçar."
        ),
        "btn_goto_ssh_screen": "Ir para Tela Direto/VPN/Tor",
        "btn_reopen_ram_screen": "Reabrir Tela de RAM",
    },
    "fr": {
        "title": "Chameleon",
        "subtitle": "Moteur d'Acquisition Forensique Numérique",
        "choose_language": "Langue",
        "choose_engine": "Choisir la méthode",
        "ssh_engine": "Image distante via SSH",
        "ssh_engine_desc": "Se connecte à une cible Linux ou Windows via SSH et crée une image de disque/fichiers",
        "ram_engine": "Image de RAM (Windows, local)",
        "ram_engine_desc": "S'exécute sur cette machine, aucune connexion distante nécessaire",
        "launched": "démarré.",
        "error_launch": "Impossible de démarrer, vérifiez si le fichier est manquant :",
        "missing_file": "Ce fichier ne se trouve pas où il devrait être :",

        "nav_home": "Accueil",
        "nav_direct": "Direct / Redirection de Port",
        "nav_vpn": "VPN",
        "nav_tor": "Tor (Urgence)",
        "nav_ram": "Image RAM",
        "nav_history": "Historique des Dossiers",
        "nav_incomplete": "Inachevés",
        "nav_help": "Centre d'Aide",
        "nav_settings": "Paramètres",

        "home_intro": "Choisissez une méthode -- la page de chacune explique ce qu'elle fait et comment l'utiliser.",
        "home_recent_case_title": "Dossier le Plus Récent",
        "btn_view_all_cases": "Voir Tous les Dossiers",

        "method_when_heading": "Quand l'utiliser ?",
        "method_requires_heading": "Prérequis (dans l'ordre)",
        "method_steps_heading": "Étape par étape",
        "btn_start": "Démarrer",
        "btn_open": "Ouvrir",

        "case_info_title": "Informations du Dossier",
        "case_info_note": "(Facultatif -- laissez vide si vous ne produisez pas de rapport)",
        "field_case_id": "N° de Dossier",
        "field_examiner": "Enquêteur",
        "field_custodian": "Propriétaire de l'Appareil / Détenteur",
        "field_organization": "Organisation",
        "btn_continue": "Continuer",

        "help_back_to_tool": "← Revenir là où vous étiez",
        "help_center_title": "Centre d'Aide",
        "help_center_intro": "Des explications détaillées sur certains choix de l'application se trouvent ici.",
        "what_does_this_mean_titled": "Qu'est-ce que cela signifie ? ({title})",
        "btn_read_in_help_center": "Qu'est-ce que cela signifie ? (lire dans le Centre d'Aide)",

        "settings_title": "Paramètres",
        "settings_language_card": "Langue",
        "settings_theme_card": "Thème",
        "theme_dark": "Sombre",
        "theme_light": "Clair",
        "settings_timezone_card": "Fuseau Horaire (Affichage)",
        "settings_timezone_note": (
            "Un équivalent en heure locale est ajouté à côté des horodatages UTC dans les "
            "rapports, uniquement pour la lisibilité -- la valeur qui fait foi comme preuve "
            "est toujours l'UTC, ce choix n'affecte jamais le report.json lui-même."
        ),
        "settings_timezone_row_label": "Fuseau Horaire :",
        "settings_timezone_utc_option": "UTC (aucun équivalent local affiché)",

        "case_history_title": "Historique des Dossiers",
        "case_history_load_error": "Impossible de charger l'historique des dossiers : {exc}",
        "case_history_export_csv": "Exporter en CSV",
        "case_history_search_placeholder": "Filtrer par n° de dossier, enquêteur, cible...",
        "case_history_tag_label": "Étiquette",
        "case_history_tag_placeholder": "Ajouter une étiquette (p. ex. suivi nécessaire)",
        "case_history_group_count": "{count} entrées",
        "btn_export_pdf": "Enregistrer en PDF",
        "pdf_save_dialog_title": "Enregistrer en PDF",
        "pdf_export_error": "Impossible de créer le PDF : {exc}",
        "pdf_export_success": "PDF enregistré : {path}",
        "case_history_empty": "Aucun dossier enregistré pour l'instant -- il apparaîtra ici une fois une acquisition terminée.",
        "engine_ssh": "Moteur SSH",
        "engine_ram": "Moteur RAM",
        "case_history_no_case_id": "Aucun N° de Dossier",
        "label_engine": "Moteur",
        "label_target": "Cible",
        "label_custodian": "Détenteur",
        "label_examiner": "Enquêteur",
        "label_organization": "Organisation",
        "label_date": "Date",
        "btn_open_report": "Ouvrir le Rapport",
        "csv_save_default_name": "historique_des_dossiers.csv",
        "csv_save_dialog_title": "Enregistrer en CSV",
        "csv_write_error": "Impossible d'écrire le CSV : {exc}",
        "csv_saved": "CSV enregistré : {path}",

        "incomplete_title": "Opérations Inachevées",
        "incomplete_intro": "Les opérations restées inachevées suite à une perte de connexion ou à la fermeture de l'application sont listées ici.",
        "incomplete_empty": "Aucune opération inachevée.",
        "label_type": "Type",
        "label_progress": "Progression",
        "label_started": "Démarré",
        "type_ssh_full_disk": "SSH Disque Complet",
        "type_ssh_file_folder": "SSH Fichier/Dossier",
        "type_ram_process": "RAM (Dump de Processus)",
        "type_ram_full": "RAM (Mémoire Complète)",
        "progress_blocks": "{completed}/{total} blocs",
        "progress_files": "{completed}/{total} fichiers",
        "incomplete_resume_hint_disk": (
            "Pour continuer, allez à l'écran de connexion et reconnectez-vous à la même "
            "cible/au même disque -- il vous sera demandé si vous souhaitez reprendre."
        ),
        "incomplete_resume_hint_tree": (
            "Pour continuer, allez à l'écran de connexion et reconnectez-vous à la même "
            "cible/au même chemin -- il vous sera demandé si vous souhaitez reprendre."
        ),
        "incomplete_resume_hint_ram": (
            "Une reprise réelle n'est pas possible -- un instantané de RAM est une opération "
            "unique. Le bouton ci-dessous rouvre l'écran RAM avec les mêmes informations de "
            "dossier pour recommencer."
        ),
        "btn_goto_ssh_screen": "Aller à l'Écran Direct/VPN/Tor",
        "btn_reopen_ram_screen": "Rouvrir l'Écran RAM",
    },
}

# Desteklenen dillerin sirali listesi -- Ayarlar sayfasindaki dil seciciyi
# TEK bir yerden besler (bkz. chameleon_gui.py _show_settings).
LANGUAGES = [
    ("tr", "Türkçe"),
    ("en", "English"),
    ("es", "Español"),
    ("de", "Deutsch"),
    ("pt", "Português"),
    ("fr", "Français"),
]


def t(key, lang="tr", **kwargs):
    """Anahtari verilen dilde dondurur; bulunamazsa TR'ye, o da yoksa
    anahtarin kendisine duser (hicbir zaman crash etmez -- eksik bir
    ceviri, en kotu ihtimalle ekranda anahtar ismini gosterir, uygulamayi
    durdurmaz). {exc}/{path} gibi format alanlari varsa kwargs ile
    doldurulur."""
    text = STRINGS.get(lang, STRINGS["tr"]).get(key)
    if text is None:
        text = STRINGS["tr"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
