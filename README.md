# canias-erp-web-service-python

**Türkçe:** [README.tr.md](https://github.com/hcemaras/canias-erp-web-service-python/blob/main/README.tr.md)

[![CI](https://github.com/hcemaras/canias-erp-web-service-python/actions/workflows/ci.yml/badge.svg)](https://github.com/hcemaras/canias-erp-web-service-python/actions/workflows/ci.yml)

Python client for the **CANIAS ERP** (caniasERP) **TROIA Web Service 2.0**, with a command-line connectivity check.

- `login`, `listServices`, `callService` and `logout` over the SOAP endpoint
- The session is logged out on every code path, so integrations do not leak CANIAS license seats
- No third-party dependencies; Python 3.10+ on Windows and Linux

> **Status: alpha.** The protocol follows the TROIA Web Service 2.0 documentation and is tested against simulated server responses. It has not yet been verified against a live CANIAS server.
>
> Unofficial community project, not affiliated with or endorsed by IAS. CANIAS is a trademark of its owner.

## Installation

```bash
pip install git+https://github.com/hcemaras/canias-erp-web-service-python
```

## Quick start

```python
from canias_erp_web_service import CaniasWebServiceClient, config_from_env, load_env

config = config_from_env(load_env(".env"))

with CaniasWebServiceClient(config) as client:  # logout runs when the block ends, even after an error
    print(client.list_services())

    result = client.call("PING", ["first", "second"])
    if result.ok:
        print(result.value)
    else:
        print(result.sys_status, result.sys_status_error)
```

The first call logs in automatically; `client.login()` can also be called explicitly.

## Why logout matters

Web service sessions take the same concurrent license seats as Java and Web Client users; the CANIAS dongle counts them together. A seat stays taken until `logout` is called or the server-side session times out. Sessions left open by crashed clients keep their seats, and enough of them cause license errors (login error codes 6, 11, 15, 20 and 21) even when few people are logged in. Using the client as a context manager guarantees the logout.

## Configuration

`config_from_env(env)` reads the settings below from a mapping. `load_env(path)` builds that mapping from a `.env` file plus `CANIAS_*` environment variables; environment variables win. Called without arguments, `config_from_env()` uses the environment only. See [.env.example](https://github.com/hcemaras/canias-erp-web-service-python/blob/main/.env.example).

| Variable | Required | Meaning |
|---|---|---|
| `CANIAS_WS_URL` | yes | Service URL, e.g. `http://host:8080/CaniasWS-v2/services/CaniasWebService`. The path depends on the installation; a trailing `?wsdl` is removed |
| `CANIAS_WS_CLIENT` | yes | Client (mandant) code, e.g. `00` |
| `CANIAS_WS_LANGUAGE` | no | Session language: `T`, `E`, `D`, … (default `T`) |
| `CANIAS_WS_DB_SERVER` | yes | Database server alias, as on the CANIAS login screen |
| `CANIAS_WS_DB_NAME` | yes | Database alias. TROIA `SELECT`s inside your services run against this database |
| `CANIAS_WS_APP_SERVER` | yes | Application server alias |
| `CANIAS_WS_USER` | yes | Web service user |
| `CANIAS_WS_PASSWORD` | yes | Password |
| `CANIAS_WS_PASSWORD_MODE` | no | `plain` (default) or `md5`. The TROIA documentation specifies an MD5 hash; other clients report that servers accept plain text |
| `CANIAS_WS_TIMEOUT` | no | Request timeout in seconds (default `30`) |

The first eight names match the TypeScript client [canias-ws](https://github.com/bymcs/canias-ws), so one `.env` file serves both.

## Connectivity check

Run it on a machine that can reach the CANIAS server:

```bash
canias-erp-web-service-check --env .env
canias-erp-web-service-check --env .env --service PING --param 1 --report-dir reports
python -m canias_erp_web_service --env .env   # same command when the Scripts folder is not on PATH
```

The check reads the WSDL and tells Web Service 2.0 from the older 1.0. Then it logs in, lists the services the user may call, optionally calls one test service and logs out. The exit code is `0` only when every step succeeds. `--report-dir` writes a JSON report. Neither the console output nor the report contains the password, session id or security key.

`--service` really runs the service inside CANIAS; use one that only reads.

Console messages are in Turkish. A successful run:

```text
[ OK  ] WSDL erişilebilir, TROIA Web Service 2.0 (callService, listServices, login, logout)
[ OK  ] Login başarılı (WSUSER@CANIAS903). Bir lisans koltuğu kullanılıyor.
[ OK  ] Çağrılabilir servisler (1): PING_TESTWS
[BİLGİ] --service için ilk '_' öncesini kullanın (örn. PING_TESTWS -> PING)
[ OK  ] PING: SYSStatus=0
<RESULT>OK</RESULT>
[ OK  ] Logout yapıldı, lisans koltuğu bırakıldı.
```

A failed login prints the error code and what to check:

```text
[HATA ] login başarısız (kod 15): Azami kullanıcı sayısı aşıldı
[ÖNERİ] Lisans havuzu dolu görünüyor. Web servis oturumları kullanıcılarla aynı dongle lisanslarını kullanır …
```

### Login error codes

`LoginError.code` holds `n` from the server's `login error: n` message. The codes come from the TROIA documentation; the error text itself is Turkish.

| Code | Meaning | What to check |
|---|---|---|
| 2 | Invalid login credentials | User name and password; try `CANIAS_WS_PASSWORD_MODE=md5` |
| 3 | Database connection error | `CANIAS_WS_DB_SERVER`, `CANIAS_WS_DB_NAME` |
| 4 | Invalid client | `CANIAS_WS_CLIENT` |
| 5 | System table error | |
| 6, 11, 15, 20, 21 | License error; user count; maximum user count; maximum session count; module user count | Close stale web service sessions in SYS, then retry. If it persists, confirm the license assignment with IAS |
| 7 | User blocked | |
| 8 | Invalid time zone | |
| 10, 23 | No suitable server found; invalid server | `CANIAS_WS_APP_SERVER` |
| 16 | Version inconsistency | `canias1.jar` in Tomcat must match the application server build |
| 17 | Maintenance mode | |
| 18, 22 | Invalid web service license; invalid module license | Web service (WSR) license, with IAS |
| 19 | Access denied by the server access file | Allow this machine's IP address |
| 24 | Invalid input | |
| 26 | Invalid client type | The user's client type must allow web service logins |
| 28 | Language license error | `CANIAS_WS_LANGUAGE` |

## Registering a service in CANIAS

A TROIA class method becomes callable once it is registered as a web service (screen `WSRT01`) and the web service user has the right to call it (screen `WSRT02`), in the database you log in to. `list_services()` returns items such as `PING_TESTWS`; pass the part before the first `_` to `call()`.

## API

`CaniasWebServiceClient(config)`:

| Method | Description |
|---|---|
| `login() -> Session` | Opens a session and takes one license seat. An existing session is logged out first |
| `list_services() -> list[str]` | Services the user may call. Also empty when the session has expired |
| `call(service_id, params=(), *, permanent=False, extra_variables="") -> CallResult` | Runs a registered service. `params` is a sequence of positional values, or a ready `<PARAMETERS>` XML string for `TABLE` and `VECTOR` parameters. `permanent=True` keeps the server transaction open for the next call. `extra_variables` lists TROIA variables to return, comma-separated |
| `logout() -> bool` | Best effort and never raises; returns the server's answer |

`CallResult` fields: `ok` (`SYSStatus == 0`), `value`, `messages` (`<TROIAMESSAGES>` XML), `extra_variables` (`<EXTRAVARIABLES>` XML), `sys_status`, `sys_status_error`, `request_id`. Many services report business errors inside `value` while `SYSStatus` is `0`, so check both.

Errors, all subclasses of `CaniasError`:

| Error | When |
|---|---|
| `ConfigError` | A setting is missing or invalid |
| `TransportError` | Network failure, timeout, HTTP error or a non-XML response |
| `SoapFault` | The server answered with a SOAP fault |
| `LoginError` | Login was refused; `code` holds the login error code |
| `ProtocolError` | The response did not have the expected shape |

A non-zero `SYSStatus` is returned in `CallResult`, not raised.

## Limitations

- Web Service 2.0 only.
- No encrypted or compressed payloads: login sends `Encrypted=false` and `Compression=false`, and a compressed response raises `ProtocolError`.
- The endpoint usually speaks plain HTTP, so the password travels in clear text unless the service sits behind TLS or a VPN.
- Requests ignore system proxy settings, because CANIAS normally runs on the internal network.

## Security note

In May 2026 HawkTrace published [eight CVEs for caniasERP 8.03](https://hawktrace.com/blog/caniaserp/), including an unauthenticated remote code execution chain (CVE-2026-8214, CVE-2026-8216, CVE-2026-8217 and CVE-2026-8215). They are in the Java RMI interface used by the desktop client and in the JNLP deployment endpoint, not in the SOAP web service. According to the report, the vendor did not respond before publication. Keep the application server's RMI port and the JNLP endpoint unreachable from untrusted networks.

## Development

```bash
pip install -e .
python -m unittest discover -s tests
```

The tests run against a local fake server and need no CANIAS installation.

## Related projects

- [caniasERP/troia-webservice-connector](https://github.com/caniasERP/troia-webservice-connector): official Java connector
- [bymcs/canias-ws](https://github.com/bymcs/canias-ws): TypeScript client
- [TROIA Web Services documentation](https://github.com/bahtiyartan/troia/blob/master/docs/70WebServices.rst)

## License

[MIT](https://github.com/hcemaras/canias-erp-web-service-python/blob/main/LICENSE)
