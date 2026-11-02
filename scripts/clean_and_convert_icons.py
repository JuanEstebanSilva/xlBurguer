import os
import re
import sys
import subprocess
from PIL import Image

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ICONS_DIR = os.path.join(_PROJECT_ROOT, "icons")

def clean_meat_svg():
    p = os.path.join(ICONS_DIR, "noun_Meat_10038.svg")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            c = f.read()
        # Remove all text tags
        c_clean = re.sub(r'<text[\s\S]*?</text>', '', c)
        c_clean = c_clean.replace('viewBox="0 0 100 125"', 'viewBox="0 0 100 100"')
        c_clean = c_clean.replace("viewBox='0 0 100 125'", "viewBox='0 0 100 100'")
        with open(p, "w", encoding="utf-8") as f:
            f.write(c_clean)
        
        meat_solid = os.path.join(ICONS_DIR, "meat-solid-full.svg")
        with open(meat_solid, "w", encoding="utf-8") as f:
            f.write(c_clean)
        print("Cleaned meat SVG and wrote meat-solid-full.svg")

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
    clean_meat_svg()
    # Meat icons
    convert("meat-solid-full.svg", "meat_white.png", "#FFFFFF")
    convert("meat-solid-full.svg", "meat_sky.png", "#38BDF8")
    convert("meat-solid-full.svg", "meat_gold.png", "#F59E0B")
    convert("meat-solid-full.svg", "meat_slate.png", "#94A3B8")
    convert("meat-solid-full.svg", "meat_red.png", "#F87171")

    # Box open icons
    convert("box-open-solid-full.svg", "box_open_white.png", "#FFFFFF")
    convert("box-open-solid-full.svg", "box_open_cyan.png", "#67E8F9")
    convert("box-open-solid-full.svg", "box_open_slate.png", "#94A3B8")

    # Truck fast icons
    convert("truck-fast-solid-full.svg", "truck_fast_white.png", "#FFFFFF")
    convert("truck-fast-solid-full.svg", "truck_fast_red.png", "#F87171")
    convert("truck-fast-solid-full.svg", "truck_fast_slate.png", "#94A3B8")

    # Retweet icons
    convert("retweet-solid-full.svg", "retweet_white.png", "#FFFFFF")
    convert("retweet-solid-full.svg", "retweet_sky.png", "#38BDF8")

    # Building user icons
    convert("building-user-solid-full.svg", "building_user_white.png", "#FFFFFF")
    convert("building-user-solid-full.svg", "building_user_blue.png", "#3B82F6")
    convert("building-user-solid-full.svg", "building_user_slate.png", "#94A3B8")

    # Hospital user icons
    convert("hospital-user-solid-full.svg", "hospital_user_white.png", "#FFFFFF")
    convert("hospital-user-solid-full.svg", "hospital_user_blue.png", "#3B82F6")
    convert("hospital-user-solid-full.svg", "hospital_user_slate.png", "#94A3B8")
    print("All conversions completed successfully.")
