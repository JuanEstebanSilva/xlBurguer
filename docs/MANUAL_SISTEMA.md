# MANUAL OPERATIVO Y TÉCNICO DEL SISTEMA
## Carnicería San Diego — Villa de Leyva, Boyacá
### Sistema de Punto de Venta (POS), Inventario, Hardware & Gestión Comercial

---

## 1. INTRODUCCIÓN Y ARQUITECTURA GENERAL

**Carnicería San Diego POS** es una aplicación comercial de escritorio de alta gama, 100% nativa y fuera de línea (offline), desarrollada con Python 3.13, CustomTkinter (aceleración gráfica por hardware) y SQLite3 transaccional en modo WAL (Write-Ahead Logging).

### Componentes de la Arquitectura:
- **Capa de Presentación (Views):** Diseñada bajo el patrón *Single-Window Frame Switcher* en [main.py](file:///d:/Varios/Varios/GitHub/sanDiego/main.py) y [views/](file:///d:/Varios/Varios/GitHub/sanDiego/views/). Una sola ventana fluida con transiciones instantáneas entre Punto de Venta, Inventario, Estadísticas/Cierre de Caja y Clientes/Usuarios.
- **Capa de Negocio y Dominio (Models):** Clases de entidad y repositorios en [models/](file:///d:/Varios/Varios/GitHub/sanDiego/models/) con validaciones estrictas de moneda colombiana (COP sin decimales), gramaje (base 500g libra / 1000g kilo), cupos de crédito (fiados) y auditoría de ventas.
- **Capa de Integración de Hardware:** Drivers no bloqueantes en [hardware/](file:///d:/Varios/Varios/GitHub/sanDiego/hardware/) para básculas de pesaje serial (RS-232/USB COM), escáneres ópticos HID y spooling de tickets térmicos POS en Windows (`win32print`).
- **Capa de Persistencia y Datos (Database):** Administrada centralizadamente en [database/connection.py](file:///d:/Varios/Varios/GitHub/sanDiego/database/connection.py).

---

## 2. GESTIÓN Y PERSISTENCIA DE LA BASE DE DATOS

### 2.1. Fuente Única de Verdad: `sandiego.db`
El sistema opera con **una única base de datos relacional**: `sandiego.db`.
- **Integridad:** `PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;`
- **Tablas Principales:**
  1. `users`: Operadores, administradores y contraseñas hasheadas con PBKDF2-HMAC-SHA256 (600.000 iteraciones, estándar OWASP 2024+), con bloqueo tras 5 intentos fallidos.
  2. `categories`: Clasificación de carnes (Res, Cerdo, Pollo, Embutidos, Lácteos/Víveres).
  3. `customers`: Directorio comercial con Cédula/NIT, cupos empresariales y saldo deudor (`debt_balance`).
  4. `products`: Catálogo de cortes, precios por kilo/libra, costo, IVA y control de inventario en gramos.
  5. `sales`: Maestro de facturación, estado ('COMPLETADA', 'ANULADA'), medios de pago (Efectivo, Nequi, Daviplata, Tarjeta, Fiado), total, IVA y descuentos.
  6. `sale_items`: Detalle de renglones vendidos con peso real, precio unitario, subtotal y desglose de IVA por ítem.
  7. `company_product_quotas`: Precios diferenciales y cupos especiales pactados con restaurantes y hoteles locales.
  8. `cash_shifts`: Control de turnos y arqueos de caja (apertura, ventas en efectivo/electrónicas/fiado, retiros, efectivo esperado, contado y sobrante/faltante).
  9. `invoice_sequences`: Generador atómico de consecutivos estrictamente monótonos (evita huecos y reutilización).
  10. `audit_logs`: Bitácora inmutable de auditoría para operaciones críticas del sistema (anulaciones, modificaciones, etc.).

### 2.2. Ubicación de los Datos en Equipos de Producción
Para cumplir con las directivas de seguridad de Windows y evitar fallos de permisos al instalar en `C:\Program Files\`:
- **Ruta Estándar (Instalación con Instalador):**
  ```text
  %APPDATA%\CarniceriaSanDiego\sandiego.db
  (Equivalente a: C:\Users\<Usuario>\AppData\Roaming\CarniceriaSanDiego\sandiego.db)
  ```
- **Ruta Portable (Memoria USB / Carpeta Local):**
  Si existe un archivo llamado `.portable` junto al ejecutable `CarniceriaSanDiego.exe`, o si se define la variable de entorno `SANDIEGO_PORTABLE=1`, la base de datos se guarda y lee directamente en la misma carpeta del ejecutable.
- **Ruta de Desarrollo:**
  En entorno de desarrollo (`git clone`), el sistema utiliza directamente el archivo `sandiego.db` de la raíz del proyecto.

### 2.3. Inicialización Automática y Siembra de Datos
Cuando se instala la aplicación en un computador nuevo donde `%APPDATA%\CarniceriaSanDiego\sandiego.db` aún no existe:
1. El motor de conexión detecta la ausencia de la base de datos local.
2. Copia automáticamente la base de datos semilla bundled desde el directorio de instalación hacia `%APPDATA%\CarniceriaSanDiego\`.
3. Valida la integridad (`PRAGMA integrity_check`) y ejecuta cualquier migración de esquema pendiente de manera idempotente.
4. El usuario no pierde sus catálogos, configuraciones ni históricos en ningún momento.

### 2.4. Copias de Seguridad (Backups)
El módulo [database/connection.py](file:///d:/Varios/Varios/GitHub/sanDiego/database/connection.py) cuenta con la función `backup_database()`, la cual implementa la **API de Copia de Seguridad en Línea de SQLite (`sqlite3.Connection.backup`)**:
- Se puede ejecutar con la carnicería en pleno funcionamiento y sin detener las ventas ni bloquear el archivo.
- Genera un archivo con marca de tiempo: `sandiego_backup_YYYYMMDD_HHMMSS.db`.
- En equipos instalados, los respaldos se guardan en `%APPDATA%\CarniceriaSanDiego\backups\`.
- Para restaurar una copia de seguridad: basta con cerrar la aplicación, copiar el archivo de respaldo sobre `sandiego.db` y reiniciar el sistema.

---

## 3. INSTALACIÓN EN OTROS COMPUTADORES

### Requisitos del Sistema:
- **Sistema Operativo:** Windows 10 o Windows 11 (64 bits).
- **Hardware Mínimo:** Procesador Intel Core i3 / AMD Ryzen 3 o superior, 4 GB de memoria RAM, 200 MB de espacio en disco.
- **Dependencias Requeridas:** **Ninguna.** El instalador incorpora el entorno de ejecución, bibliotecas, motores gráficos y SQLite. No requiere instalar Python, Visual Studio ni administradores de paquetes.

### Procedimiento de Instalación Paso a Paso:
1. Copie el archivo `Instalador_Carniceria_SanDiego_v1.0.exe` a una memoria USB o descárguelo en el computador de destino.
2. Haga doble clic sobre `Instalador_Carniceria_SanDiego_v1.0.exe`.
3. Si el Control de Cuentas de Usuario (UAC) de Windows solicita confirmación, pulse **Sí**.
4. Seleccione el directorio de instalación (por defecto: `C:\Program Files\Carniceria San Diego`).
5. Marque la casilla **Crear un acceso directo en el Escritorio** y haga clic en **Instalar**.
6. En la pantalla final, pulse **Finalizar**. La aplicación se abrirá automáticamente maximizada a pantalla completa.

### Credenciales de Acceso Iniciales:
- **Administrador:**
  - **Usuario:** `admin`
  - **Contraseña:** `admin123`
- *Nota de Seguridad:* Se recomienda cambiar la contraseña del administrador desde el módulo de "Usuarios / Clientes" tras el primer ingreso.

---

## 4. SEGURIDAD Y PROTECCIÓN DE DATOS

1. **Protección del Código Fuente:**
   - La aplicación distribuida no incluye archivos de texto plano `.py`. Todo el código está precompilado en bytecode binario e integrado en un contenedor ejecutable nativo (`CarniceriaSanDiego.exe`).
   - El instalador excluye archivos de desarrollo, tests, entornos virtuales, metadatos Git y herramientas internas.
2. **Sin Ventana de Consola Negra:**
   - Compilado en modo nativo de Windows (`--windowed`). Las salidas de diagnóstico y errores no controlados se canalizan de forma segura al archivo `app_debug.log` en el directorio de datos de la aplicación.
3. **Manejo de Secretos:**
   - El sistema opera de forma local y soberana. No almacena credenciales de servicios en la nube ni tokens en texto claro.
   - Las contraseñas de los usuarios del sistema utilizan derivación criptográfica PBKDF2-HMAC-SHA256 con sal única por usuario.
4. **Protección de Datos Comerciales durante la Desinstalación:**
   - Si el usuario desinstala la aplicación desde el Panel de Control de Windows o Configuración, el desinstalador remueve los ejecutables de `Program Files` pero **preserva de forma deliberada** la carpeta `%APPDATA%\CarniceriaSanDiego\`. Esto evita que un error humano elimine el historial contable y las facturas de la carnicería.

---

## 5. PROCEDIMIENTO DE RECONSTRUCCIÓN DEL INSTALADOR

Para que el equipo de desarrollo pueda generar nuevas versiones del instalador en el futuro:

### Prerrequisitos en la máquina de desarrollo:
- Python 3.10+ con dependencias instaladas: `pip install -r requirements.txt pyinstaller`.
- Inno Setup 6 instalado (disponible mediante: `winget install JRSoftware.InnoSetup`).

### Comando Único de Compilación:
Ejecute desde la raíz del proyecto:
```powershell
python scripts/build_installer.py
```

El script ejecutará automáticamente:
1. Verificación y recolección de recursos gráficos e iconos.
2. Compilación del ejecutable standalone con PyInstaller (`build_exe.py`) en modo ventana.
3. Inyección de la base de datos semilla y configuraciones.
4. Compilación del instalador comercial con Inno Setup (`installer/CarniceriaSanDiego.iss`).
5. Generación del instalador final en: `dist/installer/Instalador_Carniceria_SanDiego_v1.0.exe`.
