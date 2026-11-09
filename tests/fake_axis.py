"""Minimal AXIS-style SOAP server for tests: canned responses per operation, WSDL on GET."""

from __future__ import annotations

import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from canias_erp_web_service import WebServiceConfig

PASSWORD = "PASSWORD-789"
SESSION_ID = "SESSION-123"
SECURITY_KEY = "KEY-456"

_ENVELOPE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"'
    ' xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    ' xmlns:soapenc="http://schemas.xmlsoap.org/soap/encoding/"><soapenv:Body>{}</soapenv:Body></soapenv:Envelope>'
)
LOGIN_OK = _ENVELOPE.format(
    '<ns1:loginResponse xmlns:ns1="http://webservice.ias.com"><loginReturn href="#id0"/></ns1:loginResponse>'
    '<multiRef id="id0" xmlns:ns2="http://webservice.ias.com" xsi:type="ns2:LoginResponse">'
    f'<SessionId xsi:type="xsd:string">{SESSION_ID}</SessionId><ErrorMessage xsi:nil="true"/>'
    '<ContactNum xsi:type="xsd:string">42</ContactNum><Success xsi:type="xsd:boolean">true</Success>'
    f'<SecurityKey xsi:type="xsd:string">{SECURITY_KEY}</SecurityKey></multiRef>'
)
LOGIN_LICENSE_FULL = _ENVELOPE.format(
    '<ns1:loginResponse xmlns:ns1="http://webservice.ias.com"><loginReturn>'
    '<SessionId xsi:nil="true"/><ErrorMessage xsi:type="xsd:string">login error: 15</ErrorMessage>'
    '<Success xsi:type="xsd:boolean">false</Success></loginReturn></ns1:loginResponse>'
)
LIST = _ENVELOPE.format(
    '<ns1:listServicesResponse xmlns:ns1="http://webservice.ias.com">'
    '<listServicesReturn xsi:type="soapenc:Array"><item>PING_TESTWS</item><item>EINV_IMPORT_EINVWS</item>'
    "</listServicesReturn></ns1:listServicesResponse>"
)
CALL_OK = _ENVELOPE.format(
    '<ns1:callServiceResponse xmlns:ns1="http://webservice.ias.com"><callServiceReturn href="#id0"/>'
    "</ns1:callServiceResponse>"
    '<multiRef id="id0"><Response href="#id1"/><Messages href="#id2"/><ExtraVariables href="#id2"/>'
    '<SYSStatus xsi:type="xsd:int">0</SYSStatus><SYSStatusError xsi:nil="true"/>'
    '<RequestId xsi:type="xsd:int">1</RequestId></multiRef>'
    '<multiRef id="id1"><Value>&lt;RESULT&gt;OK&lt;/RESULT&gt;</Value><Comressed>false</Comressed></multiRef>'
    '<multiRef id="id2"><Value></Value><Comressed>false</Comressed></multiRef>'
)
CALL_FAILED = CALL_OK.replace(">0</SYSStatus>", ">1</SYSStatus>")
FAULT = _ENVELOPE.format(
    "<soapenv:Fault><faultcode>soapenv:Server</faultcode><faultstring>boom</faultstring></soapenv:Fault>"
)
LOGOUT = _ENVELOPE.format(
    '<ns1:logoutResponse xmlns:ns1="http://webservice.ias.com"><logoutReturn>true</logoutReturn>'
    "</ns1:logoutResponse>"
)
WSDL_V2 = (
    '<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"><wsdl:portType name="CaniasWebService">'
    '<wsdl:operation name="login"/><wsdl:operation name="logout"/>'
    '<wsdl:operation name="listServices"/><wsdl:operation name="callService"/>'
    "</wsdl:portType></wsdl:definitions>"
)


def config_for(url: str) -> WebServiceConfig:
    return WebServiceConfig(url, "00", "T", "DBS", "DB", "APP", "WSUSER", PASSWORD, timeout=5)


class FakeAxis:
    """Answers each SOAP operation with ``responses[operation]`` (a body, or ``(status, body)``)."""

    def __init__(self, **responses: str | tuple[int, str]) -> None:
        merged = {"logout": LOGOUT, **responses}
        self.responses = {op: (200, r) if isinstance(r, str) else r for op, r in merged.items()}
        self.calls: list[str] = []
        self.bodies: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._reply(200, WSDL_V2)

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
                operation = re.search(r"<web:(\w+)>", body).group(1)
                fake.calls.append(operation)
                fake.bodies.append(body)
                self._reply(*fake.responses[operation])

            def _reply(self, status: int, payload: str) -> None:
                data = payload.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/xml; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/CaniasWS-v2/services/CaniasWebService"

    def config(self) -> WebServiceConfig:
        return config_for(self.url)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
