# canias-erp-web-service-python

**English:** [README.md](https://github.com/hcemaras/canias-erp-web-service-python/blob/main/README.md)

[![CI](https://github.com/hcemaras/canias-erp-web-service-python/actions/workflows/ci.yml/badge.svg)](https://github.com/hcemaras/canias-erp-web-service-python/actions/workflows/ci.yml)

**CANIAS ERP** (caniasERP) **TROIA Web Service 2.0** için Python istemcisi ve komut satırından bağlantı kontrolü.

- SOAP uç noktası üzerinden `login`, `listServices`, `callService` ve `logout`
- Oturum her durumda kapatılır; entegrasyonlar CANIAS lisans koltuğu tüketip bırakmaz
- Üçüncü parti bağımlılık yok; Windows ve Linux'ta Python 3.10+

> **Durum: alfa.** Protokol TROIA Web Service 2.0 dokümantasyonuna göre yazıldı ve taklit sunucu yanıtlarıyla test edildi. Henüz gerçek bir CANIAS sunucusunda doğrulanmadı.
>
> Resmi olmayan bir topluluk projesidir; IAS ile bağlantısı yoktur ve IAS tarafından onaylanmamıştır. CANIAS, sahibinin ticari markasıdır.

## Kurulum

```bash
pip install git+https://github.com/hcemaras/canias-erp-web-service-python
```

## Hızlı başlangıç

```python
from canias_erp_web_service import CaniasWebServiceClient, config_from_env, load_env

config = config_from_env(load_env(".env"))

with CaniasWebServiceClient(config) as client:  # blok bitince logout çalışır, hata olsa bile
    print(client.list_services())

    result = client.call("PING", ["birinci", "ikinci"])
    if result.ok:
        print(result.value)
    else:
        print(result.sys_status, result.sys_status_error)
```

İlk çağrı otomatik olarak login yapar; istenirse `client.login()` ayrıca çağrılabilir.

## Logout neden önemli

Web servis oturumları, Java ve Web Client kullanıcılarıyla aynı eşzamanlı lisans koltuklarını kullanır; CANIAS dongle'ı hepsini birlikte sayar. Koltuk, `logout` çağrılana ya da sunucudaki oturum zaman aşımına uğrayana kadar dolu kalır. Çöken istemcilerin açık bıraktığı oturumlar koltuklarını tutmaya devam eder. Bunlar birikince, içeride az kullanıcı olsa bile lisans hataları (login hata kodu 6, 11, 15, 20 ve 21) başlar. İstemciyi `with` bloğu içinde kullanmak logout'u garanti eder.

## Ayarlar

`config_from_env(env)` aşağıdaki ayarları bir sözlükten okur. `load_env(path)` bu sözlüğü bir `.env` dosyasından ve `CANIAS_*` ortam değişkenlerinden oluşturur; ortam değişkenleri önceliklidir. Argümansız çağrılan `config_from_env()` yalnızca ortam değişkenlerini kullanır. Örnek: [.env.example](https://github.com/hcemaras/canias-erp-web-service-python/blob/main/.env.example).

| Değişken | Zorunlu | Anlamı |
|---|---|---|
| `CANIAS_WS_URL` | evet | Servis adresi, örn. `http://sunucu:8080/CaniasWS-v2/services/CaniasWebService`. Yol kuruluma göre değişir; sondaki `?wsdl` silinir |
| `CANIAS_WS_CLIENT` | evet | Client (mandant) kodu, örn. `00` |
| `CANIAS_WS_LANGUAGE` | hayır | Oturum dili: `T`, `E`, `D`, … (varsayılan `T`) |
| `CANIAS_WS_DB_SERVER` | evet | Veritabanı sunucusu takma adı, CANIAS giriş ekranındaki gibi |
| `CANIAS_WS_DB_NAME` | evet | Veritabanı takma adı. Servislerinizdeki TROIA `SELECT`'leri bu veritabanında çalışır |
| `CANIAS_WS_APP_SERVER` | evet | Uygulama sunucusu takma adı |
| `CANIAS_WS_USER` | evet | Web servis kullanıcısı |
| `CANIAS_WS_PASSWORD` | evet | Parola |
| `CANIAS_WS_PASSWORD_MODE` | hayır | `plain` (varsayılan) veya `md5`. TROIA dokümantasyonu MD5 özeti istiyor; başka istemciler sunucunun düz parolayı da kabul ettiğini bildiriyor |
| `CANIAS_WS_TIMEOUT` | hayır | İstek zaman aşımı, saniye (varsayılan `30`) |

İlk sekiz değişkenin adı TypeScript istemcisi [canias-ws](https://github.com/bymcs/canias-ws) ile aynıdır; tek bir `.env` dosyası ikisinde de çalışır.

## Bağlantı kontrolü

CANIAS sunucusuna erişebilen bir bilgisayarda çalıştırın:

```bash
canias-erp-web-service-check --env .env
canias-erp-web-service-check --env .env --service PING --param 1 --report-dir reports
python -m canias_erp_web_service --env .env   # Scripts klasörü PATH'te değilse aynı komut
```

Kontrol önce WSDL'i okur ve Web Service 2.0'ı eski 1.0'dan ayırt eder. Sonra login yapar, kullanıcının çağırabildiği servisleri listeler, istenirse bir test servisi çağırır ve logout yapar. Çıkış kodu yalnızca bütün adımlar başarılıysa `0` olur. `--report-dir` verilirse JSON rapor yazar. Ne ekran çıktısında ne raporda parola, SessionId veya SecurityKey bulunur.

`--service` servisi CANIAS içinde gerçekten çalıştırır; yalnızca okuma yapan bir servis seçin.

Başarılı bir çalıştırma:

```text
[ OK  ] WSDL erişilebilir, TROIA Web Service 2.0 (callService, listServices, login, logout)
[ OK  ] Login başarılı (WSUSER@CANIAS903). Bir lisans koltuğu kullanılıyor.
[ OK  ] Çağrılabilir servisler (1): PING_TESTWS
[BİLGİ] --service için ilk '_' öncesini kullanın (örn. PING_TESTWS -> PING)
[ OK  ] PING: SYSStatus=0
<RESULT>OK</RESULT>
[ OK  ] Logout yapıldı, lisans koltuğu bırakıldı.
```

Başarısız bir login, hata kodunu ve neye bakılması gerektiğini yazar:

```text
[HATA ] login başarısız (kod 15): Azami kullanıcı sayısı aşıldı
[ÖNERİ] Lisans havuzu dolu görünüyor. Web servis oturumları kullanıcılarla aynı dongle lisanslarını kullanır …
```

### Login hata kodları

`LoginError.code`, sunucunun `login error: n` mesajındaki `n` değeridir. Kodlar TROIA dokümantasyonundan alınmıştır.

| Kod | Anlamı | Kontrol edilecek |
|---|---|---|
| 2 | Geçersiz kullanıcı bilgileri | Kullanıcı adı ve parola; `CANIAS_WS_PASSWORD_MODE=md5` deneyin |
| 3 | Veritabanı bağlantı hatası | `CANIAS_WS_DB_SERVER`, `CANIAS_WS_DB_NAME` |
| 4 | Geçersiz client (mandant) | `CANIAS_WS_CLIENT` |
| 5 | Sistem tablosu hatası | |
| 6, 11, 15, 20, 21 | Lisans hatası; kullanıcı sayısı; azami kullanıcı sayısı; azami oturum sayısı; modül kullanıcı sayısı | SYS'te asılı web servis oturumlarını kapatıp tekrar deneyin. Sorun sürerse lisans atamasını IAS ile teyit edin |
| 7 | Kullanıcı bloke | |
| 8 | Geçersiz saat dilimi | |
| 10, 23 | Uygun sunucu bulunamadı; geçersiz sunucu | `CANIAS_WS_APP_SERVER` |
| 16 | Versiyon uyumsuzluğu | Tomcat'teki `canias1.jar`, uygulama sunucusuyla aynı build olmalı |
| 17 | Bakım modu | |
| 18, 22 | Web servis lisansı geçersiz; modül lisansı geçersiz | Web servis (WSR) lisansını IAS ile teyit edin |
| 19 | Sunucu erişim dosyası erişimi reddetti | Bu bilgisayarın IP adresine izin verin |
| 24 | Geçersiz girdi | |
| 26 | Geçersiz istemci tipi | Kullanıcının istemci tipi web servis girişine izin vermeli |
| 28 | Dil lisansı hatası | `CANIAS_WS_LANGUAGE` |

## CANIAS'ta servis tanımlama

Bir TROIA sınıf metodu, web servis olarak tanımlandığında (`WSRT01` ekranı) ve web servis kullanıcısına çağırma yetkisi verildiğinde (`WSRT02` ekranı) çağrılabilir hale gelir. İki tanım da login olunan veritabanında bulunmalıdır. `list_services()` `PING_TESTWS` gibi değerler döndürür; `call()`'a ilk `_` işaretinden önceki kısmı verin.

## API

`CaniasWebServiceClient(config)`:

| Metot | Açıklama |
|---|---|
| `login() -> Session` | Oturum açar ve bir lisans koltuğu kullanır. Açık bir oturum varsa önce onu kapatır |
| `list_services() -> list[str]` | Kullanıcının çağırabildiği servisler. Oturum süresi dolmuşsa da boş döner |
| `call(service_id, params=(), *, permanent=False, extra_variables="") -> CallResult` | Tanımlı bir servisi çalıştırır. `params` sıralı değerler listesidir; `TABLE` ve `VECTOR` parametreleri için hazır bir `<PARAMETERS>` XML metni de verilebilir. `permanent=True` sunucudaki işlemi (transaction) bir sonraki çağrı için açık tutar. `extra_variables`, döndürülecek TROIA değişkenlerinin virgülle ayrılmış listesidir |
| `logout() -> bool` | Elinden geleni yapar, asla hata fırlatmaz; sunucunun cevabını döndürür |

`CallResult` alanları: `ok` (`SYSStatus == 0`), `value`, `messages` (`<TROIAMESSAGES>` XML), `extra_variables` (`<EXTRAVARIABLES>` XML), `sys_status`, `sys_status_error`, `request_id`. Birçok servis, `SYSStatus` `0` iken iş hatasını `value` içinde bildirir; ikisine de bakın.

Hatalar; hepsi `CaniasError` sınıfından türer:

| Hata | Ne zaman |
|---|---|
| `ConfigError` | Bir ayar eksik veya geçersiz |
| `TransportError` | Ağ hatası, zaman aşımı, HTTP hatası veya XML olmayan yanıt |
| `SoapFault` | Sunucu SOAP fault döndürdü |
| `LoginError` | Login reddedildi; `code` login hata kodunu taşır |
| `ProtocolError` | Yanıt beklenen biçimde değil |

Sıfırdan farklı bir `SYSStatus` hata olarak fırlatılmaz, `CallResult` içinde döner.

## Sınırlamalar

- Yalnızca Web Service 2.0.
- Şifreli veya sıkıştırılmış veri desteklenmez: login `Encrypted=false` ve `Compression=false` gönderir; sıkıştırılmış bir yanıt `ProtocolError` fırlatır.
- Uç nokta genellikle düz HTTP konuşur; servis TLS veya VPN arkasında değilse parola açık metin olarak gider.
- İstekler sistem proxy ayarlarını kullanmaz, çünkü CANIAS normalde iç ağda çalışır.

## Güvenlik notu

HawkTrace, Mayıs 2026'da [caniasERP 8.03 için sekiz CVE](https://hawktrace.com/blog/caniaserp/) yayımladı. Bunların arasında kimlik doğrulama gerektirmeyen bir uzaktan komut çalıştırma zinciri de var (CVE-2026-8214, CVE-2026-8216, CVE-2026-8217 ve CVE-2026-8215). Açıklar, masaüstü istemcinin kullandığı Java RMI arayüzünde ve JNLP indirme adresinde; SOAP web serviste değil. Rapora göre üretici yayından önce yanıt vermedi. Uygulama sunucusunun RMI portunu ve JNLP adresini güvenilmeyen ağlardan erişilemez tutun.

## Geliştirme

```bash
pip install -e .
python -m unittest discover -s tests
```

Testler yerel bir taklit sunucuya karşı çalışır; CANIAS kurulumu gerektirmez.

## İlgili projeler

- [caniasERP/troia-webservice-connector](https://github.com/caniasERP/troia-webservice-connector): resmi Java bağlantı kütüphanesi
- [bymcs/canias-ws](https://github.com/bymcs/canias-ws): TypeScript istemcisi
- [TROIA Web Services dokümantasyonu](https://github.com/bahtiyartan/troia/blob/master/docs/70WebServices.rst)

## Lisans

[MIT](https://github.com/hcemaras/canias-erp-web-service-python/blob/main/LICENSE)
