"""CaniasWebServiceClient against a fake AXIS endpoint: parsing, errors and license-seat release."""

from __future__ import annotations

import socket
import threading
import unittest

from canias_erp_web_service import CaniasWebServiceClient, LoginError, Session, SoapFault, TransportError
from fake_axis import (
    CALL_OK,
    FAULT,
    LIST,
    LOGIN_LICENSE_FULL,
    LOGIN_OK,
    PASSWORD,
    SECURITY_KEY,
    SESSION_ID,
    FakeAxis,
    config_for,
)


def _http_ok(body: str) -> bytes:
    data = body.encode("utf-8")
    head = f"HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n"
    return head.encode("ascii") + data


def _read_request(conn: socket.socket) -> None:
    data = b""
    while b"\r\n\r\n" not in data:
        data += conn.recv(65536)
    head, _, body = data.partition(b"\r\n\r\n")
    length = next(
        (int(line.split(b":", 1)[1]) for line in head.split(b"\r\n") if line.lower().startswith(b"content-length:")), 0
    )
    while len(body) < length:
        body += conn.recv(65536)


class CaniasWebServiceClientTest(unittest.TestCase):
    def serve(self, **responses: str | tuple[int, str]) -> FakeAxis:
        fake = FakeAxis(**responses)
        self.addCleanup(fake.close)
        return fake

    def raw_server(self, *replies: bytes) -> str:
        """Answers the next connections with the given raw bytes, one reply per connection."""
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        self.addCleanup(listener.close)

        def serve() -> None:
            for reply in replies:
                conn, _addr = listener.accept()
                with conn:
                    _read_request(conn)  # unread data makes Windows reset the connection on close
                    conn.sendall(reply)
                    conn.shutdown(socket.SHUT_WR)

        threading.Thread(target=serve, daemon=True).start()
        host, port = listener.getsockname()
        return f"http://{host}:{port}/ws"

    def test_session_round_trip_resolves_multirefs_and_logs_out(self) -> None:
        fake = self.serve(login=LOGIN_OK, listServices=LIST, callService=CALL_OK)
        with CaniasWebServiceClient(fake.config()) as client:
            session = client.login()
            services = client.list_services()
            result = client.call("PING", ["a<b"])
        self.assertEqual((session.session_id, session.security_key), (SESSION_ID, SECURITY_KEY))
        self.assertEqual(services, ["PING_TESTWS", "EINV_IMPORT_EINVWS"])
        self.assertTrue(result.ok)
        self.assertEqual(result.value, "<RESULT>OK</RESULT>")
        self.assertIn("&lt;PARAMETERS&gt;&lt;PARAM&gt;a&amp;lt;b", fake.bodies[2])
        self.assertEqual(fake.calls, ["login", "listServices", "callService", "logout"])
        self.assertIn(SESSION_ID, fake.bodies[-1])

    def test_license_error_exposes_code_and_sends_no_logout(self) -> None:
        fake = self.serve(login=LOGIN_LICENSE_FULL)
        with self.assertRaises(LoginError) as ctx, CaniasWebServiceClient(fake.config()) as client:
            client.login()
        self.assertEqual(ctx.exception.code, 15)
        self.assertEqual(fake.calls, ["login"])

    def test_failed_call_still_releases_the_session(self) -> None:
        fake = self.serve(login=LOGIN_OK, callService=(500, FAULT))
        with self.assertRaises(SoapFault), CaniasWebServiceClient(fake.config()) as client:
            client.call("PING")
        self.assertEqual(fake.calls, ["login", "callService", "logout"])

    def test_malformed_http_is_transport_error_and_logout_never_raises(self) -> None:
        url = self.raw_server(_http_ok(LOGIN_OK), b"NOT-HTTP\r\n\r\n", b"NOT-HTTP\r\n\r\n")
        client = CaniasWebServiceClient(config_for(url))
        client.login()
        with self.assertRaises(TransportError):
            client.list_services()
        self.assertFalse(client.logout())

    def test_repr_hides_password_and_session_secrets(self) -> None:
        for text in (repr(config_for("http://host/ws")), repr(Session(SESSION_ID, SECURITY_KEY, "42"))):
            for secret in (PASSWORD, SESSION_ID, SECURITY_KEY):
                self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
