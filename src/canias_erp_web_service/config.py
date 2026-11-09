"""Settings from a ``.env`` file and ``CANIAS_*`` environment variables (environment wins)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .client import CaniasError, WebServiceConfig

_REQUIRED = (
    "CANIAS_WS_URL",
    "CANIAS_WS_CLIENT",
    "CANIAS_WS_DB_SERVER",
    "CANIAS_WS_DB_NAME",
    "CANIAS_WS_APP_SERVER",
    "CANIAS_WS_USER",
    "CANIAS_WS_PASSWORD",
)


class ConfigError(CaniasError):
    """A setting is missing or invalid."""


def load_env(path: str | Path | None = ".env") -> dict[str, str]:
    """``KEY=VALUE`` lines from ``path`` (if the file exists), overlaid with ``CANIAS_*`` environment variables."""
    values: dict[str, str] = {}
    if path is not None and Path(path).is_file():
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ConfigError(f"{path} UTF-8 olarak kaydedilmeli (Not Defteri: Farklı Kaydet > UTF-8)") from exc
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[key.strip()] = value
    values.update({k: v for k, v in os.environ.items() if k.startswith("CANIAS_")})
    return values


def config_from_env(env: Mapping[str, str] | None = None) -> WebServiceConfig:
    """Builds the connection settings from ``env`` (default: ``CANIAS_*`` environment variables only)."""
    if env is None:
        env = load_env(None)
    missing = [key for key in _REQUIRED if not env.get(key, "").strip()]
    if missing:
        raise ConfigError("eksik ayar: " + ", ".join(missing))
    try:
        timeout = float(env.get("CANIAS_WS_TIMEOUT", "30") or 30)
    except ValueError:
        timeout = 0.0
    if timeout <= 0:
        raise ConfigError("CANIAS_WS_TIMEOUT pozitif bir sayı (saniye) olmalı")
    mode = env.get("CANIAS_WS_PASSWORD_MODE", "plain").strip().lower()
    if mode not in ("plain", "md5"):
        raise ConfigError("CANIAS_WS_PASSWORD_MODE plain veya md5 olmalı")
    return WebServiceConfig(
        url=env["CANIAS_WS_URL"].strip().removesuffix("?wsdl").removesuffix("?WSDL"),
        client=env["CANIAS_WS_CLIENT"].strip(),
        language=env.get("CANIAS_WS_LANGUAGE", "T").strip() or "T",
        db_server=env["CANIAS_WS_DB_SERVER"].strip(),
        db_name=env["CANIAS_WS_DB_NAME"].strip(),
        app_server=env["CANIAS_WS_APP_SERVER"].strip(),
        username=env["CANIAS_WS_USER"].strip(),
        password=env["CANIAS_WS_PASSWORD"],
        password_md5=mode == "md5",
        timeout=timeout,
    )
