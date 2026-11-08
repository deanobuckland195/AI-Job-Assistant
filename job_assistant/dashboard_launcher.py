"""Launch Streamlit on localhost, independently of the caller's directory/config."""

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

from . import storage


def main(argv=None):
    parser = argparse.ArgumentParser(description="Launch the local application dashboard")
    parser.add_argument("--database", type=Path, help="Explicit local SQLite path; default is the existing application database")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if importlib.util.find_spec("streamlit") is None:
        print("Dashboard dependencies are missing. Run: python -m pip install -r requirements-dashboard.txt")
        return 1
    project = Path(__file__).resolve().parent.parent
    path = args.database or Path(os.environ.get("AI_JOB_ASSISTANT_DATABASE", str(storage.DEFAULT_DATABASE)))
    env = dict(os.environ)
    env["AI_JOB_ASSISTANT_DATABASE"] = str(path.expanduser().resolve())
    command = [sys.executable, "-m", "streamlit", "run", str(project / "dashboard.py"),
               "--server.address=127.0.0.1", f"--server.port={args.port}", "--server.headless=true",
               "--browser.gatherUsageStats=false", "--server.enableCORS=true", "--server.enableXsrfProtection=true",
               "--client.showErrorDetails=none", "--client.toolbarMode=minimal"]
    try:
        return subprocess.run(command, cwd=project, env=env).returncode
    except KeyboardInterrupt:
        return 130
    except OSError:
        print("Could not launch the local dashboard. Check the Python environment and permissions.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
