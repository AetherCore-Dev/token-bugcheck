"""Entry point — run the audit server."""

import logging
import os
import sys

import uvicorn

from rugcheck.config import load_config
from rugcheck.server import create_app


def main() -> None:
    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    # In production with multiple workers, uvicorn forks — each worker gets
    # its own in-memory cache and circuit breaker.  This is acceptable for
    # our use-case (cache is short-TTL, breaker recovers quickly).
    workers = int(os.getenv("UVICORN_WORKERS", "1"))
    limit_concurrency = int(os.getenv("UVICORN_LIMIT_CONCURRENCY", "0")) or None

    if workers > 1:
        # Multi-worker mode requires passing the app as an import string
        uvicorn.run(
            "rugcheck.server:create_app",
            factory=True,
            host=config.host,
            port=config.port,
            workers=workers,
            limit_concurrency=limit_concurrency,
            log_level=config.log_level.lower(),
        )
    else:
        app = create_app(config)
        uvicorn.run(
            app,
            host=config.host,
            port=config.port,
            limit_concurrency=limit_concurrency,
            log_level=config.log_level.lower(),
        )


if __name__ == "__main__":
    main()
