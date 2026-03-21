"""Entry point for the fpms2 state service.

Usage:
    python -m wlanpi_fpms2          # default: host=127.0.0.1, port=8765
    python -m wlanpi_fpms2 --port 8765 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="wlanpi-fpms2 state service"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    import uvicorn
    from wlanpi_fpms2.state.app import create_app

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
