"""Expose an already-failed check's captured output through the Actions API."""
from pathlib import Path
import sys


if __name__ == '__main__':
    detail = Path(sys.argv[1]).read_bytes().decode('utf-8', errors='replace')[-24000:]
    detail = detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::error title=Acceptance failure details::{detail}', flush=True)
