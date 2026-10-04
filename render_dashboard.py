from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
DEFAULT_USAGE_PATH = ROOT / "data" / "usage.json"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "dashboard.png"
DEFAULT_LOGO_PATH = ROOT / "assets" / "logo" / "MediaX black.png"
VN_TZ = timezone(timedelta(hours=7), name="ICT")


BG = "#f5f7fb"
PANEL = "#ffffff"
HEADER_FILL = "#f8fafc"
INK = "#111827"
TEXT_BLUE = "#1d4ed8"
MUTED_BLUE = "#475569"
BORDER = "#d6e3f4"
GRID = "#e1e8f2"
BLUE = "#155eef"
BLUE_DARK = "#0b4bc4"
TRACK = "#e7edf6"
RED_ACCENT = "#e30613"
AMBER = "#d97706"
ERROR = "#c33d32"

TABLE_Y = 154
TABLE_WIDTH = 1656
TABLE_HEADER_HEIGHT = 80
TABLE_ROW_HEIGHT = 164
TABLE_BOTTOM_MARGIN = 31
CANVAS_WIDTH = 1688


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for item in candidates:
        path = Path(item)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


F_TITLE = font(31, True)
F_HEADER = font(26, True)
F_ACCOUNT = font(30, True)
F_PERCENT = font(32, True)
F_REMAINING = font(25)
F_BODY = font(24)
F_RESET = font(22)
F_SMALL = font(19)


def safe_text(value: Any, fallback: str = "N/A") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def filter_dashboard_accounts(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        account
        for account in accounts
        if not (
            isinstance(account.get("plan_type"), str)
            and account["plan_type"].strip().casefold() == "free"
        )
    ]


def dashboard_height(account_count: int) -> int:
    visible_count = max(0, min(4, account_count))
    return (
        TABLE_Y
        + TABLE_HEADER_HEIGHT
        + TABLE_ROW_HEIGHT * visible_count
        + TABLE_BOTTOM_MARGIN
    )


def epoch_to_vn(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=VN_TZ).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return None


def text_fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_obj: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if draw.textlength(text, font=font_obj) <= max_width:
        return text

    suffix = "..."
    if draw.textlength(suffix, font=font_obj) > max_width:
        return ""

    value = text
    while value and draw.textlength(value + suffix, font=font_obj) > max_width:
        value = value[:-1].rstrip()
    return value + suffix


def usage_color(value: Any) -> str:
    try:
        pct = int(value)
    except (TypeError, ValueError):
        return MUTED_BLUE
    if pct <= 10:
        return RED_ACCENT
    if pct <= 35:
        return AMBER
    return BLUE


def is_service_error(account: dict[str, Any]) -> bool:
    if account.get("error_type") == "transient_service_error":
        return True

    text = str(account.get("error") or "").lower()
    markers = (
        "503 service unavailable",
        "502 bad gateway",
        "504 gateway timeout",
        "500 internal server error",
        "429 too many requests",
        "upstream connect error",
        "reset reason: overflow",
        "timeout",
    )
    return any(marker in text for marker in markers)


def is_login_error(account: dict[str, Any]) -> bool:
    if account.get("error_type") == "account_auth_error":
        return True

    text = str(account.get("error") or "").lower()
    markers = (
        "không tìm thấy chatgpt account",
        "profile chưa tồn tại",
        "auth type",
        "login",
        "logged",
        "unauthorized",
        "401",
        "403",
    )
    return any(marker in text for marker in markers)


def error_cell_text(account: dict[str, Any]) -> tuple[str, str, str]:
    attempts = account.get("attempts")
    attempts_text = f"Đã thử lại {attempts} lần. " if attempts else ""

    if is_service_error(account):
        return (
            "Lỗi API ChatGPT",
            f"{attempts_text}Máy chủ trả lỗi 503/quá tải.",
            "Không phải lỗi đăng nhập. Hãy thử lại sau.",
        )

    if is_login_error(account):
        return (
            "Yêu cầu đăng nhập",
            "Hồ sơ Codex không đọc được dữ liệu tài khoản.",
            "Vui lòng đăng nhập lại.",
        )

    error = safe_text(account.get("error"))
    return (
        "Lỗi tài khoản",
        text_fit_stub(error, 70),
        "Vui lòng kiểm tra nhật ký.",
    )


def text_fit_stub(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def draw_header_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), fill="#deebff")
    bars = [
        (cx - 21, cy + 13, cx - 11, cy + 23),
        (cx - 3, cy + 2, cx + 7, cy + 23),
        (cx + 15, cy - 10, cx + 25, cy + 23),
    ]
    for box in bars:
        draw.rectangle(box, outline=BLUE, width=4)
    points = [(cx - 23, cy - 4), (cx - 11, cy - 15), (cx + 1, cy - 8), (cx + 24, cy - 30)]
    draw.line(points, fill=BLUE, width=4, joint="curve")
    draw.line((cx + 24, cy - 30, cx + 24, cy - 18), fill=BLUE, width=4)
    draw.line((cx + 24, cy - 30, cx + 12, cy - 30), fill=BLUE, width=4)


def trim_transparent(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image
    bbox = image.getbbox()
    return image.crop(bbox) if bbox else image


def paste_logo(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    path: Path,
    x: int,
    y: int,
    target_w: int = 255,
    max_h: int = 62,
) -> int:
    if not path.exists():
        draw_header_icon(draw, x + 38, y + 38)
        return 108

    logo = trim_transparent(Image.open(path).convert("RGBA"))
    target_h = max(1, int(logo.height * target_w / logo.width))
    if target_h > max_h:
        target_h = max_h
        target_w = max(1, int(logo.width * target_h / logo.height))

    logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    img.alpha_composite(logo, (x, y + (max_h - target_h) // 2))
    return target_w


def draw_avatar(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), fill=BLUE)
    draw.ellipse((cx - 10, cy - 20, cx + 10, cy), fill=PANEL)
    draw.pieslice((cx - 24, cy - 1, cx + 24, cy + 42), start=180, end=360, fill=PANEL)


def draw_clock(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.ellipse((cx - 28, cy - 28, cx + 28, cy + 28), outline=BLUE, width=4)
    draw.line((cx, cy, cx, cy - 16), fill=BLUE, width=4)
    draw.line((cx, cy, cx + 13, cy + 9), fill=BLUE, width=4)


def draw_progress(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    value: Any,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=6, fill=TRACK)
    try:
        pct = max(0, min(100, int(value)))
    except (TypeError, ValueError):
        pct = 0
    fill_w = int(w * pct / 100)
    color = usage_color(value)
    if fill_w:
        draw.rounded_rectangle((x, y, x + fill_w, y + h), radius=6, fill=color)
        if fill_w > 10:
            end_color = BLUE_DARK if color == BLUE else color
            draw.rectangle((x + fill_w - 6, y, x + fill_w, y + h), fill=end_color)


def draw_limit_cell(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    limit: dict[str, Any],
) -> None:
    remaining = safe_text(limit.get("remaining_percent"), "?")
    reset = safe_text(limit.get("reset_time_vn"))
    color = usage_color(limit.get("remaining_percent"))

    draw.text((x, y), f"{remaining}%", fill=color, font=F_PERCENT)
    percent_w = int(draw.textlength(f"{remaining}%", font=F_PERCENT))
    draw.text((x + percent_w + 14, y + 8), "còn lại", fill=INK, font=F_REMAINING)
    draw_progress(draw, x, y + 52, w - 34, 13, limit.get("remaining_percent"))
    draw.text((x, y + 84), f"Đặt lại VN: {reset}", fill=MUTED_BLUE, font=F_BODY)


def reset_credit_lines(account: dict[str, Any]) -> list[str]:
    reset_credits = account.get("rate_limit_reset_credits") or {}
    credits = reset_credits.get("credits") or []
    available_credits = [
        credit
        for credit in credits
        if credit.get("status") in (None, "available")
    ]
    if not available_credits:
        return ["Không có lượt đặt lại", "hạn mức khả dụng lúc này."]

    count = len(available_credits)
    label = "Lượt đặt lại đầy đủ"
    lines = [f"{count} {label}"]
    for index, credit in enumerate(available_credits, start=1):
        expires = epoch_to_vn(credit.get("expiresAt")) or "N/A"
        lines.append(f"Hết hạn {index} VN {expires}")
    return lines


def draw_reset_cell(
    draw: ImageDraw.ImageDraw,
    account: dict[str, Any],
    x: int,
    y: int,
    w: int,
) -> None:
    draw_clock(draw, x + 30, y + 52)
    lines = reset_credit_lines(account)
    text_x = x + 86
    compact = len(lines) > 2
    line_font = F_SMALL if compact else F_RESET
    line_gap = 29 if compact else 39
    start_y = y + 16 if compact else y + 26

    for index, line in enumerate(lines):
        color = INK if index == 0 else MUTED_BLUE
        draw.text(
            (text_x, start_y + index * line_gap),
            text_fit(draw, line, line_font, w - 88),
            fill=color,
            font=line_font,
        )


def draw_table(draw: ImageDraw.ImageDraw, accounts: list[dict[str, Any]]) -> None:
    table_x = 16
    table_y = TABLE_Y
    table_w = TABLE_WIDTH
    header_h = TABLE_HEADER_HEIGHT
    row_h = TABLE_ROW_HEIGHT
    visible_accounts = accounts[:4]
    table_h = header_h + row_h * len(visible_accounts)
    col_widths = [306, 416, 502, 432]
    col_x = [table_x]
    for width in col_widths[:-1]:
        col_x.append(col_x[-1] + width)

    draw.rounded_rectangle(
        (table_x, table_y, table_x + table_w, table_y + table_h),
        radius=16,
        fill=PANEL,
        outline=BORDER,
        width=2,
    )
    draw.rounded_rectangle(
        (table_x, table_y, table_x + table_w, table_y + header_h),
        radius=16,
        fill=HEADER_FILL,
        outline=BORDER,
        width=2,
    )
    draw.rectangle((table_x, table_y + header_h - 16, table_x + table_w, table_y + header_h), fill=HEADER_FILL)

    headers = ["TÀI KHOẢN", "HẠN MỨC 5 GIỜ", "HẠN MỨC HÀNG TUẦN", "THỜI GIAN ĐẶT LẠI"]
    for i, header in enumerate(headers):
        x = col_x[i]
        w = col_widths[i]
        tw = draw.textlength(header, font=F_HEADER)
        draw.text((x + (w - tw) / 2, table_y + 24), header, fill=TEXT_BLUE, font=F_HEADER)

    x_cursor = table_x
    for width in col_widths[:-1]:
        x_cursor += width
        draw.line((x_cursor, table_y, x_cursor, table_y + table_h), fill=GRID, width=2)

    for row in range(len(visible_accounts) + 1):
        y = table_y + header_h + row * row_h
        draw.line((table_x, y, table_x + table_w, y), fill=GRID, width=2)

    for index, account in enumerate(visible_accounts):
        row_y = table_y + header_h + index * row_h
        content_y = row_y + 36
        label = safe_text(account.get("label") or account.get("id"))

        draw_avatar(draw, table_x + 80, row_y + row_h // 2)
        draw.text((table_x + 140, row_y + 62), label, fill=INK, font=F_ACCOUNT)

        if account.get("status") != "ok":
            title, detail, action = error_cell_text(account)
            draw.text(
                (col_x[1] + 40, row_y + 42),
                title,
                fill=ERROR,
                font=F_RESET,
            )
            draw.text(
                (col_x[2] + 34, row_y + 38),
                text_fit(draw, detail, F_RESET, col_widths[2] - 68),
                fill=INK,
                font=F_RESET,
            )
            draw.text(
                (col_x[2] + 34, row_y + 78),
                text_fit(draw, action, F_RESET, col_widths[2] - 68),
                fill=MUTED_BLUE,
                font=F_RESET,
            )
            continue

        draw_limit_cell(draw, col_x[1] + 40, content_y, col_widths[1] - 64, account.get("five_hour") or {})
        draw_limit_cell(draw, col_x[2] + 34, content_y, col_widths[2] - 64, account.get("weekly") or {})
        draw_reset_cell(draw, account, col_x[3] + 34, row_y + 30, col_widths[3] - 68)


def render_dashboard(usage_path: Path = DEFAULT_USAGE_PATH, output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    payload = json.loads(usage_path.read_text(encoding="utf-8"))
    accounts = filter_dashboard_accounts(payload.get("accounts") or [])

    img = Image.new("RGBA", (CANVAS_WIDTH, dashboard_height(len(accounts))), BG)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((16, 17, 1672, 123), radius=16, fill=HEADER_FILL, outline=BORDER, width=2)
    draw.line((34, 122, 1654, 122), fill="#eef2f7", width=2)
    draw_header_icon(draw, 84, 70)
    draw.text(
        (136, 56),
        "Mức sử dụng: Codex, Work, Workspace Agents và ChatGPT cho Excel.",
        fill=INK,
        font=F_TITLE,
    )
    logo_box_x = 1286
    logo_box_w = 340
    logo_w = paste_logo(
        img,
        draw,
        DEFAULT_LOGO_PATH,
        logo_box_x + (logo_box_w - 300) // 2,
        34,
        target_w=300,
        max_h=52,
    )
    logo_center_x = logo_box_x + logo_box_w / 2
    collected = f"Thu thập lúc (VN): {safe_text(payload.get('collected_at_vn'))}"
    collected_w = draw.textlength(collected, font=F_SMALL)
    draw.text((logo_center_x - collected_w / 2, 88), collected, fill=MUTED_BLUE, font=F_SMALL)

    draw_table(draw, accounts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output_path)
    return output_path


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description="Render dashboard PNG from data/usage.json.")
    parser.add_argument("--input", default=str(DEFAULT_USAGE_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    output = render_dashboard(Path(args.input), Path(args.output))
    print(f"Đã lưu bảng giám sát: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
