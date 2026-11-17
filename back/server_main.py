"""PosePro v4: run this file and open http://localhost:3000."""
import os
from pathlib import Path

from service import create_app, main


def load_env():
    """Load optional .env from the project root; real environment wins."""
    path = Path(__file__).resolve().parent.parent / '.env'
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"\''))


if __name__ == '__main__':
    load_env()
    main()
