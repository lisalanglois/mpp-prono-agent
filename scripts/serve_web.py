#!/usr/bin/env python3
"""Lance le site web des pronos CDM 2026."""

import http.server
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PORT = 8765


def main() -> None:
    export = ROOT / "scripts" / "export_web.py"
    subprocess.run([sys.executable, str(export)], check=True)

    os.chdir(WEB)
    handler = http.server.SimpleHTTPRequestHandler
    url = f"http://localhost:{PORT}"
    print(f"\n🌐 Site prêt → {url}")
    print("   Ctrl+C pour arrêter\n")
    webbrowser.open(url)
    http.server.HTTPServer(("", PORT), handler).serve_forever()


if __name__ == "__main__":
    main()
