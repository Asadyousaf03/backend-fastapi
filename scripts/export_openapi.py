from __future__ import annotations

import json
from pathlib import Path

from main import app


def main() -> None:
    out = Path("openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
