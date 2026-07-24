"""Logging configuration with secret masking."""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.settings import get_settings

# Patterns to mask in logs
_KEY_PATTERNS = [
    # Bearer tokens
    (re.compile(r"(Bearer\s+)([a-zA-Z0-9\-_]{8})[a-zA-Z0-9\-_]+"), r"\1\2****"),
    # API keys like sk-xxx, nvapi-xxx
    (re.compile(r"(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]+"), r"\1****"),
    (re.compile(r"(nvapi-[a-zA-Z0-9]{4})[a-zA-Z0-9]+"), r"\1****"),
    (re.compile(r"(sk-gw-client-[a-zA-Z0-9]{4})[a-zA-Z0-9]+"), r"\1****"),
    # Authorization headers
    (re.compile(r'(api_key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9\-_]{4})[a-zA-Z0-9\-_]+'), r"\1\2****"),
]


class SecretMaskingFilter(logging.Filter):
    """Filter that masks API keys and secrets in log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in _KEY_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args:
            if isinstance(record.args, dict):
                for key, val in record.args.items():
                    if isinstance(val, str):
                        for pattern, replacement in _KEY_PATTERNS:
                            val = pattern.sub(replacement, val)
                        record.args[key] = val
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    pattern.sub(replacement, arg) if isinstance(arg, str) else arg
                    for arg, (pattern, replacement) in zip(record.args, _KEY_PATTERNS * len(record.args))
                )
        return True


def setup_logging(log_dir: Path | None = None, level: str | None = None) -> None:
    """Configure application logging with secret masking and file rotation."""
    settings = get_settings()
    log_level = level or settings.log_level

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(SecretMaskingFilter())
    root_logger.addHandler(console)

    # File handler (if log dir provided)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "gateway.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SecretMaskingFilter())
        root_logger.addHandler(file_handler)


def mask_key(key: str) -> str:
    """Mask an API key for display: show first 6 and last 4 chars."""
    if not key:
        return ""
    if len(key) <= 12:
        return "****"
    return key[:6] + "****" + key[-4:]
