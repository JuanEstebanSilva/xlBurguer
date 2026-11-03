"""Asset Manager for Carnicería San Diego.
Automatically loads visual assets (logo, background, icon) and generates
high-quality placeholders using Pillow if missing in development.
"""

import os
import sys
from typing import Any, Optional, Callable, Tuple
from PIL import Image, ImageDraw, ImageFont
from database.connection import get_resource_path, get_writable_path


# Canonical asset aliases mapping
_ASSET_ALIASES = {
    "fondo login.jpg": ["fondoLogin.png", "fondo login.png", "fondoLogin.jpg", "fondo login.jpg", "fondoLogin2.jpg", "asadorLogin.jpg", "fondo.png"],
    "fondologin.jpg": ["fondoLogin.png", "fondo login.png", "fondoLogin.jpg", "fondo login.jpg", "fondoLogin2.jpg", "asadorLogin.jpg", "fondo.png"],
    "fondo login.png": ["fondoLogin.png", "fondo login.png", "fondoLogin.jpg", "fondo login.jpg", "fondoLogin2.jpg", "asadorLogin.jpg", "fondo.png"],
    "fondologin.png": ["fondoLogin.png", "fondo login.png", "fondoLogin.jpg", "fondo login.jpg", "fondoLogin2.jpg", "asadorLogin.jpg", "fondo.png"],
    "asadorlogin.jpg": ["fondoLogin.png", "fondoLogin.jpg", "asadorLogin.jpg", "fondo login.jpg", "fondo.png"],
    "fondo login": ["fondoLogin.png", "fondo login.png", "fondoLogin.jpg", "fondo login.jpg", "fondoLogin2.jpg", "asadorLogin.jpg"],
    "fondologin": ["fondoLogin.png", "fondo login.png", "fondoLogin.jpg", "fondo login.jpg", "fondoLogin2.jpg", "asadorLogin.jpg"],
    "icono principal.png": ["icono.png", "icono_xl.png", "icono_principal.png", "icono.ico"],
    "icono principal.jpg": ["icono.png", "icono_xl.png", "icono_principal.png", "icono.ico"],
    "iconoprincipal.jpg": ["icono.png", "icono_xl.png", "icono_principal.png", "icono.ico"],
    "icono principal": ["icono.png", "icono_xl.png", "icono_principal.png", "icono.ico"],
    "iconoprincipal": ["icono.png", "icono_xl.png", "icono_principal.png", "icono.ico"],
    "icono_principal.png": ["icono.png", "icono_xl.png", "icono_principal.png", "icono.ico"],
    "icono_principal": ["icono.png", "icono_xl.png", "icono_principal.png", "icono.ico"],
    "logo.png": ["logoHorizontal.png", "logoCompleto.png", "XL_Burguer_logo.png"],
    "icono.png": ["icono.png", "icono_xl.png", "icono.ico", "favicon.ico"],
    "icono": ["icono.png", "icono_xl.png", "icono.ico", "favicon.ico"],
    "icono_xl.png": ["icono_xl.png", "icono.png"],
    "icono_xl.ico": ["icono_xl.ico", "icono.ico"],
    "icono.ico": ["icono.ico", "icono_xl.ico", "icono.png"],
    "logo.ico": ["icono.ico", "icono_xl.ico", "icono.png"],
    "favicon.ico": ["icono.ico", "icono_xl.ico", "icono.png"],
    "logo xl burguer": ["logoHorizontal.png", "XL_Burguer_horizontal.png", "logoCompleto.png"],
    "logo xlburguer": ["logoHorizontal.png", "XL_Burguer_horizontal.png", "logoCompleto.png"],
    "xl burguer": ["logoHorizontal.png", "XL_Burguer_horizontal.png", "logoCompleto.png"],
    "xlburguer": ["logoHorizontal.png", "XL_Burguer_horizontal.png", "logoCompleto.png"],
    "icono xl burguer": ["icono.png", "icono_xl.png", "icono.ico"],
    "icono xlburguer": ["icono.png", "icono_xl.png", "icono.ico"],
    "logo_factura_negro.png": ["XL_Burguer_factura_negro.png", "logotipo-negro-2000.png"],
    "logo_factura_negro": ["XL_Burguer_factura_negro.png", "logotipo-negro-2000.png"],
    "xl_burguer_factura_negro.png": ["XL_Burguer_factura_negro.png", "logotipo-negro-2000.png"],
    "xl_burguer_isotipo_negro.png": ["XL_Burguer_isotipo_negro.png", "isotipoNegro.png"],
    "isotipoblanco": ["XL_Burguer_isotipo_blanco.png", "isotipoBlanco.png"],
    "isotiponegro": ["XL_Burguer_isotipo_negro.png", "isotipoNegro.png"],
    "isotipo negro.png": ["XL_Burguer_isotipo_negro.png", "isotipoNegro.png"],
    "isotipo negro": ["XL_Burguer_isotipo_negro.png", "isotipoNegro.png"],
    "isotiponegro.png": ["XL_Burguer_isotipo_negro.png", "isotipoNegro.png"],
    "qr.png": ["qr.png"],
    "qr": ["qr.png"],
    "logotipo-negro-2000.png": ["XL_Burguer_factura_negro.png", "logotipo-negro-2000.png"],
    "logotipo-negro-2000": ["XL_Burguer_factura_negro.png", "logotipo-negro-2000.png"],
    "logotipo negro 2000": ["XL_Burguer_factura_negro.png", "logotipo-negro-2000.png"],
    "logotipo negro 2000.png": ["XL_Burguer_factura_negro.png", "logotipo-negro-2000.png"],
    "selloblanco": ["XL_Burguer_isotipo_blanco.png", "isotipoBlanco.png"],
    "sellonegro": ["XL_Burguer_isotipo_negro.png", "isotipoNegro.png"],
    "logocompleto": ["logoCompleto.png", "XL_Burguer_completo.png"],
    "logohorizontal": ["logoHorizontal.png", "XL_Burguer_horizontal.png", "XL_Burguer_logo.png"],
    "flame_active.png": ["flame_active.png"],
    "flame_inactive.png": ["flame_inactive.png"],
    "floppy_green.png": ["floppy_green.png", "floppy-disk-regular-full.svg"],
    "floppy_green": ["floppy_green.png", "floppy-disk-regular-full.svg"],
    "floppy_white.png": ["floppy_white.png", "floppy-disk-regular-full.svg", "floppy_green.png"],
    "floppy_white": ["floppy_white.png", "floppy-disk-regular-full.svg", "floppy_green.png"],
    "floppy": ["floppy_green.png", "floppy_white.png", "floppy-disk-regular-full.svg"],
    "save": ["floppy_green.png", "floppy_white.png", "floppy-disk-regular-full.svg"],
    "logout_icon.png": ["logout_icon.png", "exit_icon.png"],
    "logout_icon": ["logout_icon.png", "exit_icon.png"],
    "exit_icon": ["logout_icon.png", "exit_icon.png"],
    "hunzaia.png": ["hunzaia.png", "unzaga.png"],
    "unzaga.png": ["unzaga.png", "hunzaia.png"],
    "hunzaia": ["hunzaia.png", "unzaga.png"],
    "unzaga": ["unzaga.png", "hunzaia.png"],
    "user_icon.png": ["user_icon.png", "user-solid-full.png", "user-solid-full.svg"],
    "user_icon": ["user_icon.png", "user-solid-full.png", "user-solid-full.svg"],
    "user-solid-full.png": ["user-solid-full.png", "user_icon.png", "user-solid-full.svg"],
    "user-solid-full.svg": ["user-solid-full.png", "user_icon.png", "user-solid-full.svg"],
    "repeat-solid-full": ["repeat-solid-full.png", "repeat_blue.png", "repeat_white.png", "repeat-solid-full.svg"],
    "repeat-solid-full.svg": ["repeat-solid-full.png", "repeat_blue.png", "repeat_white.png", "repeat-solid-full.svg"],
    "repeat-solid": ["repeat-solid-full.png", "repeat_blue.png", "repeat_white.png", "repeat-solid-full.svg"],
    "repeat": ["repeat-solid-full.png", "repeat_blue.png", "repeat_white.png", "repeat-solid-full.svg"],
    "eye-slash-solid": ["eye-slash-solid.png", "eye-slash-solid-full.png", "eye_slash_white.png", "eye-slash-solid-full.svg"],
    "eye-slash-solid-full": ["eye-slash-solid-full.png", "eye-slash-solid.png", "eye_slash_white.png", "eye-slash-solid-full.svg"],
    "eye-slash-solid-full.svg": ["eye-slash-solid-full.png", "eye-slash-solid.png", "eye_slash_white.png", "eye-slash-solid-full.svg"],
    "percent": ["percent_green.png", "percent-solid-full.png", "percent_solid_white.png", "percent-solid-full.svg"],
    "percent_green": ["percent_green.png", "percent-solid-full.png"],
    "percent_gold": ["percent_gold.png", "percent-solid-full.png"],
    "percent_white": ["percent_white.png", "percent-solid-full.png"],
    "square_check": ["square-check-solid-full.svg", "square-check-regular-full.svg", "check_green.png"],
    "square-check": ["square-check-solid-full.svg", "square-check-regular-full.svg", "check_green.png"],
    "square check": ["square-check-solid-full.svg", "square-check-regular-full.svg", "check_green.png"],
    "ranking-star-solid-full": ["ranking-star-solid-full.svg"],
    "ranking-star-solid-full.svg": ["ranking-star-solid-full.svg"],
    "ranking-star": ["ranking-star-solid-full.svg"],
    "ranking_star": ["ranking-star-solid-full.svg"],
    "user-tie-solid-full": ["user-tie-solid-full.png", "user_tie_solid_white.png", "user_tie_solid_slate.png", "user-tie-solid-full.svg"],
    "user-tie-solid-full.svg": ["user-tie-solid-full.png", "user_tie_solid_white.png", "user-tie-solid-full.svg"],
    "user-tie": ["user-tie-solid-full.png", "user_tie_solid_white.png", "user-tie-solid-full.svg"],
    "users-gear-solid-full": ["users-gear-solid-full.png", "users_gear_solid_white.png", "users_gear_solid_slate.png", "users-gear-solid-full.svg"],
    "users-gear-solid-full.svg": ["users-gear-solid-full.png", "users_gear_solid_white.png", "users-gear-solid-full.svg"],
    "user-gear": ["users-gear-solid-full.png", "users_gear_solid_white.png", "users-gear-solid-full.svg"],
    "users-gear": ["users-gear-solid-full.png", "users_gear_solid_white.png", "users-gear-solid-full.svg"],
    "user-plus-solid-full": ["user-plus-solid-full.png", "user_plus_solid_white.png", "user_plus_solid_slate.png", "user-plus-solid-full.svg"],
    "user-plus-solid-full.svg": ["user-plus-solid-full.png", "user_plus_solid_white.png", "user-plus-solid-full.svg"],
    "user-plus": ["user-plus-solid-full.png", "user_plus_solid_white.png", "user-plus-solid-full.svg"],
    "building-solid-full": ["building-solid-full.png", "building_solid_white.png", "building_solid_gold.png", "building-solid-full.svg"],
    "building-solid-full.svg": ["building-solid-full.png", "building_solid_white.png", "building-solid-full.svg"],
    "building": ["building-solid-full.png", "building_solid_white.png", "building-solid-full.svg"],
    "building-regular-full": ["building-regular-full.png", "building_regular_white.png", "building-regular-full.svg"],
    "building-regular-full.svg": ["building-regular-full.png", "building_regular_white.png", "building-regular-full.svg"],
    "tags-solid-full": ["tags-solid-full.png", "tags_slate.png", "tags_white.png", "tags_gold.png", "tags-solid-full.svg"],
    "tags-solid-full.svg": ["tags-solid-full.png", "tags_slate.png", "tags_white.png", "tags-solid-full.svg"],
    "tags": ["tags_slate.png", "tags-solid-full.png", "tags_white.png", "tags-solid-full.svg"],
    "tags_slate": ["tags_slate.png", "tags-solid-full.png"],
    "tags_white": ["tags_white.png", "tags-solid-full.png"],
    "tags_gold": ["tags_gold.png", "tags-solid-full.png"],
    "eraser-solid-full": ["eraser-solid-full.png", "eraser_slate.png", "eraser_white.png", "eraser_blue.png", "eraser-solid-full.svg"],
    "eraser-solid-full.svg": ["eraser-solid-full.png", "eraser_slate.png", "eraser_white.png", "eraser-solid-full.svg"],
    "eraser": ["eraser_slate.png", "eraser-solid-full.png", "eraser_white.png", "eraser_blue.png"],
    "eraser_slate": ["eraser_slate.png", "eraser-solid-full.png"],
    "eraser_white": ["eraser_white.png", "eraser-solid-full.png"],
    "eraser_blue": ["eraser_blue.png", "eraser-solid-full.png"],
    "eraser_red": ["eraser_red.png", "eraser-solid-full.png"],
    "repeat-solid-full": ["repeat-solid-full.png", "repeat_blue.png", "repeat_white.png", "repeat_slate.png", "repeat-solid-full.svg"],
    "repeat-solid-full.svg": ["repeat-solid-full.png", "repeat_blue.png", "repeat_white.png", "repeat-solid-full.svg"],
    "repeat": ["repeat_blue.png", "repeat_white.png", "repeat_slate.png", "repeat-solid-full.png"],
    "repeat_blue": ["repeat_blue.png", "repeat-solid-full.png"],
    "repeat_white": ["repeat_white.png", "repeat-solid-full.png"],
    "repeat_slate": ["repeat_slate.png", "repeat-solid-full.png"],
    "recycle-solid-full": ["recycle_blue.png", "recycle_white.png", "recycle_slate.png", "recycle-solid-full.svg"],
    "recycle": ["recycle_blue.png", "recycle_white.png", "recycle_slate.png"],
    "recycle_blue": ["recycle_blue.png"],
    "recycle_white": ["recycle_white.png"],
    "recycle_slate": ["recycle_slate.png"],
    "hand-holding-dollar-solid-full": ["hand-holding-dollar-solid-full.svg", "hand-holding-dollar-solid-full.png"],
    "hand-holding-dollar-solid-full.svg": ["hand-holding-dollar-solid-full.svg", "hand-holding-dollar-solid-full.png"],
    "hand-holding-dollar": ["hand-holding-dollar-solid-full.svg", "hand-holding-dollar-solid-full.png"],
    "fiados": ["hand-holding-dollar-solid-full.svg", "hand-holding-dollar-solid-full.png"],
    "drumstick-bite-solid-full": ["drumstick-bite-solid-full.png", "drumstick_gold.png", "drumstick_white.png", "drumstick-bite-solid-full.svg"],
    "drumstick-bite-solid-full.svg": ["drumstick-bite-solid-full.png", "drumstick_white.png", "drumstick-bite-solid-full.svg"],
    "drumstick_bite_solid_full": ["drumstick-bite-solid-full.png", "drumstick_gold.png", "drumstick_white.png", "drumstick-bite-solid-full.svg"],
    "drumstick": ["drumstick-bite-solid-full.png", "drumstick_gold.png", "drumstick_white.png", "drumstick-bite-solid-full.svg"],
    "drumstick_gold": ["drumstick_gold.png"],
    "drumstick_white": ["drumstick_white.png"],
    "drumstick_slate": ["drumstick_slate.png"],
    "box-open-solid-full": ["box_open_cyan.png", "box_open_white.png", "box_open_slate.png", "box_open_gold.png", "box-open-solid-full.png", "box-open-solid-full.svg"],
    "box-open-solid-full.svg": ["box_open_cyan.png", "box_open_white.png", "box-open-solid-full.svg"],
    "box-open": ["box_open_cyan.png", "box_open_white.png", "box-open-solid-full.png"],
    "box_open_cyan": ["box_open_cyan.png", "box-open-solid-full.png"],
    "box_open_green": ["box_open_green.png", "box_open_emerald.png", "box_open_cyan.png", "box-open-solid-full.png"],
    "box_open_emerald": ["box_open_emerald.png", "box_open_green.png", "box-open-solid-full.png"],
    "box_open_gold": ["box_open_gold.png", "box-open-solid-full.png"],
    "truck-fast-solid-full": ["truck_fast_amber.png", "truck_fast_sky.png", "truck_fast_red.png", "truck_fast_white.png", "truck-fast-solid-full.png", "truck-fast-solid-full.svg"],
    "truck-fast-solid-full.svg": ["truck_fast_amber.png", "truck_fast_white.png", "truck-fast-solid-full.svg"],
    "truck-fast": ["truck_fast_amber.png", "truck_fast_sky.png", "truck_fast_white.png", "truck-fast-solid-full.png"],
    "truck_fast": ["truck_fast_amber.png", "truck_fast_sky.png", "truck_fast_white.png", "truck-fast-solid-full.png"],
    "truck_fast_red": ["truck_fast_red.png", "truck-fast-solid-full.png"],
    "truck_fast_amber": ["truck_fast_amber.png", "truck-fast-solid-full.png"],
    "truck_fast_gold": ["truck_fast_gold.png", "truck_fast_amber.png", "truck-fast-solid-full.png"],
    "truck_fast_indigo": ["truck_fast_indigo.png", "truck_fast_sky.png", "truck-fast-solid-full.png"],
    "truck_fast_sky": ["truck_fast_sky.png", "truck-fast-solid-full.png"],
    "retweet-solid-full": ["retweet_blue.png", "retweet_white.png", "retweet_green.png", "retweet_slate.png", "retweet-solid-full.png", "retweet-solid-full.svg"],
    "retweet-solid-full.svg": ["retweet_blue.png", "retweet_white.png", "retweet-solid-full.svg"],
    "retweet": ["retweet_blue.png", "retweet_white.png", "retweet_green.png", "retweet-solid-full.png"],
    "retweet_blue": ["retweet_blue.png", "retweet-solid-full.png"],
    "retweet_sky": ["retweet_blue.png", "retweet-solid-full.png"],
    "building-user-solid-full": ["building_user_gold.png", "building_user_white.png", "building_user_slate.png", "building-user-solid-full.png", "building-user-solid-full.svg"],
    "building-user-solid-full.svg": ["building_user_gold.png", "building_user_white.png", "building-user-solid-full.svg"],
    "building-user": ["building_user_gold.png", "building_user_white.png", "building-user-solid-full.png"],
    "building_user": ["building_user_gold.png", "building_user_white.png", "building-user-solid-full.png"],
    "building_user_gold": ["building_user_gold.png", "building-user-solid-full.png"],
    "hospital-user-solid-full": ["hospital_user_gold.png", "hospital_user_white.png", "hospital_user_slate.png", "hospital-user-solid-full.png", "hospital-user-solid-full.svg"],
    "hospital-user-solid-full.svg": ["hospital_user_gold.png", "hospital_user_white.png", "hospital-user-solid-full.svg"],
    "hospital-user": ["hospital_user_gold.png", "hospital_user_white.png", "hospital-user-solid-full.png"],
    "hospital_user": ["hospital_user_gold.png", "hospital_user_white.png", "hospital-user-solid-full.png"],
    "hospital_user_gold": ["hospital_user_gold.png", "hospital-user-solid-full.png"],
    "meat-solid-full": ["meat_gold.png", "meat_white.png", "meat_slate.png", "meat_green.png", "meat_sky.png", "meat-solid-full.png", "meat-solid-full.svg"],
    "meat-solid-full.svg": ["meat_gold.png", "meat_white.png", "meat-solid-full.svg"],
    "meat": ["meat_gold.png", "meat_white.png", "meat_slate.png", "meat-solid-full.png"],
    "meat_gold": ["meat_gold.png", "meat_white.png", "meat-solid-full.png"],
    "meat_white": ["meat_white.png", "meat_gold.png", "meat-solid-full.png"],
    "meat_sky": ["meat_sky.png", "meat_gold.png", "meat-solid-full.png"],
    "noun_meat_10038": ["meat_gold.png", "meat_white.png", "meat-solid-full.png"],
    "noun_meat": ["meat_gold.png", "meat_white.png", "meat-solid-full.png"],
    "percent-solid-full": ["percent_green.png", "percent_white.png", "percent_gold.png", "percent-solid-full.svg"],
    "percent-solid-full.svg": ["percent_green.png", "percent_white.png", "percent_gold.png", "percent-solid-full.svg"],
    "percent": ["percent_green.png", "percent_white.png", "percent_gold.png"],
    "percent_green": ["percent_green.png", "percent_white.png"],
    "percent_white": ["percent_white.png", "percent_green.png"],
    "percent_gold": ["percent_gold.png", "percent_white.png"],
    "coins_white": ["coins_white.png", "coins-solid-full.svg", "coins_gold.png"],
    "coins_white.png": ["coins_white.png", "coins-solid-full.svg", "coins_gold.png"],
}


def get_asset_path(filename: str) -> str:
    """Return absolute path for an asset located in imgs/, img/, or icons/ folder.
    Supports canonical aliases, space normalization, bundled resources (sys._MEIPASS),
    and local writable paths.
    """
    clean_name = filename.strip()
    key = clean_name.lower()

    # Build prioritized candidate names list
    candidates = [clean_name]
    if key in _ASSET_ALIASES:
        for alias in _ASSET_ALIASES[key]:
            if alias not in candidates:
                candidates.append(alias)

    # If key has no extension, try with .jpg, .png, .ico, .svg
    if "." not in clean_name:
        for ext in [".png", ".jpg", ".ico", ".svg"]:
            cand_ext = clean_name + ext
            if cand_ext not in candidates:
                candidates.append(cand_ext)
            cand_ext_lower = key + ext
            if cand_ext_lower in _ASSET_ALIASES:
                for alias in _ASSET_ALIASES[cand_ext_lower]:
                    if alias not in candidates:
                        candidates.append(alias)

    # Add space-stripped variant
    no_spaces = clean_name.replace(" ", "")
    if no_spaces not in candidates:
        candidates.append(no_spaces)
    if "." not in no_spaces:
        for ext in [".png", ".jpg", ".ico", ".svg"]:
            cand_ext = no_spaces + ext
            if cand_ext not in candidates:
                candidates.append(cand_ext)

    # Search in canonical locations: imgs/ (brand assets) -> icons/ (UI icons) -> root
    for folder in ["imgs", "icons", "img", ""]:
        for cand in candidates:
            rel = os.path.join(folder, cand) if folder else cand
            # 1. Bundled resource (PyInstaller sys._MEIPASS or dev root)
            res_p = get_resource_path(rel)
            if os.path.exists(res_p):
                return res_p

            # 2. Local writable path next to executable or dev root
            wri_p = get_writable_path(rel)
            if os.path.exists(wri_p):
                return wri_p

    # Fallback to direct path in imgs
    return get_resource_path(os.path.join("imgs", clean_name))


def set_window_icon(window) -> None:
    """Set high-resolution window and taskbar icon using icono.ico (and icono.png fallback)."""
    try:
        ico_path = get_asset_path("icono.ico")
        if not os.path.exists(ico_path):
            ico_path = get_asset_path("icono.png")

        if os.path.exists(ico_path):
            if sys.platform.startswith("win") and ico_path.lower().endswith(".ico"):
                try:
                    window.iconbitmap(default=os.path.abspath(ico_path))
                except Exception:
                    pass
                try:
                    window.iconbitmap(os.path.abspath(ico_path))
                except Exception:
                    pass

            png_path = get_asset_path("icono.png")
            if os.path.exists(png_path):
                from PIL import Image, ImageTk
                img = Image.open(png_path)
                photo = ImageTk.PhotoImage(img)
                window._app_icon_photo_ref = photo
                try:
                    window.iconphoto(True, photo)
                except Exception:
                    pass
            elif ico_path.lower().endswith(".png"):
                from PIL import Image, ImageTk
                img = Image.open(ico_path)
                photo = ImageTk.PhotoImage(img)
                window._app_icon_photo_ref = photo
                try:
                    window.iconphoto(True, photo)
                except Exception:
                    pass
    except Exception as e:
        import logging
        logging.warning("No se pudo establecer el icono de la ventana: %s", e)


def _apply_modal_backdrop(toplevel, root) -> None:
    """Create a sleek dark semi-transparent backdrop over root while toplevel is open."""
    try:
        if getattr(toplevel, "_has_modal_backdrop", False):
            return
        toplevel._has_modal_backdrop = True

        rx = root.winfo_rootx()
        ry = root.winfo_rooty()
        rw = root.winfo_width()
        rh = root.winfo_height()

        if rw <= 100 or rh <= 100:
            return

        import tkinter as tk
        backdrop = tk.Toplevel(root)
        backdrop.overrideredirect(True)
        backdrop.configure(bg="#050811")
        try:
            backdrop.attributes("-alpha", 0.55)  # 55% smooth dark dimmer
        except Exception:
            pass

        backdrop.geometry(f"{rw}x{rh}+{rx}+{ry}")
        backdrop.lift(root)
        toplevel.lift(backdrop)
        toplevel._modal_backdrop = backdrop

        def _on_destroy(event=None):
            try:
                if event and getattr(event, "widget", None) != toplevel:
                    return
                if backdrop.winfo_exists():
                    backdrop.destroy()
            except Exception:
                pass

        toplevel.bind("<Destroy>", _on_destroy, add="+")

        # Keep modal in front and active if backdrop is clicked
        def _on_backdrop_click(event=None):
            try:
                if toplevel.winfo_exists():
                    toplevel.lift()
                    toplevel.focus_force()
            except Exception:
                pass

        backdrop.bind("<Button-1>", _on_backdrop_click)
    except Exception:
        pass


def center_modal(toplevel, width: int, height: int, parent=None, enable_backdrop: bool = True) -> None:
    """Explicitly center a modal window on the screen with full Windows DPI scaling awareness.
    Guarantees the dialog is always vertically and horizontally centered in the screen / parent,
    and applies a sleek dark dimmer backdrop over the parent application window.
    """
    set_window_icon(toplevel)
    toplevel.update_idletasks()

    # Determine scaling factor (CustomTkinter window scaling)
    scale = 1.0
    if hasattr(toplevel, "_get_window_scaling"):
        try:
            scale = float(toplevel._get_window_scaling())
        except Exception:
            scale = 1.0

    actual_w = int(round(width * scale))
    actual_h = int(round(height * scale))

    # Obtain screen workarea (excluding Windows taskbar) or primary monitor resolution
    screen_w = toplevel.winfo_screenwidth()
    screen_h = toplevel.winfo_screenheight()
    wa_left, wa_top, wa_w, wa_h = 0, 0, screen_w, screen_h

    # Find the top-level root window (the main application window) if available
    root = None
    if parent:
        try:
            root = parent.winfo_toplevel()
        except Exception:
            root = None
    if not root and hasattr(toplevel, "master") and toplevel.master:
        try:
            root = toplevel.master.winfo_toplevel()
        except Exception:
            root = None

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.DWORD),
                    ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT),
                    ('dwFlags', wintypes.DWORD)
                ]
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            hwnd = 0
            if root:
                try:
                    hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
                except Exception:
                    hwnd = 0
            if not hwnd:
                try:
                    hwnd = ctypes.windll.user32.GetParent(toplevel.winfo_id()) or toplevel.winfo_id()
                except Exception:
                    hwnd = 0
            hMon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            if hMon and ctypes.windll.user32.GetMonitorInfoW(hMon, ctypes.byref(mi)):
                wa_left = int(mi.rcWork.left)
                wa_top = int(mi.rcWork.top)
                wa_w = max(100, int(mi.rcWork.right - mi.rcWork.left))
                wa_h = max(100, int(mi.rcWork.bottom - mi.rcWork.top))
            else:
                user32 = ctypes.windll.user32
                class RECT(ctypes.Structure):
                    _fields_ = [
                        ('left', ctypes.c_long),
                        ('top', ctypes.c_long),
                        ('right', ctypes.c_long),
                        ('bottom', ctypes.c_long)
                    ]
                wa = RECT()
                if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0):
                    wa_left = int(wa.left)
                    wa_top = int(wa.top)
                    wa_w = max(100, int(wa.right - wa.left))
                    wa_h = max(100, int(wa.bottom - wa.top))
        except Exception:
            pass

    # Backdrop over root if available
    if root and hasattr(root, "winfo_ismapped") and root.winfo_ismapped() and root.winfo_width() > 200:
        if enable_backdrop:
            _apply_modal_backdrop(toplevel, root)

    # USER REQUIREMENT: Modals and forms must ALWAYS appear in the exact center of the screen
    center_x = wa_left + wa_w // 2
    center_y = wa_top + wa_h // 2

    # Calculate top-left x, y
    x = center_x - actual_w // 2
    y = center_y - actual_h // 2

    # Ensure effective height doesn't exceed screen work area (accounting for Windows taskbar & titlebar)
    safe_margin_bottom = 50
    safe_margin_top = 10
    max_safe_h = max(200, wa_h - (safe_margin_bottom + safe_margin_top))

    effective_h = height
    if actual_h > max_safe_h:
        effective_h = max(200, int(max_safe_h / scale))
        actual_h = int(round(effective_h * scale))

    # Prevent modal from being positioned off-screen or stuck below workarea
    if y + actual_h > wa_top + wa_h - safe_margin_bottom:
        y = max(wa_top + safe_margin_top, wa_top + wa_h - actual_h - safe_margin_bottom)
    if y < wa_top + safe_margin_top:
        y = wa_top + safe_margin_top

    if x + actual_w > wa_left + wa_w - 10:
        x = max(wa_left + 10, wa_left + wa_w - actual_w - 10)
    if x < wa_left + 10:
        x = wa_left + 10

    toplevel.geometry(f"{width}x{effective_h}+{x}+{y}")

    # Micro-recenter verification after window is mapped to avoid Windows titlebar offset drift
    after_ids = []

    def _cancel_afters(e=None):
        try:
            if e and getattr(e, "widget", None) != toplevel:
                return
            for aid in list(after_ids):
                try:
                    toplevel.after_cancel(aid)
                except Exception:
                    pass
            after_ids.clear()
        except Exception:
            pass

    def _reverify_center():
        try:
            if not toplevel.winfo_exists():
                return
            curr_w = toplevel.winfo_width()
            curr_h = toplevel.winfo_height()
            if curr_w > 50 and curr_h > 50:
                cur_x = center_x - curr_w // 2
                cur_y = center_y - curr_h // 2
                if cur_y + curr_h > wa_top + wa_h - safe_margin_bottom:
                    cur_y = max(wa_top + safe_margin_top, wa_top + wa_h - curr_h - safe_margin_bottom)
                if cur_y < wa_top + safe_margin_top:
                    cur_y = wa_top + safe_margin_top
                if cur_x + curr_w > wa_left + wa_w - 10:
                    cur_x = max(wa_left + 10, wa_left + wa_w - curr_w - 10)
                if cur_x < wa_left + 10:
                    cur_x = wa_left + 10
                toplevel.geometry(f"+{cur_x}+{cur_y}")
        except Exception:
            pass

    try:
        toplevel.bind("<Destroy>", _cancel_afters, add="+")
        aid1 = toplevel.after(40, _reverify_center)
        aid2 = toplevel.after(120, _reverify_center)
        after_ids.extend([aid1, aid2])
    except Exception:
        pass


def build_standard_modal_header(
    parent_modal: Any,
    title_text: str = "",
    title_icon: Optional[Any] = None,
    icon_name: Optional[str] = None,
    on_close_cmd: Optional[Callable[[], None]] = None,
    show_close_btn: bool = False,
    text_color: str = "#C5A059",
    height: int = 50,
    title_below_topbar: bool = True
) -> Tuple[Any, Any]:
    """Builds the standardized executive topbar across all modals in Carnicería San Diego:
    - Topbar (full width, dark background #13151B):
        * Left: Official San Diego horizontal brand logo ('logoHorizontal.png')
        * Right: HunzaIA corporate emblem ('hunzaia.png') + optional close button ('✕')
    - 1px divider underneath topbar (#252836)
    - Below topbar: Centered executive title banner with contextual icon in brand golden-ochre (#C5A059)
      using Cambria Bold Italic typography.
    Returns (topbar_frame, title_label).
    """
    import customtkinter as ctk

    topbar = ctk.CTkFrame(parent_modal, height=height, fg_color="#13151B", corner_radius=0)
    topbar.pack(fill="x", side="top")
    topbar.pack_propagate(False)

    tb_content = ctk.CTkFrame(topbar, fg_color="transparent")
    tb_content.pack(fill="both", expand=True, padx=16)

    # 1. Left: Official San Diego Horizontal Logo
    left_box = ctk.CTkFrame(tb_content, fg_color="transparent")
    left_box.pack(side="left", fill="y")

    logo_img = get_ctk_icon("logoHorizontal.png", size=(125, 40))
    if logo_img:
        ctk.CTkLabel(left_box, text="", image=logo_img).pack(side="left")
    else:
        ctk.CTkLabel(
            left_box,
            text="SAN DIEGO\nCORTES MADURADOS",
            font=ctk.CTkFont(family="Cambria", size=11, weight="bold"),
            text_color="#C5A059"
        ).pack(side="left")

    # 2. Right: HunzaIA partner emblem + Optional close button
    right_box = ctk.CTkFrame(tb_content, fg_color="transparent")
    right_box.pack(side="right", fill="y")

    hunzaia_img = get_ctk_icon("hunzaia.png", size=(28, 32))
    if hunzaia_img:
        ctk.CTkLabel(right_box, text="", image=hunzaia_img).pack(side="right", padx=(8, 0))

    # Note: Topbar X button removed across all modules as requested by user; modals use footer buttons and Escape key.

    # 1px border divider below topbar
    ctk.CTkFrame(parent_modal, height=1, fg_color="#252836", corner_radius=0).pack(fill="x", side="top")

    # Dynamic contextual action color resolution based on user preference:
    # - Crear / Nuevo / Registrar / Entrada: Light green (#80C567)
    # - Ver / Detalle / Consulta / Ficha / Factura: Light violet (#666BC5)
    # - Editar / Modificar / Ajustar: Light orange (#DE6E22)
    # - General / Default: Ochre Gold (#C5A059)
    if not text_color or text_color in ("#C5A059", "#FFFFFF"):
        low_t = (title_text or "").lower()
        if any(w in low_t for w in ["crear", "nuevo", "nueva", "registrar", "registro", "agregar", "entrada", "stock"]):
            text_color = "#80C567"
        elif any(w in low_t for w in ["ver", "detalle", "consulta", "ficha", "factura", "visualizar"]):
            text_color = "#666BC5"
        elif any(w in low_t for w in ["editar", "modificar", "ajustar", "cupo", "descuento", "precio"]):
            text_color = "#DE6E22"
        else:
            text_color = "#C5A059"

    # Resolve Title Icon with matching color tint
    resolved_ico = None
    if icon_name:
        resolved_ico = get_tinted_ctk_icon(icon_name, text_color, size=(16, 16)) or get_ctk_icon(icon_name, size=(16, 16))
    elif title_icon:
        # If title_icon is already a CTkImage, attempt to tint its PIL representation to text_color
        try:
            from PIL import ImageColor, Image
            raw_pil = getattr(title_icon, "_light_image", None)
            if raw_pil and hasattr(raw_pil, "convert"):
                raw_rgba = raw_pil.convert("RGBA")
                alpha = raw_rgba.split()[-1]
                rgb = ImageColor.getrgb(text_color)[:3]
                tinted_pil = Image.new("RGBA", raw_rgba.size, (*rgb, 255))
                tinted_pil.putalpha(alpha)
                ico_sz = getattr(title_icon, "_size", (16, 16))
                resolved_ico = ctk.CTkImage(light_image=tinted_pil, dark_image=tinted_pil, size=ico_sz)
        except Exception:
            resolved_ico = title_icon
        if not resolved_ico:
            resolved_ico = title_icon

    title_lbl = None
    if title_text:
        # Executive title banner centered strictly below topbar in Cambria Bold Italic with contextual action color
        sub_title_box = ctk.CTkFrame(parent_modal, fg_color="transparent")
        sub_title_box.pack(fill="x", side="top", pady=(8, 4))

        title_font = ctk.CTkFont(family="Cambria", size=14, weight="bold", slant="italic")

        if resolved_ico:
            title_lbl = ctk.CTkLabel(
                sub_title_box,
                image=resolved_ico,
                compound="left",
                text=f"  {title_text}",
                font=title_font,
                text_color=text_color
            )
        else:
            title_lbl = ctk.CTkLabel(
                sub_title_box,
                text=title_text,
                font=title_font,
                text_color=text_color
            )
        title_lbl.pack(anchor="center")

    return topbar, title_lbl


def ensure_assets() -> None:
    """Check and automatically synchronize/generate canonical assets in imgs/ and icons/."""
    if getattr(sys, 'frozen', False):
        return

    imgs_dir = get_writable_path("imgs")
    try:
        os.makedirs(imgs_dir, exist_ok=True)
    except Exception:
        pass

    target_png_ico = get_asset_path("icono.png")
    target_ico = get_asset_path("icono.ico")

    # Generate crisp multi-resolution .ico from icono.png if needed
    if os.path.exists(target_png_ico):
        crisp_ico_imgs = os.path.join(imgs_dir, "icono.ico")
        if not os.path.exists(crisp_ico_imgs):
            try:
                pil_icon = Image.open(target_png_ico)
                pil_icon.save(
                    crisp_ico_imgs,
                    format="ICO",
                    sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
                )
            except Exception:
                pass

    # Ensure logout icon exists in imgs/
    target_logout = get_asset_path("logout_icon.png")
    if not os.path.exists(target_logout):
        logout_dest = os.path.join(imgs_dir, "logout_icon.png")
        create_logout_icon(logout_dest)

    # Ensure flame icons exist in imgs/
    flame_on_imgs = os.path.join(imgs_dir, "flame_active.png")
    flame_off_imgs = os.path.join(imgs_dir, "flame_inactive.png")
    if not os.path.exists(flame_on_imgs):
        generate_flame_icon(active=True).save(flame_on_imgs)
    if not os.path.exists(flame_off_imgs):
        generate_flame_icon(active=False).save(flame_off_imgs)

    # Fallback placeholder generation only if brand assets are missing
    logo_path = get_asset_path("logoCompleto.png")
    fondo_path = get_asset_path("fondoLogin.png")
    if not os.path.exists(logo_path):
        create_logo(os.path.join(imgs_dir, "logoCompleto.png"))
    if not os.path.exists(fondo_path):
        create_background(os.path.join(imgs_dir, "fondoLogin.png"))

    # Ensure white coins icon exists in icons/
    icons_dir = get_writable_path("icons")
    try:
        os.makedirs(icons_dir, exist_ok=True)
    except Exception:
        pass
    coins_w_dest = os.path.join(icons_dir, "coins_white.png")
    if not os.path.exists(coins_w_dest):
        coins_svg = get_asset_path("coins-solid-full.svg")
        if os.path.exists(coins_svg):
            try:
                import resvg_py, io
                with open(coins_svg, "r", encoding="utf-8") as f:
                    svg_d = f.read()
                b = resvg_py.svg_to_bytes(svg_d)
                sp = Image.open(io.BytesIO(b)).convert("RGBA")
                a = sp.split()[-1]
                wi = Image.new("RGBA", sp.size, (255, 255, 255, 255))
                wi.putalpha(a)
                wi.save(coins_w_dest)
            except Exception:
                pass


def generate_flame_icon(active: bool = True, size: tuple = (48, 48)) -> Image.Image:
    """Generate high-resolution anti-aliased flame icon (burning or struck-through)."""
    scale = 4
    w, h = size[0] * scale, size[1] * scale
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    pts = [
        (0.48, 0.06), # main top tip
        (0.55, 0.18),
        (0.68, 0.30),
        (0.78, 0.45),
        (0.82, 0.62),
        (0.78, 0.80),
        (0.68, 0.92),
        (0.50, 0.96), # bottom base
        (0.32, 0.92),
        (0.22, 0.80),
        (0.18, 0.62),
        (0.22, 0.48),
        (0.30, 0.40),
        (0.35, 0.48), # interior swirl dip
        (0.38, 0.32),
        (0.42, 0.20),
    ]
    coords = [(x * w, y * h) for x, y in pts]

    if active:
        # Fiery bright amber-gold
        draw.polygon(coords, fill=(245, 158, 11, 255))
        # Inner flame core (bright warm yellow/white)
        inner_pts = [
            (0.49, 0.38),
            (0.58, 0.52),
            (0.64, 0.68),
            (0.60, 0.84),
            (0.50, 0.92),
            (0.40, 0.84),
            (0.36, 0.68),
            (0.42, 0.52),
        ]
        inner_coords = [(x * w, y * h) for x, y in inner_pts]
        draw.polygon(inner_coords, fill=(254, 240, 138, 255))
    else:
        # Muted slate/charcoal flame
        draw.polygon(coords, fill=(100, 116, 139, 210))
        inner_pts = [
            (0.49, 0.38),
            (0.58, 0.52),
            (0.64, 0.68),
            (0.60, 0.84),
            (0.50, 0.92),
            (0.40, 0.84),
            (0.36, 0.68),
            (0.42, 0.52),
        ]
        inner_coords = [(x * w, y * h) for x, y in inner_pts]
        draw.polygon(inner_coords, fill=(51, 65, 85, 230))

        # Strike-through diagonal red slash (top-left to bottom-right)
        line_w = int(2.5 * scale)
        draw.line([(0.12 * w, 0.14 * h), (0.88 * w, 0.88 * h)], fill=(239, 68, 68, 255), width=line_w)

    return im.resize(size, Image.Resampling.LANCZOS)


def create_logo(output_path: str) -> None:
    """Generate a stylized XL Burguer emblem with transparent background if missing."""
    size = (600, 600)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    center_x = size[0] // 2
    center_y = 230

    # Outer decorative circle / shield
    radius_outer = 190
    draw.ellipse(
        [
            center_x - radius_outer,
            center_y - radius_outer,
            center_x + radius_outer,
            center_y + radius_outer,
        ],
        outline=(239, 68, 68, 255),  # Crimson red #EF4444
        width=8,
    )

    # Inner decorative dashed/thinner circle
    radius_inner = 175
    draw.ellipse(
        [
            center_x - radius_inner,
            center_y - radius_inner,
            center_x + radius_inner,
            center_y + radius_inner,
        ],
        outline=(245, 158, 11, 240),  # Amber gold accent #F59E0B
        width=4,
    )

    # Dark badge fill behind emblem
    draw.ellipse(
        [
            center_x - (radius_inner - 4),
            center_y - (radius_inner - 4),
            center_x + (radius_inner - 4),
            center_y + (radius_inner - 4),
        ],
        fill=(26, 17, 16, 240),
    )

    # Typography fonts
    font_xl = None
    font_main = None
    font_sub = None
    try:
        font_xl = ImageFont.truetype("arialbd.ttf", 110)
        font_main = ImageFont.truetype("arialbd.ttf", 32)
        font_sub = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font_xl = ImageFont.load_default()
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Draw "XL" center emblem
    bbox_xl = draw.textbbox((0, 0), "XL", font=font_xl)
    xl_w = bbox_xl[2] - bbox_xl[0]
    xl_h = bbox_xl[3] - bbox_xl[1]
    draw.text(
        (center_x - xl_w // 2, center_y - xl_h // 2 - 10),
        "XL",
        fill=(245, 158, 11, 255),
        font=font_xl,
    )

    # Decorative banner below emblem
    banner_y = 440
    draw.rectangle(
        [center_x - 240, banner_y - 30, center_x + 240, banner_y + 35],
        fill=(220, 38, 38, 255),
        outline=(245, 158, 11, 255),
        width=3,
    )

    # Text: XL BURGUER
    text_main = "XL BURGUER"
    bbox_main = draw.textbbox((0, 0), text_main, font=font_main)
    text_w = bbox_main[2] - bbox_main[0]
    draw.text(
        (center_x - text_w // 2, banner_y - 20),
        text_main,
        fill=(255, 255, 255, 255),
        font=font_main,
    )

    # Subtitle: COMIDAS RÁPIDAS & HAMBURGUESAS
    text_sub = "COMIDAS RÁPIDAS & HAMBURGUESAS"
    bbox_sub = draw.textbbox((0, 0), text_sub, font=font_sub)
    sub_w = bbox_sub[2] - bbox_sub[0]
    draw.text(
        (center_x - sub_w // 2, banner_y + 55),
        text_sub,
        fill=(245, 158, 11, 255),
        font=font_sub,
    )

    # Save PNG
    image.save(output_path, "PNG")


def create_background(output_path: str) -> None:
    """Generate subtle textured gourmet dark burgundy gradient for login background."""
    width, height = 1280, 800
    image = Image.new("RGB", (width, height), (26, 17, 16))
    draw = ImageDraw.Draw(image)

    for y in range(height):
        factor_y = (y / height)
        for step in range(0, width, 16):
            dx = abs(step - width // 2) / (width // 2)
            dist = (dx**2 + (factor_y - 0.4)**2)**0.5
            dist = min(1.0, dist)

            r = int((53 * (1 - dist)) + (19 * dist))
            g = int((28 * (1 - dist)) + (11 * dist))
            b = int((25 * (1 - dist)) + (10 * dist))

            draw.rectangle([step, y, step + 16, y + 1], fill=(r, g, b))

    for x in range(0, width, 120):
        for y in range(0, height, 120):
            draw.line([(x, y + 20), (x + 20, y)], fill=(45, 26, 24), width=1)

    image.save(output_path, "PNG")


def create_logout_icon(output_path: str) -> None:
    """Generate high-DPI modern exit/logout icon (doorway frame + outward arrow)."""
    try:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = (248, 113, 113, 255)  # Crimson red #F87171
        width = 4
        # Door frame bracket:
        draw.line([(32, 12), (16, 12)], fill=color, width=width)
        draw.line([(16, 12), (16, 52)], fill=color, width=width)
        draw.line([(16, 52), (32, 52)], fill=color, width=width)
        # Arrow shaft:
        draw.line([(24, 32), (48, 32)], fill=color, width=width)
        # Arrow head:
        draw.line([(40, 24), (48, 32)], fill=color, width=width)
        draw.line([(40, 40), (48, 32)], fill=color, width=width)
        img.save(output_path, "PNG")
    except Exception as e:
        import logging
        logging.warning("No se pudo generar logout_icon.png: %s", e)


def create_icon(logo_path: str, icon_path: str) -> None:
    """Generate .ico file from logo.png for PyInstaller and window icons."""
    try:
        img = Image.open(logo_path)
        img.save(
            icon_path,
            format="ICO",
            sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)],
        )
    except Exception as e:
        print(f"Warning generating ICO: {e}")

_PIL_IMAGE_CACHE: dict = {}


def get_ctk_icon(name: str, size: tuple = (20, 20)):
    """Retrieve or create a CTkImage for any icon in icons/ or imgs/.
    Caches the underlying PIL.Image in memory for blazing performance while avoiding
    Tkinter Tcl interpreter invalidation across destroyed test or window roots.
    Returns None gracefully if the icon image file is not found.
    """
    if name in _PIL_IMAGE_CACHE:
        pil_img = _PIL_IMAGE_CACHE[name]
    else:
        path = get_asset_path(name if "." in name else f"{name}.png")
        if not os.path.exists(path):
            path = get_asset_path(name)

        if os.path.exists(path):
            if path.lower().endswith(".svg"):
                try:
                    import resvg_py, io
                    with open(path, "r", encoding="utf-8") as f:
                        svg_data = f.read()
                    png_bytes = resvg_py.svg_to_bytes(svg_data)
                    svg_pil = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                    alpha = svg_pil.split()[-1]
                    white_img = Image.new("RGBA", svg_pil.size, (255, 255, 255, 255))
                    white_img.putalpha(alpha)
                    pil_img = white_img
                    _PIL_IMAGE_CACHE[name] = pil_img
                except Exception as e:
                    import logging
                    logging.warning("Error renderizando SVG '%s': %s", name, e)
                    return None
            else:
                try:
                    pil_img = Image.open(path).convert("RGBA")
                    _PIL_IMAGE_CACHE[name] = pil_img
                except Exception as e:
                    import logging
                    logging.warning("Error cargando imagen PIL '%s': %s", name, e)
                    return None
        else:
            return None

    try:
        import customtkinter as ctk
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
    except Exception as e:
        import logging
        logging.warning("Error creando CTkImage '%s': %s", name, e)
        return None


def get_tinted_ctk_icon(name: str, color_hex: str, size: tuple = (20, 20)):
    """Retrieve or create a color-tinted CTkImage for any icon in icons/ or imgs/.
    Re-colors non-transparent pixels to the exact target color hex while preserving the alpha mask.
    Caches the tinted PIL image in memory.
    """
    cache_key = (name, color_hex)
    if cache_key in _PIL_IMAGE_CACHE:
        pil_img = _PIL_IMAGE_CACHE[cache_key]
    else:
        path = get_asset_path(name if "." in name else f"{name}.png")
        if not os.path.exists(path):
            path = get_asset_path(name)

        if not os.path.exists(path):
            return None

        try:
            from PIL import ImageColor
            if path.lower().endswith(".svg"):
                import resvg_py, io
                with open(path, "r", encoding="utf-8") as f:
                    svg_data = f.read()
                png_bytes = resvg_py.svg_to_bytes(svg_data)
                raw_pil = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
            else:
                raw_pil = Image.open(path).convert("RGBA")

            alpha = raw_pil.split()[-1]
            rgb = ImageColor.getrgb(color_hex)[:3]
            tinted_img = Image.new("RGBA", raw_pil.size, (*rgb, 255))
            tinted_img.putalpha(alpha)
            pil_img = tinted_img
            _PIL_IMAGE_CACHE[cache_key] = pil_img
        except Exception as e:
            import logging
            logging.warning("Error tinting icon '%s' with color '%s': %s", name, color_hex, e)
            return None

    try:
        import customtkinter as ctk
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
    except Exception as e:
        import logging
        logging.warning("Error creando tinted CTkImage '%s': %s", name, e)
        return None



if __name__ == "__main__":
    ensure_assets()
    print("Assets generated successfully.")
