from __future__ import annotations

import argparse

from .config import DEFAULT_GUI_PORT
from .server import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the VLLM Engine GUI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=DEFAULT_GUI_PORT, help="TCP port to bind.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
