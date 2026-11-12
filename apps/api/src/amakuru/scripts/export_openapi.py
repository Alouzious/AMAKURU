"""Export OpenAPI JSON for TypeScript client generation."""

from __future__ import annotations

import json
from pathlib import Path

from amakuru.main import create_app


def main() -> None:
    app = create_app()
    schema = app.openapi()
    repo = Path(__file__).resolve().parents[5]
    out_dir = repo / "docs" / "api"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "openapi.json"
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    client_dir = repo / "packages" / "api-client"
    client_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "openapi.json").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"Wrote {client_dir / 'openapi.json'}")


if __name__ == "__main__":
    main()
