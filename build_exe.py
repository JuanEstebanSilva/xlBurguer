"""Automated PyInstaller Build Script for XL Burguer POS.

Packages the entire offline desktop application into a standalone Windows
executable (--onedir). Includes CustomTkinter themes/assets, Pillow, openpyxl,
pywin32 DLLs (with runtime hook) and the SQLite schema.
"""

import os
import sys
import PyInstaller.__main__

# En producción comercial se compila en modo WINDOWED (True) sin consola negra.
# Pase el argumento '--console' por línea de comandos para compilar en modo consola si se requiere depuración.
WINDOWED_MODE = True
if "--console" in sys.argv:
    WINDOWED_MODE = False

# Separador de rutas de datos según plataforma
_SEP = ";" if sys.platform.startswith("win") else ":"


def build() -> None:
    print("=================================================================")
    print("   Compilación PyInstaller: XL Burguer POS")
    print("=================================================================")

    mode_str = "WINDOWED (Sin consola)" if WINDOWED_MODE else "CONSOLE (Con consola para depuración)"
    print(f"Modo seleccionado: {mode_str}\n")

    icon_candidate = "imgs/icono.ico" if os.path.exists("imgs/icono.ico") else ""
    icon_arg = [f"--icon={icon_candidate}"] if icon_candidate else []
    mode_arg = ["--windowed"] if WINDOWED_MODE else ["--console"]

    # Runtime hook: debe correr ANTES que el código de aplicación para
    # registrar las rutas de DLL de pywin32 en sys.path y AddDllDirectory.
    runtime_hook_path = os.path.join("pyinstaller_hooks", "rthook_pywin32.py")
    runtime_hook_arg = (
        [f"--runtime-hook={runtime_hook_path}"]
        if os.path.exists(runtime_hook_path)
        else []
    )
    if not runtime_hook_arg:
        print("ADVERTENCIA: No se encontró pyinstaller_hooks/rthook_pywin32.py")

    data_args = []
    if os.path.exists("imgs"):
        data_args.append(f"--add-data=imgs{_SEP}imgs")
    if os.path.exists("icons"):
        data_args.append(f"--add-data=icons{_SEP}icons")
    data_args.append(f"--add-data=database/schema.sql{_SEP}database")

    args = [
        "main.py",
        "--name=XLBurguer",
        "--onedir",
        # ── Colecciones de paquetes ────────────────────────────────────────
        "--collect-all=customtkinter",
        "--collect-all=openpyxl",
        "--collect-all=PIL",
        # pywin32 — CRÍTICO: empaqueta pywintypes*.dll y pythoncom*.dll
        "--collect-all=win32api",
        "--collect-all=win32print",
        "--collect-all=win32ui",
        "--collect-all=pywintypes",
        "--collect-all=pythoncom",
        "--collect-all=serial",
        # ── Hidden imports de pywin32 ─────────────────────────────────────
        "--hidden-import=win32api",
        "--hidden-import=win32con",
        "--hidden-import=win32print",
        "--hidden-import=win32gui",
        "--hidden-import=win32ui",
        "--hidden-import=pywintypes",
        "--hidden-import=pythoncom",
        "--hidden-import=winerror",
        # ── Hidden imports de Tkinter ──────────────────────────────────────
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.messagebox",
        "--hidden-import=tkinter.filedialog",
        "--hidden-import=_tkinter",
        # ── Hidden imports de serial ───────────────────────────────────────
        "--hidden-import=serial",
        "--hidden-import=serial.tools",
        "--hidden-import=serial.tools.list_ports",
        # ── Hidden imports de la aplicación ────────────────────────────────
        "--hidden-import=utils.navbar_animator",
        "--hidden-import=utils.sound_manager",
        "--hidden-import=utils.theme",
        "--hidden-import=utils.asset_manager",
        "--hidden-import=database.connection",
        "--hidden-import=models.customer",
        "--hidden-import=models.product",
        "--hidden-import=models.ingredient",
        "--hidden-import=models.sale",
        "--hidden-import=models.user",
        "--hidden-import=models.cash_shift",
        "--hidden-import=views.about_modal",
        "--hidden-import=views.calendar_modal",
        "--hidden-import=views.users_frame",
        "--hidden-import=views.inventory_frame",
        "--hidden-import=views.pos_frame",
        "--hidden-import=views.stats_frame",
        "--hidden-import=views.login_frame",
        "--hidden-import=views.recipe_modal",
        "--hidden-import=views.ingredients_modal",
        # ── Opciones de compilación ───────────────────────────────────────
        "--noconfirm",
        "--clean",
    ] + mode_arg + icon_arg + runtime_hook_arg + data_args

    print(f"Ejecutando PyInstaller con argumentos:\n{chr(10).join('  ' + a for a in args)}\n")
    PyInstaller.__main__.run(args)

    # No copiar la BD de desarrollo por defecto para evitar enviar datos locales al cliente
    if "--include-db" in sys.argv and os.path.exists("xlburguer.db"):
        import shutil
        target_db = os.path.join("dist", "XLBurguer", "xlburguer.db")
        try:
            shutil.copy2("xlburguer.db", target_db)
            print(f"Base de datos copiada exitosamente a: {target_db}")
        except Exception as e:
            print(f"Advertencia al copiar xlburguer.db: {e}")
    else:
        print("Base de datos local omitida del empaquetado (la aplicación inicializa una BD limpia desde schema.sql).")

    # Copiar icono.ico a la raíz de la distribución y carpeta imgs para accesos directos
    if os.path.exists("imgs/icono.ico"):
        import shutil
        target_ico = os.path.join("dist", "XLBurguer", "icono.ico")
        target_imgs_dir = os.path.join("dist", "XLBurguer", "imgs")
        os.makedirs(target_imgs_dir, exist_ok=True)
        target_imgs_ico = os.path.join(target_imgs_dir, "icono.ico")
        try:
            shutil.copy2("imgs/icono.ico", target_ico)
            shutil.copy2("imgs/icono.ico", target_imgs_ico)
            print(f"Icono copiado exitosamente a: {target_ico} y {target_imgs_ico}")
        except Exception as e:
            print(f"Advertencia al copiar icono.ico: {e}")

    # Copiar printer_settings.json para asegurar impresora predeterminada
    if os.path.exists("printer_settings.json"):
        import shutil
        target_cfg = os.path.join("dist", "XLBurguer", "printer_settings.json")
        try:
            shutil.copy2("printer_settings.json", target_cfg)
            print(f"Configuración de impresora copiada exitosamente a: {target_cfg}")
        except Exception as e:
            print(f"Advertencia al copiar printer_settings.json: {e}")

    print("\n=================================================================")
    print("Compilación completada.")
    print("Directorio de salida : dist/XLBurguer/")
    print("Ejecutable principal : dist/XLBurguer/XLBurguer.exe")
    print("")
    print("VERIFICACIÓN RÁPIDA:")
    print("  1. Ejecute el EXE desde la consola del sistema para ver stderr")
    print("  2. Revise dist/XLBurguer/app_debug.log tras el login")
    print("  3. El log debe mostrar 'on_login_success' y 'Cambiando a: pos'")
    print("=================================================================")


if __name__ == "__main__":
    build()


if __name__ == "__main__":
    build()
