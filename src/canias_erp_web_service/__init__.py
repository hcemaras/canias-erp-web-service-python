"""Python client for the CANIAS ERP (caniasERP, TROIA) Web Service 2.0."""

from .client import (
    LOGIN_ERRORS,
    CallResult,
    CaniasError,
    CaniasWebServiceClient,
    LoginError,
    ProtocolError,
    Session,
    SoapFault,
    TransportError,
    WebServiceConfig,
    build_parameters,
    fetch_wsdl_operations,
)
from .config import ConfigError, config_from_env, load_env

__version__ = "0.1.0"

__all__ = [
    "LOGIN_ERRORS",
    "CallResult",
    "CaniasError",
    "CaniasWebServiceClient",
    "ConfigError",
    "LoginError",
    "ProtocolError",
    "Session",
    "SoapFault",
    "TransportError",
    "WebServiceConfig",
    "__version__",
    "build_parameters",
    "config_from_env",
    "fetch_wsdl_operations",
    "load_env",
]
