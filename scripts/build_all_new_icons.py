"""Generate all color variants for new SVGs using resvg_py.
Cleans meat SVG from Noun Project text watermark and produces
high-resolution PNGs for UI components.
"""

import os
import re
import io
import resvg_py
from PIL import Image

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ICONS_DIR = os.path.join(_PROJECT_ROOT, "icons")

# 1. Clean meat icon (Noun Project)
meat_clean_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" xml:space="preserve"><g><g><path d="M99.462,31.821c0,0-5.129-14.749-33.517-14.2C37.547,18.181,2.932,29.164,0.361,36.675C0.255,36.989,0,56.092,0,56.092    s17.581,23.173,65.483,26.29c15.11,0.36,19.778-7.15,21.613-13.377c1.833-6.227,12.18-14.927,12.728-15.573    C100.373,52.797,99.462,31.821,99.462,31.821z M95.067,35.302c-8.158,6.315-10.629,13.374-10.629,13.374    c-2.656,9.885-8.335,16.11-24.544,13.917C18.404,57.001,4.393,38.508,4.393,38.508c-0.882-1.372-0.54-3.177,2.568-4.304    c70.063-25.644,86.274-8.249,88.106-4.49C96.891,33.469,96.343,33.469,95.067,35.302z"/><path d="M84.9,28.095c0,0.137-8.316,6.521-14.425,9.198c-6.119,2.677-42.499-0.195-43.342,0c-1.813,0.42,0,1.167,0,1.167    c3.011,1.47,30.495,4.744,37.429,5.225c6.942,0.48,4.814,11.729,4.95,13.466c0.147,1.873,2.394,2.757,2.335,0.823    c0-8.589,12.092-24.113,13.876-27.477C87.509,27.124,84.9,27.957,84.9,28.095z"/></g></g></svg>"""

with open(os.path.join(ICONS_DIR, "meat-solid-full.svg"), "w", encoding="utf-8") as f:
    f.write(meat_clean_svg)
with open(os.path.join(ICONS_DIR, "noun_Meat_10038.svg"), "w", encoding="utf-8") as f:
    f.write(meat_clean_svg)


def render_svg_to_png(svg_str: str, color: str, out_path: str, size: int = 64) -> None:
    if 'fill="' in svg_str:
        colored = re.sub(r'fill="[^"]*"', f'fill="{color}"', svg_str)
    else:
        colored = svg_str.replace("<path ", f'<path fill="{color}" ')
    png_bytes = resvg_py.svg_to_bytes(colored)
    im = Image.open(io.BytesIO(png_bytes)).resize((size, size), Image.Resampling.LANCZOS)
    im.save(out_path, "PNG")
    print(f"Generated: {os.path.basename(out_path)}")


jobs = [
    # 1. Meat icon
    ("meat-solid-full.svg", [
        ("#FFFFFF", "meat_white.png"),
        ("#F59E0B", "meat_gold.png"),
        ("#94A3B8", "meat_slate.png"),
        ("#38BDF8", "meat_sky.png"),
        ("#10B981", "meat_green.png"),
        ("#F87171", "meat_red.png"),
        ("#FFFFFF", "meat-solid-full.png"),
        ("#FFFFFF", "noun_Meat_10038.png"),
    ]),
    # 2. Box Open icon (Cupo Total Asignado)
    ("box-open-solid-full.svg", [
        ("#FFFFFF", "box_open_white.png"),
        ("#67E8F9", "box_open_cyan.png"),
        ("#94A3B8", "box_open_slate.png"),
        ("#F59E0B", "box_open_gold.png"),
        ("#FFFFFF", "box-open-solid-full.png"),
    ]),
    # 3. Truck Fast icon (Despachado)
    ("truck-fast-solid-full.svg", [
        ("#FFFFFF", "truck_fast_white.png"),
        ("#F87171", "truck_fast_red.png"),
        ("#94A3B8", "truck_fast_slate.png"),
        ("#FFFFFF", "truck-fast-solid-full.png"),
    ]),
    # 4. Retweet icon (Renovar)
    ("retweet-solid-full.svg", [
        ("#FFFFFF", "retweet_white.png"),
        ("#38BDF8", "retweet_blue.png"),
        ("#10B981", "retweet_green.png"),
        ("#94A3B8", "retweet_slate.png"),
        ("#FFFFFF", "retweet-solid-full.png"),
    ]),
    # 5. Building User icon (Empresa avatar & detail)
    ("building-user-solid-full.svg", [
        ("#FFFFFF", "building_user_white.png"),
        ("#F59E0B", "building_user_gold.png"),
        ("#94A3B8", "building_user_slate.png"),
        ("#FFFFFF", "building-user-solid-full.png"),
    ]),
    # 6. Hospital User icon (Registrar Empresa)
    ("hospital-user-solid-full.svg", [
        ("#FFFFFF", "hospital_user_white.png"),
        ("#F59E0B", "hospital_user_gold.png"),
        ("#94A3B8", "hospital_user_slate.png"),
        ("#FFFFFF", "hospital-user-solid-full.png"),
    ]),
    # 7. Percent icon (Descuento Pactado)
    ("percent-solid-full.svg", [
        ("#34D399", "percent_green.png"),
        ("#FFFFFF", "percent_white.png"),
        ("#F59E0B", "percent_gold.png"),
    ]),
]


def main():
    for svg_file, variants in jobs:
        svg_path = os.path.join(ICONS_DIR, svg_file)
        if not os.path.exists(svg_path):
            print(f"Skipping missing SVG: {svg_file}")
            continue
        with open(svg_path, "r", encoding="utf-8") as f:
            content = f.read()
        for color, filename in variants:
            render_svg_to_png(content, color, os.path.join(ICONS_DIR, filename))
    print("ALL NEW ICONS SUCCESSFULLY GENERATED!")


if __name__ == "__main__":
    main()
