"""Structured application logs with secret filtering before rendering."""

import logging

import structlog

from app.acp.security import scrub, scrub_data


def configure_logging() -> None:
    class SecretFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.msg = scrub(record.getMessage())
            record.args = ()
            return True

    handler = logging.StreamHandler()
    handler.addFilter(SecretFilter())
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                lambda _logger, _method, event: scrub_data(event),
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=[structlog.stdlib.add_log_level, structlog.processors.TimeStamper(fmt="iso")],
        )
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # Access logs include websocket query tokens. Application middleware can log paths only.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
