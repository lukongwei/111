"""Run the local dashboard server."""

from pathlib import Path
import argparse

from .server import serve


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local AI Workspace dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(Path(__file__).resolve().parents[2], args.host, args.port)

