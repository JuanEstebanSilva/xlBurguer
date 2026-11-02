"""SVG to Colored PNG Batch Renderer for Carnicería San Diego.
Converts vector SVGs in icons/ to crisp, anti-aliased PNG icons with custom fills
using headless Chromium/Edge rendering.
"""

import os
import re
import subprocess
from PIL import Image

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ICONS_DIR = os.path.join(_PROJECT_ROOT, "icons")
IMGS_DIR = os.path.join(_PROJECT_ROOT, "imgs")


def get_edge_path():
    for c in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]:
        if os.path.exists(c):
            return c
    return "msedge"


def convert(svg_name, out_name, color="#FFFFFF", size=64):
    svg_path = os.path.join(ICONS_DIR, svg_name)
    if not os.path.exists(svg_path):
        print(f"Missing SVG: {svg_path}")
        return False
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
    if "fill=" in svg_content:
        svg_content = re.sub(r'fill="[^"]*"', f'fill="{color}"', svg_content)
    else:
        svg_content = svg_content.replace("<path ", f'<path fill="{color}" ')

    temp_html = os.path.join(_PROJECT_ROOT, "temp_render.html")
    temp_shot = os.path.join(_PROJECT_ROOT, "temp_shot.png")
    html = f"""<!DOCTYPE html>
<html><head><style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {size}px; height: {size}px; background: transparent; overflow: hidden; display: flex; align-items: center; justify-content: center; }}
svg {{ width: {size}px; height: {size}px; }}
</style></head><body>{svg_content}</body></html>"""
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html)

    cmd = [
        get_edge_path(),
        "--headless",
        f"--screenshot={temp_shot}",
        f"--window-size={size},{size}",
        "--default-background-color=00000000",
        f"file:///{temp_html.replace(os.sep, '/')}"
    ]
    subprocess.run(cmd, capture_output=True, timeout=10)
    if os.path.exists(temp_shot):
        im = Image.open(temp_shot).crop((0, 0, size, size))
        p = os.path.join(ICONS_DIR, out_name)
        im.save(p, "PNG")
        print(f"Saved: {p}")
        try:
            os.remove(temp_shot)
            os.remove(temp_html)
        except Exception:
            pass
        return True
    return False


if __name__ == "__main__":
    # 1. Sun icons
    convert("sun-solid-full.svg", "sun_white.png", "#FFFFFF")
    convert("sun-solid-full.svg", "sun_emerald.png", "#10B981")

    # 2. Calendar icons
    convert("calendar-days-regular-full.svg", "calendar_day_white.png", "#FFFFFF")
    convert("calendar-days-regular-full.svg", "calendar_day_sky.png", "#38BDF8")
    convert("calendar-week-solid-full.svg", "calendar_week_white.png", "#FFFFFF")
    convert("calendar-week-solid-full.svg", "calendar_week_purple.png", "#A855F7")

    # 3. Chart column icon
    convert("chart-column-solid-full.svg", "chart_column_white.png", "#FFFFFF")

    # 4. Infinity icons
    convert("infinite-solid-full.svg", "infinity_white.png", "#FFFFFF")
    convert("infinite-solid-full.svg", "infinity_amber.png", "#F59E0B")

    # 5. Recycle / reset icons
    convert("recycle-solid-full.svg", "recycle_white.png", "#FFFFFF")
    convert("recycle-solid-full.svg", "recycle_slate.png", "#94A3B8")

    # 6. Payment methods
    convert("credit-card-solid-full.svg", "credit_card_white.png", "#FFFFFF")
    convert("mobile-screen-solid-full.svg", "mobile_white.png", "#FFFFFF")
    convert("money-bill-1-regular-full.svg", "money_white.png", "#FFFFFF")

    # 7. Search
    convert("magnifying-glass-solid-full.svg", "search_white.png", "#FFFFFF")

    # 8. Mockup specific icons
    convert("receipt-solid-full.svg", "receipt_blue.png", "#38BDF8")
    convert("sack-dollar-solid-full.svg", "sack_dollar_green.png", "#10B981")
    convert("coins-solid-full.svg", "coins_gold.png", "#F59E0B")
