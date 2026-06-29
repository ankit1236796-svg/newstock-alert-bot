import logging
import sys
from typing import Final

_RESERVED_LOG_RECORD_FIELDS: Final[frozenset[str]] = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None))
)


class KeyValueFormatter(logging.Formatter):
    """Small structured formatter suitable for container logs."""

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in sorted(record.__dict__.items()):
            if key not in _RESERVED_LOG_RECORD_FIELDS and not key.startswith("_"):
                base[key] = value
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)
        return " ".join(f"{key}={value!r}" for key, value in base.items())


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(KeyValueFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
