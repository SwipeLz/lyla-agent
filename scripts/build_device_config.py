"""Build a ready-to-flash /config.json for the ESP32 SD card.

Mirrors the logic of POST /devices/pair (app/api/devices.py) but works
offline by reading the SQLAlchemy session directly. Writes to
``firmware/Lyla-Taskbot/sd_template/config.json`` so the ESP can pick
it up after the operator copies the SD template folder onto the card.

Usage:
    python -m scripts.build_device_config                       # auto-pick latest paired device
    python -m scripts.build_device_config --device-code TASKBOT-XXXX
    python -m scripts.build_device_config --wifi-ssid Foo --wifi-password Bar
    python -m scripts.build_device_config --base-url https://lyla.example.com
    python -m scripts.build_device_config --update-env          # also write DEVICE_API_TOKEN to .env (ADR-11)

Default base_url policy:
    - If settings.base_url starts with http://127.0.0.1 or http://localhost,
      auto-detect the host's LAN IP and substitute it (so the ESP can reach
      the backend over WiFi).
    - Otherwise use settings.base_url as-is (production, AWS, Cloudflare
      tunnel, etc).
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.models.device import Device
from app.models.user import User


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_PATH = (
    _PROJECT_ROOT / "firmware" / "Lyla-Taskbot" / "sd_template" / "config.json"
)
_ENV_PATH = _PROJECT_ROOT / ".env"


def _detect_lan_ip() -> str | None:
    """Return the host's LAN IP without sending any packet.

    Uses the connected-UDP-socket trick: connecting an UDP socket only
    asks the OS routing table which interface would be used to reach
    the destination; no datagram is actually emitted.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
        return None
    except OSError:
        return None
    finally:
        s.close()


def _resolve_base_url(override: str | None) -> tuple[str, str]:
    """Return ``(resolved_url, source)`` where source describes the choice."""
    if override:
        return override.rstrip("/"), "override"

    raw = (settings.base_url or "").rstrip("/")
    is_localhost = raw.startswith("http://127.0.0.1") or raw.startswith(
        "http://localhost"
    )
    if not is_localhost:
        return raw, "settings.base_url"

    lan = _detect_lan_ip()
    if lan is None:
        return raw, "settings.base_url (no LAN IP detected)"

    port = ""
    if ":" in raw.split("//", 1)[-1]:
        host_with_port = raw.split("//", 1)[-1]
        port = ":" + host_with_port.split(":", 1)[-1]
    return f"http://{lan}{port}", f"LAN auto-detect ({raw} -> {lan})"


def _pick_device(
    db, *, device_code: str | None
) -> tuple[Device, User]:
    user = (
        db.query(User).filter(User.email == settings.mvp_user_email).one_or_none()
    )
    if user is None:
        raise SystemExit(
            f"ERROR: MVP user not found ({settings.mvp_user_email}). "
            "Run `python -m scripts.seed_dev` first."
        )

    if device_code is not None:
        device = (
            db.query(Device)
            .filter(Device.device_code == device_code, Device.user_id == user.id)
            .one_or_none()
        )
        if device is None:
            raise SystemExit(
                f"ERROR: device_code {device_code!r} not found for {user.email!r}."
            )
        if not device.api_token:
            raise SystemExit(
                f"ERROR: device {device_code} has no api_token. "
                "Re-pair via POST /devices/pair to mint one."
            )
        return device, user

    candidates = (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.api_token.is_not(None))
        .order_by(Device.created_at.desc())
        .all()
    )
    if not candidates:
        raise SystemExit(
            "ERROR: no paired device with a token. "
            "Run the dashboard `Pair New Device` flow first."
        )
    return candidates[0], user


def _build_config_json(
    *,
    user: User,
    device: Device,
    base_url: str,
    wifi_ssid: str,
    wifi_password: str,
) -> dict:
    return {
        "user_id": user.id,
        "device_id": device.id,
        "device_code": device.device_code,
        "device_token": device.api_token,
        "base_url": base_url,
        "wifi": {
            "ssid": wifi_ssid,
            "password": wifi_password,
        },
        "firmware_version": "0.1.0",
    }


def _patch_env_token(token: str) -> bool:
    """Set DEVICE_API_TOKEN in .env. Returns True if file was modified."""
    if not _ENV_PATH.exists():
        print(f"  WARN: {_ENV_PATH} not found, skipping --update-env.", file=sys.stderr)
        return False
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_value = f"DEVICE_API_TOKEN={token}"
    found = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("DEVICE_API_TOKEN=") or stripped.startswith(
            "#DEVICE_API_TOKEN="
        ):
            lines[i] = new_value
            found = True
            break
    if not found:
        lines.append(new_value)
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_device_config",
        description=(
            "Generate a ready-to-flash /config.json for the ESP32 SD card "
            "by reusing /devices/pair logic against the local DB."
        ),
    )
    parser.add_argument(
        "--device-code",
        default=None,
        help="Force a specific device (default: latest paired device with a token).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override settings.base_url (e.g. https://lyla.example.com).",
    )
    parser.add_argument(
        "--wifi-ssid",
        default="",
        help="Pre-fill wifi.ssid (default: empty, fill manually).",
    )
    parser.add_argument(
        "--wifi-password",
        default="",
        help="Pre-fill wifi.password (default: empty, fill manually).",
    )
    parser.add_argument(
        "--output",
        default=str(_OUTPUT_PATH),
        help=f"Output path (default: {_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--update-env",
        action="store_true",
        help="Also write DEVICE_API_TOKEN to .env (ADR-11 1-device convention).",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        device, user = _pick_device(db, device_code=args.device_code)
    finally:
        db.close()

    base_url, base_url_source = _resolve_base_url(args.base_url)

    cfg = _build_config_json(
        user=user,
        device=device,
        base_url=base_url,
        wifi_ssid=args.wifi_ssid,
        wifi_password=args.wifi_password,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    print("Generated /config.json:")
    print(f"  output     : {out_path}")
    print(f"  user       : {user.email} ({user.id})")
    print(f"  device     : {device.device_code} ({device.id})")
    print(f"  token      : {device.api_token[:12]}... ({len(device.api_token)} chars)")
    print(f"  base_url   : {base_url}  [{base_url_source}]")

    wifi_filled = bool(args.wifi_ssid)
    print(
        f"  wifi.ssid  : {args.wifi_ssid!r}"
        + ("" if wifi_filled else "   <-- FILL THIS IN before flashing")
    )
    print(f"  wifi.pass  : {'***' if args.wifi_password else '(empty)'}")
    print()

    if args.update_env:
        modified = _patch_env_token(device.api_token)
        if modified:
            print(f"  .env       : DEVICE_API_TOKEN updated in {_ENV_PATH}")
            print("  -> restart uvicorn for the new token to take effect")
    else:
        print("ADR-11 reminder (1-device MVP convention):")
        print(
            "  Set DEVICE_API_TOKEN in your backend .env to match the device token "
            "above so the same X-Device-Token works for /agent/audio* and "
            "/devices/{code}/* endpoints. Either:"
        )
        print(f"    DEVICE_API_TOKEN={device.api_token}")
        print("  ...or re-run this script with --update-env to patch .env automatically.")

    print()
    print("Next steps:")
    print(f"  1. Edit {out_path} and fill wifi.ssid + wifi.password (if not already).")
    print("  2. Format SD card as FAT32, copy this file to /config.json on the SD root.")
    print(
        f"  3. Copy {Path('firmware/Lyla-Taskbot/sd_template/sounds/')} to /sounds/ on the SD."
    )
    print("  4. Insert SD into Freenove on-board slot, power on the ESP32.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
