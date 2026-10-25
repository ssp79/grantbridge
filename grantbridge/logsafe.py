"""Logging that cannot leak secrets or private data.

install() puts a redacting formatter on every handler of the root logger and of
Streamlit's loggers. The formatter runs on the final text, so secrets in a
message, in its arguments, or in an exception traceback are all replaced with
[REDACTED], and email addresses with [email]. Chatty HTTP client libraries are
held at WARNING so request details never reach the log at INFO.
"""

from __future__ import annotations

import logging

from grantbridge import guards
from grantbridge.config import known_secrets

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
QUIET = ("httpx", "httpcore", "openai", "urllib3")


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return guards.redact_for_logs(super().format(record), known_secrets())


def install(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    loggers = [root] + [logging.getLogger(name) for name in list(logging.root.manager.loggerDict)
                        if name.startswith("streamlit")]
    for logger in loggers:
        for handler in logger.handlers:
            if not isinstance(handler.formatter, RedactingFormatter):
                handler.setFormatter(RedactingFormatter(FORMAT))
    root.setLevel(level)
    for name in QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
