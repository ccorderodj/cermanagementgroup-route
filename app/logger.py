"""
Logging estructurado en JSON.

Un solo formato para toda la aplicación, para que lo que sale por stdout sea
directamente ingerible por un agregador de logs sin tener que parsear texto
libre.
"""

import logging
from datetime import datetime, timezone

from pythonjsonlogger.json import JsonFormatter

from app.config import settings


class CustomJsonFormatter(JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        if not log_record.get("timestamp"):
            # `datetime.utcnow()` está deprecado desde Python 3.12: devuelve un
            # datetime naive que aparenta ser UTC, y esa ambigüedad es la que
            # se está quitando de todo el proyecto (D10, AUD-BE-025).
            log_record["timestamp"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )

        if log_record.get("level"):
            log_record["level"] = log_record["level"].upper()
        else:
            log_record["level"] = record.levelname


logger = logging.getLogger()

_handler = logging.StreamHandler()
_handler.setFormatter(
    CustomJsonFormatter("%(timestamp)s %(level)s %(message)s %(module)s %(funcName)s")
)

logger.addHandler(_handler)
logger.setLevel(settings.LOG_LEVEL)
