import os
from pathlib import Path


def _load_dotenv(path: Path = Path(__file__).parent.parent / ".env") -> None:
    """Read KEY=value lines from .env without overriding real env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
