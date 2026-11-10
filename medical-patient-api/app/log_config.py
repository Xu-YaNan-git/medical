"""Application logging that survives Uvicorn's default config.

Docker starts the API as ``uvicorn app.main:app``. That default dictConfig only
attaches handlers to ``uvicorn`` (stderr) and ``uvicorn.access`` (stdout).
Loggers under ``app.*`` propagate to the root logger, which stays at WARNING
with no handler, so ``logger.info`` — including ``consult_llm`` — is dropped.

``configure_app_logging`` gives ``app`` its own INFO handler on stdout.
It is idempotent and does not log request bodies, keys, or tokens.
"""

from __future__ import annotations

import logging
import sys

_HANDLER_MARK = "_patient_api_stdout"


def configure_app_logging() -> None:
    """Send ``app.*`` INFO (and above) to stdout, once."""
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, _HANDLER_MARK, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        setattr(handler, _HANDLER_MARK, True)
        logger.addHandler(handler)
    # Stop at this logger so root's WARNING lastResort does not drop INFO
    # or print the same WARNING twice.
    logger.propagate = False
