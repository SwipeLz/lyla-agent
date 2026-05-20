"""Generate the scrypt-hashed value for ``DASHBOARD_PASSWORD_SCRYPT``.

Usage::

    python -m scripts.hash_dashboard_password
    python -m scripts.hash_dashboard_password --password admin

Prints a single line ``<salt_hex>:<hash_hex>`` ready to paste into ``.env``.
The plaintext password is never logged or persisted; the helper is the only
place plaintext touches memory before being discarded.

This script depends on ``app.auth.passwords`` (Phase 12 Wave 2). Running it
before Wave 2 is implemented raises ImportError.
"""
from __future__ import annotations

import argparse
import getpass
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.hash_dashboard_password",
        description=(
            "Generate a scrypt-hashed password value for "
            "DASHBOARD_PASSWORD_SCRYPT in .env."
        ),
    )
    parser.add_argument(
        "--password",
        default=None,
        help=(
            "Plaintext password. Avoid passing on real shells (visible in "
            "history). Omit to read from stdin via getpass."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    plaintext = args.password
    if plaintext is None:
        plaintext = getpass.getpass("Dashboard password: ")
    if not plaintext:
        print("error: password is empty", file=sys.stderr)
        return 1

    from app.auth.passwords import hash_password

    print(hash_password(plaintext))
    return 0


if __name__ == "__main__":
    sys.exit(main())
