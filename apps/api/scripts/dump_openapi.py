"""Dump déterministe du schéma OpenAPI (source du client TS + drift check)."""

import json

from augura_api.main import create_app


def main() -> None:
    schema = create_app().openapi()
    print(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
