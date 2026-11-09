"""Connectivity check for the CANIAS ERP web service (console messages are Turkish).

    canias-erp-web-service-check --env .env [--service PING --param 1] [--report-dir reports]

Runs WSDL -> login -> listServices -> optional test service -> logout. Logout runs on
every path, so the check holds a license seat only while it runs. Neither the console
output nor the report contains the password, session id or security key.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .client import (
    CaniasError,
    CaniasWebServiceClient,
    LoginError,
    TransportError,
    WebServiceConfig,
    fetch_wsdl_operations,
)
from .config import ConfigError, config_from_env, load_env

_LICENSE_HINT = (
    "Lisans havuzu dolu görünüyor. Web servis oturumları kullanıcılarla aynı dongle lisanslarını kullanır ve "
    "logout yapılmadan kopan oturumlar lisansı tutmaya devam eder. SYS ekranından aktif oturumlara bakın, "
    "web servis kullanıcısına ait asılı oturumları kapatın, sonra tekrar deneyin. Sorun sürerse bu kullanıcı "
    "için lisans/modül atamasını IAS'tan teyit edin."
)
LOGIN_HINTS: dict[int, str] = {
    2: "Kullanıcı adı/parola reddedildi. Sunucu MD5 bekliyor olabilir: CANIAS_WS_PASSWORD_MODE=md5 deneyin.",
    3: "CANIAS_WS_DB_SERVER / CANIAS_WS_DB_NAME takma adları uygulama sunucusundaki tanımla eşleşmiyor.",
    4: "CANIAS_WS_CLIENT (mandant kodu, örn. 00) yanlış.",
    6: _LICENSE_HINT,
    10: "CANIAS_WS_APP_SERVER takma adı uygun bir uygulama sunucusuna çözülmedi.",
    11: _LICENSE_HINT,
    15: _LICENSE_HINT,
    16: "Tomcat'teki canias1.jar, uygulama sunucusuyla aynı build numarasında olmalı.",
    17: "Sistem bakım modunda.",
    18: "Web servis lisansı geçersiz/tanımsız. WSR lisansını IAS/bayi ile teyit edin.",
    19: "Bu bilgisayarın IP adresi sunucu erişim dosyasında izinli değil.",
    20: _LICENSE_HINT,
    21: _LICENSE_HINT,
    22: "Modül lisansı geçersiz. WSR modül lisansını IAS/bayi ile teyit edin.",
    23: "CANIAS_WS_APP_SERVER geçersiz.",
    26: "Bu kullanıcının istemci tipi web servis girişine izin vermiyor.",
    28: "Seçilen oturum dili lisanslı değil. CANIAS_WS_LANGUAGE değerini kontrol edin.",
}


def say(status: str, message: str) -> None:
    """Prints one aligned status line, e.g. ``[ OK  ] ...``."""
    print(f"[{status:^5}] {message}")


def configure_console() -> None:
    """Server text may contain characters the console code page cannot show; replace them instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def run_check(config: WebServiceConfig, service: str | None = None, params: Sequence[str] = ()) -> dict[str, Any]:
    """Runs the check, printing each step; returns a report without secrets (``report["ok"]`` is the verdict)."""
    report: dict[str, Any] = {"ok": False, "url": config.url}
    try:
        operations = fetch_wsdl_operations(config.url, config.timeout)
    except CaniasError as exc:
        say("HATA", f"WSDL alınamadı: {exc}")
        report["error"] = str(exc)
        if isinstance(exc, TransportError) and exc.snippet:
            report["snippet"] = exc.snippet
        return report
    report["wsdl_operations"] = operations
    if "callService" in operations:
        report["version"] = "2.0"
        say("OK", f"WSDL erişilebilir, TROIA Web Service 2.0 ({', '.join(operations)})")
    elif "callIASService" in operations:
        report["version"] = "1.0"
        say("HATA", "Bu adres eski TROIA Web Service 1.0. Web Service 2.0 adresini kullanın.")
        report["error"] = "web service 1.0 endpoint"
        return report
    else:
        say("UYARI", f"Tanınmayan WSDL işlemleri: {operations}")

    client = CaniasWebServiceClient(config)
    try:
        session = client.login()
        report["login"] = {"success": True, "contact_num": session.contact_num}
        say("OK", f"Login başarılı ({config.username}@{config.db_name}). Bir lisans koltuğu kullanılıyor.")

        services = client.list_services()
        report["services"] = services
        if services:
            say("OK", f"Çağrılabilir servisler ({len(services)}): {', '.join(services)}")
            say("BİLGİ", "--service için ilk '_' öncesini kullanın (örn. PING_TESTWS -> PING)")
        else:
            say("UYARI", "Bu kullanıcıya açık servis yok. WSRT01'de servis, WSRT02'de kullanıcı yetkisi tanımlayın.")

        if service:
            result = client.call(service, params)
            report["call"] = {
                "service": service,
                "ok": result.ok,
                "sys_status": result.sys_status,
                "sys_status_error": result.sys_status_error,
                "value": result.value[:2000],
                "messages": result.messages[:2000],
            }
            say("OK" if result.ok else "HATA", f"{service}: SYSStatus={result.sys_status} {result.sys_status_error}".rstrip())
            if result.value:
                print(result.value[:2000])
            report["ok"] = result.ok
        else:
            report["ok"] = True
    except LoginError as exc:
        report["login"] = {"success": False, "code": exc.code, "message": exc.raw_message}
        say("HATA", str(exc))
        if exc.code in LOGIN_HINTS:
            say("ÖNERİ", LOGIN_HINTS[exc.code])
    except CaniasError as exc:
        report["error"] = str(exc)
        say("HATA", str(exc))
    finally:
        had_session = client.session is not None
        logged_out = client.logout()
        if had_session:
            report["logout"] = logged_out
            if logged_out:
                say("OK", "Logout yapıldı, lisans koltuğu bırakıldı.")
            else:
                say("UYARI", "Logout teyit edilemedi. Oturum sunucu zaman aşımına kadar lisansı tutabilir.")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    configure_console()
    parser = argparse.ArgumentParser(
        prog="canias-erp-web-service-check",
        description="CANIAS ERP web servis bağlantı kontrolü: WSDL, login, servis listesi, isteğe bağlı test servisi, logout.",
    )
    parser.add_argument("--env", type=Path, default=Path(".env"), help="ayar dosyası (varsayılan: .env)")
    parser.add_argument("--service", help="login sonrası çağrılacak TEST servisi (WSRT01'deki ServiceId)")
    parser.add_argument("--param", action="append", default=[], help="servis parametresi (sırayla, tekrarlanabilir)")
    parser.add_argument("--report-dir", type=Path, help="JSON raporun yazılacağı klasör (verilmezse rapor yazılmaz)")
    args = parser.parse_args(argv)

    if not args.env.is_file():
        say("UYARI", f"{args.env} bulunamadı; yalnızca ortam değişkenleri kullanılıyor")
    try:
        config = config_from_env(load_env(args.env))
    except ConfigError as exc:
        say("HATA", str(exc))
        report: dict[str, Any] = {"ok": False, "error": str(exc)}
    else:
        report = run_check(config, args.service, args.param)

    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        path = args.report_dir / f"check-{now:%Y%m%d-%H%M%S-%f}.json"
        content = {"created": now.isoformat(timespec="seconds"), **report}
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nRapor: {path}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
