"""Deterministic dump of the OpenAPI schema (source of the TS client + drift check)."""

import json

from augura_api.main import create_app


def main() -> None:
    schema = create_app().openapi()
    print(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
