"""canias-erp-web-service-check: exit code, report and secrets."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from canias_erp_web_service import check
from fake_axis import CALL_FAILED, CALL_OK, LIST, LOGIN_OK, PASSWORD, SECURITY_KEY, SESSION_ID, FakeAxis


class CheckCommandTest(unittest.TestCase):
    def run_command(self, fake: FakeAxis, *args: str) -> tuple[int, str, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        env_file = directory / ".env"
        env_file.write_text(
            f"CANIAS_WS_URL={fake.url}?wsdl\nCANIAS_WS_CLIENT=00\nCANIAS_WS_DB_SERVER=DBS\nCANIAS_WS_DB_NAME=DB\n"
            f"CANIAS_WS_APP_SERVER=APP\nCANIAS_WS_USER=WSUSER\nCANIAS_WS_PASSWORD={PASSWORD}\n",
            encoding="utf-8",
        )
        # Real CANIAS_* variables would override the .env file.
        isolated = {k: v for k, v in os.environ.items() if not k.startswith("CANIAS_")}
        out = io.StringIO()
        with mock.patch.dict(os.environ, isolated, clear=True), redirect_stdout(out):
            code = check.main(["--env", str(env_file), "--report-dir", str(directory), *args])
        return code, out.getvalue(), directory

    def serve(self, **responses: str) -> FakeAxis:
        fake = FakeAxis(**responses)
        self.addCleanup(fake.close)
        return fake

    def test_failed_test_service_fails_the_run_and_still_logs_out(self) -> None:
        fake = self.serve(login=LOGIN_OK, listServices=LIST, callService=CALL_FAILED)
        code, _out, _directory = self.run_command(fake, "--service", "PING")
        self.assertEqual(code, 1)
        self.assertEqual(fake.calls[-1], "logout")

    def test_successful_run_writes_a_report_without_secrets(self) -> None:
        fake = self.serve(login=LOGIN_OK, listServices=LIST, callService=CALL_OK)
        code, out, directory = self.run_command(fake, "--service", "PING", "--param", "1")
        self.assertEqual(code, 0)
        (report_file,) = directory.glob("check-*.json")
        report_text = report_file.read_text(encoding="utf-8")
        self.assertTrue(json.loads(report_text)["ok"])
        for secret in (PASSWORD, SESSION_ID, SECURITY_KEY):
            self.assertNotIn(secret, out)
            self.assertNotIn(secret, report_text)


if __name__ == "__main__":
    unittest.main()
