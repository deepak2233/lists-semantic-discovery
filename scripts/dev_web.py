"""Development entrypoint accepting the common host/port preview-server flags."""

import argparse
import os
import sys
from pathlib import Path

import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--strictPort", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    origins = os.getenv("LISTS_WEB_ORIGINS", "")
    origin = f"http://{args.host}:{args.port}"
    os.environ["LISTS_WEB_ORIGINS"] = ",".join(filter(None, [origins, origin]))
    uvicorn.run("app:app", host=args.host, port=args.port, access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
