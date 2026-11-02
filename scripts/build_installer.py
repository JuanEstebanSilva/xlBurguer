"""Automated Build & Packaging Pipeline for XL Burguer.
Compiles the application with PyInstaller and builds the professional
Inno Setup Windows Installer executable.
"""

import os
import sys
import subprocess
import shutil

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def find_iscc() -> str:
    """Locate Inno Setup Compiler executable."""
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Inno Setup 6", "ISCC.exe"),
        "ISCC.exe"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Try PATH
    path_iscc = shutil.which("ISCC.exe")
    if path_iscc:
        return path_iscc
    raise FileNotFoundError("No se encontró el compilador de Inno Setup (ISCC.exe). Instálelo con winget install JRSoftware.InnoSetup")


def build_pipeline():
    print("=" * 70)
    print("[PIPELINE DE COMPILACION E INSTALADOR: XL BURGUER POS]")
    print("=" * 70)

    # 1. Compilar con PyInstaller (main.py -> dist/XLBurguer)
    print("\n[Paso 1/3] Compilando ejecutable standalone con PyInstaller...")
    from build_exe import build
    build()

    # 2. Verificar artefactos de distribución
    print("\n[Paso 2/3] Verificando integridad de la carpeta de distribución...")
    dist_app = os.path.join(_PROJECT_ROOT, "dist", "XLBurguer")
    main_exe = os.path.join(dist_app, "XLBurguer.exe")
    if not os.path.exists(main_exe):
        raise FileNotFoundError(f"Fallo en la compilación: no se encontró {main_exe}")

    db_path = os.path.join(dist_app, "xlburguer.db")
    if os.path.exists(db_path) and "--include-db" not in sys.argv:
        try:
            os.remove(db_path)
            print("  [-] Base de datos local removida del paquete de distribución para proteger datos del cliente.")
        except Exception as e:
            print(f"  [!] Aviso: {e}")

    # 3. Compilar instalador con Inno Setup
    print("\n[Paso 3/3] Compilando instalador comercial para Windows...")
    iscc_path = find_iscc()
    print(f"  Usando compilador Inno Setup: {iscc_path}")

    iss_file = os.path.join(_PROJECT_ROOT, "installer", "XLBurguer.iss")
    if not os.path.exists(iss_file):
        raise FileNotFoundError(f"No se encontró el script de Inno Setup: {iss_file}")

    installer_output_dir = os.path.join(_PROJECT_ROOT, "dist", "installer")
    os.makedirs(installer_output_dir, exist_ok=True)

    cmd = [iscc_path, iss_file]
    print(f"  Ejecutando: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=os.path.join(_PROJECT_ROOT, "installer"), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print("ERROR al compilar el instalador:")
        print(res.stderr or res.stdout)
        sys.exit(res.returncode)

    installer_exe = os.path.join(installer_output_dir, "Instalador_XLBurguer_v1.0.exe")
    if os.path.exists(installer_exe):
        size_mb = os.path.getsize(installer_exe) / (1024 * 1024)
        print("\n" + "=" * 70)
        print("[OK] INSTALADOR GENERADO EXITOSAMENTE!")
        print(f"   Ubicación : {installer_exe}")
        print(f"   Tamaño    : {size_mb:.2f} MB")
        print("=" * 70)
    else:
        print("ADVERTENCIA: El proceso finalizó pero no se detectó el archivo de salida.")


if __name__ == "__main__":
    build_pipeline()


if __name__ == "__main__":
    build_pipeline()
