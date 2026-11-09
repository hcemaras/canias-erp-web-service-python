"""Client for the CANIAS ERP (TROIA) Web Service 2.0.

The endpoint (for example ``CaniasWS-v2/services/CaniasWebService``) is an AXIS 1.4
SOAP 1.1 ``rpc/encoded`` service with four operations: ``login``, ``logout``,
``listServices`` and ``callService``. Envelopes are built by hand because
WSDL-driven clients handle ``rpc/encoded`` + ``multiRef`` poorly.

Every successful ``login`` holds one concurrent license seat on the CANIAS
dongle until ``logout`` is called or the server-side session times out, so use
the client as a context manager: ``logout`` then runs on every path.

Error messages are Turkish; ``LoginError.code`` carries the numeric login error.
"""

from __future__ import annotations

import hashlib
import http.client
import itertools
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Sequence
from xml.sax.saxutils import escape

_CANIAS_NS = "http://webservice.ias.com"
_SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
_SOAP_ENC = "http://schemas.xmlsoap.org/soap/encoding/"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_XSD_NS = "http://www.w3.org/2001/XMLSchema"

# "login error: n" codes from the TROIA Web Services 2.0 documentation.
LOGIN_ERRORS: dict[int, str] = {
    2: "Geçersiz kullanıcı bilgileri",
    3: "Veritabanı bağlantı hatası",
    4: "Geçersiz client (mandant)",
    5: "Sistem tablosu hatası",
    6: "Lisans hatası",
    7: "Kullanıcı bloke",
    8: "Geçersiz saat dilimi",
    10: "Uygun uygulama sunucusu bulunamadı",
    11: "Kullanıcı sayısı hatası",
    15: "Azami kullanıcı sayısı aşıldı",
    16: "Versiyon uyumsuzluğu",
    17: "Bakım modu",
    18: "Web servis lisansı geçersiz",
    19: "Sunucu erişim dosyası erişimi reddetti",
    20: "Azami oturum sayısı aşıldı",
    21: "Modül kullanıcı sayısı hatası",
    22: "Geçersiz modül lisansı",
    23: "Geçersiz sunucu",
    24: "Geçersiz girdi",
    26: "Geçersiz istemci tipi",
    28: "Dil lisansı hatası",
}

_LOGIN_ERROR_RE = re.compile(r"login error:\s*(\d+)", re.IGNORECASE)
_HREF_DEPTH_LIMIT = 32


class CaniasError(Exception):
    """Base class for all errors raised by this package."""


class TransportError(CaniasError):
    """Network failure, timeout, HTTP error or a non-XML response."""

    def __init__(self, message: str, *, status: int | None = None, snippet: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.snippet = snippet


class SoapFault(CaniasError):
    """The server answered with a SOAP ``Fault``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"SOAP fault {code}: {message}")
        self.code = code
        self.fault_message = message


class LoginError(CaniasError):
    """``login`` returned ``Success=false``; ``code`` is ``n`` from ``login error: n``."""

    def __init__(self, raw_message: str) -> None:
        match = _LOGIN_ERROR_RE.search(raw_message)
        self.code: int | None = int(match.group(1)) if match else None
        self.raw_message = raw_message
        description = LOGIN_ERRORS.get(self.code, "bilinmeyen kod") if self.code is not None else raw_message
        super().__init__(f"login başarısız (kod {self.code}): {description}")


class ProtocolError(CaniasError):
    """The response did not have the expected AXIS shape."""


@dataclass(frozen=True)
class WebServiceConfig:
    """Connection settings; the aliases are the ones on the CANIAS login screen."""

    url: str
    client: str
    language: str
    db_server: str
    db_name: str
    app_server: str
    username: str
    password: str = field(repr=False)
    password_md5: bool = False
    timeout: float = 30.0


@dataclass(frozen=True)
class Session:
    session_id: str = field(repr=False)
    security_key: str = field(repr=False)
    contact_num: str


@dataclass(frozen=True)
class CallResult:
    ok: bool
    """``SYSStatus == 0``. Services may still report a business error inside ``value``."""
    value: str
    messages: str
    extra_variables: str
    sys_status: int
    sys_status_error: str
    request_id: int


def _build_envelope(operation: str, params: Sequence[tuple[str, str, object]]) -> bytes:
    """SOAP 1.1 rpc/encoded request; ``params`` are ``(name, xsd_type, value)``."""
    parts = []
    for name, xsd_type, value in params:
        text = ("true" if value else "false") if isinstance(value, bool) else str(value)
        parts.append(f'<{name} xsi:type="xsd:{xsd_type}">{escape(text)}</{name}>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soapenv:Envelope xmlns:soapenv="{_SOAP_NS}" xmlns:xsi="{_XSI_NS}"'
        f' xmlns:xsd="{_XSD_NS}" xmlns:web="{_CANIAS_NS}">'
        "<soapenv:Header/>"
        f'<soapenv:Body soapenv:encodingStyle="{_SOAP_ENC}">'
        f"<web:{operation}>{''.join(parts)}</web:{operation}>"
        "</soapenv:Body></soapenv:Envelope>"
    ).encode("utf-8")


def build_parameters(values: Sequence[object]) -> str:
    """Positional TROIA method parameters as ``<PARAMETERS><PARAM>..</PARAM></PARAMETERS>``."""
    return "<PARAMETERS>" + "".join(f"<PARAM>{escape(str(v))}</PARAM>" for v in values) + "</PARAMETERS>"


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


class _Response:
    """Return node of an AXIS response with ``multiRef``/``href`` resolution."""

    def __init__(self, node: ET.Element, refs: dict[str, ET.Element]) -> None:
        self._refs = refs
        self.node = self._deref(node)

    def _deref(self, node: ET.Element) -> ET.Element:
        for _ in range(_HREF_DEPTH_LIMIT):
            href = node.get("href")
            if not href or not href.startswith("#"):
                return node
            target = self._refs.get(href[1:])
            if target is None:
                raise ProtocolError(f"multiRef bulunamadı: {href}")
            node = target
        raise ProtocolError("multiRef zinciri çok derin")

    def child(self, name: str, node: ET.Element | None = None) -> ET.Element | None:
        for element in self.node if node is None else node:
            if _local(element.tag) == name:
                return self._deref(element)
        return None

    def text(self, name: str, node: ET.Element | None = None) -> str:
        element = self.child(name, node)
        return (element.text or "") if element is not None else ""

    def string_response(self, name: str) -> str:
        """Value of a ``StringResponse`` member (``Value`` + ``Comressed`` flag)."""
        element = self.child(name)
        if element is None:
            return ""
        value = self.child("Value", element)
        if value is None:
            return element.text or ""
        # The server spells the flag "Comressed".
        flag = self.text("Comressed", element) or self.text("Compressed", element)
        if flag.strip().lower() in ("true", "1"):
            raise ProtocolError(f"{name} sıkıştırılmış döndü; sıkıştırma desteklenmiyor")
        return value.text or ""

    def items(self) -> list[str]:
        return [(self._deref(e).text or "") for e in self.node if isinstance(e.tag, str)]


def _parse_response(raw: bytes, operation: str) -> _Response:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ProtocolError(f"geçersiz XML yanıtı: {exc}") from exc
    body = next((e for e in root if _local(e.tag) == "Body"), None)
    if body is None:
        raise ProtocolError("SOAP Body bulunamadı")
    fault = next((e for e in body if _local(e.tag) == "Fault"), None)
    if fault is not None:
        code = next((e.text or "" for e in fault if _local(e.tag) == "faultcode"), "")
        message = next((e.text or "" for e in fault if _local(e.tag) == "faultstring"), "")
        raise SoapFault(code, message)
    refs = {e.get("id"): e for e in body.iter() if e.get("id")}
    response = next((e for e in body if _local(e.tag) == f"{operation}Response"), None)
    if response is None:
        raise ProtocolError(f"{operation}Response bulunamadı")
    returned = next((e for e in response if _local(e.tag) == f"{operation}Return"), None)
    if returned is None:
        raise ProtocolError(f"{operation}Return bulunamadı")
    return _Response(returned, refs)


# CANIAS runs on the internal network; ignore system/registry proxies (Windows).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http(url: str, *, data: bytes | None, timeout: float) -> bytes:
    """POST (or GET when ``data`` is None). Every network/HTTP failure becomes ``TransportError``."""
    headers = {"Accept": "text/xml"}
    if data is not None:
        headers |= {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}
    try:
        request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with _OPENER.open(request, timeout=timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            with exc:
                body = exc.read()
            # AXIS returns SOAP faults with HTTP 500; keep them for the parser.
            if b"Fault" not in body:
                raise TransportError(
                    f"HTTP {exc.code}: {url}", status=exc.code, snippet=body[:500].decode("utf-8", "replace")
                ) from exc
    except TransportError:
        raise
    except (http.client.HTTPException, ValueError, OSError) as exc:
        # URLError is an OSError; ValueError covers malformed URLs.
        raise TransportError(f"{url} adresine ulaşılamadı: {type(exc).__name__}: {exc}") from exc
    head = body.lstrip()[:15].lower()
    if not head.startswith(b"<") or head.startswith((b"<!doctype", b"<html")):
        raise TransportError(f"XML olmayan yanıt: {url}", snippet=body[:500].decode("utf-8", "replace"))
    return body


def fetch_wsdl_operations(url: str, timeout: float = 30.0) -> list[str]:
    """Operation names declared in the endpoint's WSDL (2.0: ``callService``; 1.0: ``callIASService``)."""
    raw = _http(f"{url}?wsdl", data=None, timeout=timeout)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ProtocolError(f"WSDL ayrıştırılamadı: {exc}") from exc
    names = {
        op.get("name", "")
        for port_type in root.iter()
        if _local(port_type.tag) == "portType"
        for op in port_type
        if _local(op.tag) == "operation"
    }
    return sorted(n for n in names if n)


class CaniasWebServiceClient:
    """One CANIAS session. Use as a context manager so ``logout`` always runs."""

    def __init__(self, config: WebServiceConfig) -> None:
        self._config = config
        self._session: Session | None = None
        self._request_ids = itertools.count(1)

    @property
    def session(self) -> Session | None:
        return self._session

    def __enter__(self) -> CaniasWebServiceClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.logout()

    def _post(self, operation: str, params: Sequence[tuple[str, str, object]]) -> _Response:
        raw = _http(self._config.url, data=_build_envelope(operation, params), timeout=self._config.timeout)
        return _parse_response(raw, operation)

    def login(self) -> Session:
        """Opens a session (takes one license seat). An existing session is logged out first."""
        self.logout()
        cfg = self._config
        password = hashlib.md5(cfg.password.encode("utf-8")).hexdigest() if cfg.password_md5 else cfg.password
        response = self._post(
            "login",
            [
                ("Client", "string", cfg.client),
                ("Language", "string", cfg.language),
                ("DBServer", "string", cfg.db_server),
                ("DBName", "string", cfg.db_name),
                ("ApplicationServer", "string", cfg.app_server),
                ("Username", "string", cfg.username),
                ("Password", "string", password),
                ("Encrypted", "boolean", False),
                ("Compression", "boolean", False),
                ("LCheck", "string", ""),
                ("VKey", "string", ""),
            ],
        )
        if response.text("Success").strip().lower() not in ("true", "1"):
            raise LoginError(response.text("ErrorMessage").strip())
        session_id = response.text("SessionId").strip()
        if not session_id:
            raise ProtocolError("login yanıtında SessionId yok")
        self._session = Session(session_id, response.text("SecurityKey").strip(), response.text("ContactNum").strip())
        return self._session

    def logout(self) -> bool:
        """Best-effort logout that never raises; returns the server's answer."""
        session, self._session = self._session, None
        if session is None:
            return False
        try:
            response = self._post("logout", [("SessionId", "string", session.session_id)])
        except Exception:
            return False
        return (response.node.text or "").strip().lower() in ("true", "1")

    def _require_session(self) -> Session:
        return self._session or self.login()

    def list_services(self) -> list[str]:
        """Raw ``NAME_CLASS`` items the user may call; empty also when the session expired."""
        session = self._require_session()
        return self._post("listServices", [("SessionId", "string", session.session_id)]).items()

    def call(
        self,
        service_id: str,
        params: Sequence[object] | str = (),
        *,
        permanent: bool = False,
        extra_variables: str = "",
    ) -> CallResult:
        """Runs a service registered in WSRT01. ``SYSStatus != 0`` is returned, not raised.

        ``params`` is a sequence of positional values or a ready ``<PARAMETERS>`` XML string
        (needed for ``TABLE``/``VECTOR`` parameters). ``permanent`` keeps the server-side
        transaction open for the next call; ``extra_variables`` is a comma-separated list of
        TROIA variables to return.
        """
        session = self._require_session()
        request_id = next(self._request_ids)
        response = self._post(
            "callService",
            [
                ("SessionId", "string", session.session_id),
                ("SecurityKey", "string", session.security_key),
                ("ServiceId", "string", service_id),
                ("Parameters", "string", params if isinstance(params, str) else build_parameters(params)),
                ("Compressed", "boolean", False),
                ("Permanent", "boolean", permanent),
                ("ExtraVariables", "string", extra_variables),
                ("RequestId", "int", request_id),
            ],
        )
        status_text = response.text("SYSStatus").strip()
        sys_status = int(status_text) if status_text.lstrip("-").isdigit() else 0
        returned_id = response.text("RequestId").strip()
        return CallResult(
            ok=sys_status == 0,
            value=response.string_response("Response"),
            messages=response.string_response("Messages"),
            extra_variables=response.string_response("ExtraVariables"),
            sys_status=sys_status,
            sys_status_error=response.string_response("SYSStatusError").strip(),
            request_id=int(returned_id) if returned_id.isdigit() and returned_id != "0" else request_id,
        )
