from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGE_PATH = ROOT / "data" / "dashboard.png"
DEFAULT_ENV_PATH = ROOT / ".env"


class SlackError(RuntimeError):
    pass


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_dotenv(path: Path = DEFAULT_ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def slack_api(method: str, token: str, fields: dict[str, Any]) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SlackError(f"Slack HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SlackError(f"Slack network error: {exc}") from exc

    if not payload.get("ok"):
        raise SlackError(f"Slack API {method} failed: {payload.get('error') or payload}")
    return payload


def upload_bytes(upload_url: str, image_bytes: bytes) -> None:
    request = urllib.request.Request(
        upload_url,
        data=image_bytes,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status < 200 or response.status >= 300:
                raise SlackError(f"Slack upload returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SlackError(f"Slack upload HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SlackError(f"Slack upload network error: {exc}") from exc


def upload_image(
    image_path: Path,
    token: str,
    channel_id: str,
    initial_comment: str,
) -> dict[str, Any]:
    image_bytes = image_path.read_bytes()
    filename = image_path.name

    start = slack_api(
        "files.getUploadURLExternal",
        token,
        {
            "filename": filename,
            "length": str(len(image_bytes)),
        },
    )

    upload_url = start.get("upload_url")
    file_id = start.get("file_id")
    if not upload_url or not file_id:
        raise SlackError("Slack did not return upload_url/file_id.")

    upload_bytes(upload_url, image_bytes)

    return slack_api(
        "files.completeUploadExternal",
        token,
        {
            "files": json.dumps([{"id": file_id, "title": "ChatGPT Usage Dashboard"}]),
            "channel_id": channel_id,
            "initial_comment": initial_comment,
        },
    )


def main() -> int:
    configure_console()
    load_dotenv()
    parser = argparse.ArgumentParser(description="Upload dashboard PNG to Slack.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE_PATH))
    parser.add_argument("--comment", default="ChatGPT usage dashboard")
    parser.add_argument("--token", default=os.environ.get("SLACK_BOT_TOKEN"))
    parser.add_argument("--channel", default=os.environ.get("SLACK_CHANNEL_ID"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: Image not found: {image_path}")
        return 1

    if args.dry_run:
        print(f"Dry run OK. Would upload: {image_path}")
        return 0

    if not args.token or not args.channel:
        print("ERROR: Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID before sending Slack.")
        return 2

    result = upload_image(image_path, args.token, args.channel, args.comment)
    files = result.get("files") or []
    print(f"Uploaded dashboard to Slack. Files: {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
