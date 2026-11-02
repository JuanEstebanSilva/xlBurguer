# MANUAL OPERATIVO Y TÉCNICO DEL SISTEMA
## XL Burguer — Restaurante de Comidas Rápidas
### Sistema de Punto de Venta (POS), Recetas por Gramos, Inventario y Gestión Comercial

---

## 1. INTRODUCCIÓN Y ARQUITECTURA GENERAL

**XL Burguer POS** es una aplicación comercial de escritorio de alto rendimiento, 100% nativa y fuera de línea (offline), desarrollada con Python 3.10+, CustomTkinter (aceleración gráfica por hardware) y SQLite3 transaccional en modo WAL (Write-Ahead Logging).

### Componentes de la Arquitectura:
- **Capa de Presentación (Views):** Diseñada bajo el patrón *Single-Window Frame Switcher* en [main.py](file:///d:/Varios/Varios/GitHub/POS/xlBurguer/main.py) y [views/](file:///d:/Varios/Varios/GitHub/POS/xlBurguer/views/). Una sola ventana fluida con transiciones instantáneas entre Punto de Venta, Inventario/Recetas, Estadísticas/Cierre de Caja y Clientes/Usuarios.
- **Capa de Negocio y Dominio (Models):** Clases de entidad y repositorios en [models/](file:///d:/Varios/Varios/GitHub/POS/xlBurguer/models/) con control de inventario en gramos (`g`), recetas desagregadas, cálculo de porciones teóricas por ingrediente limitante, deducción atómica de existencias, moneda colombiana (COP sin centavos) y auditoría de ventas.
- **Capa de Integración de Hardware:** Drivers no bloqueantes en [hardware/](file:///d:/Varios/Varios/GitHub/POS/xlBurguer/hardware/) para escáneres ópticos USB HID y spooling de tickets térmicos POS de 40 columnas en Windows (`win32print`).
- **Capa de Persistencia y Datos (Database):** Administrada centralizadamente en [database/connection.py](file:///d:/Varios/Varios/GitHub/POS/xlBurguer/database/connection.py).

---

## 2. GESTIÓN Y PERSISTENCIA DE LA BASE DE DATOS

### 2.1. Fuente Única de Verdad: `xlburguer.db`
El sistema opera con **una única base de datos relacional**: `xlburguer.db`.
- **Integridad:** `PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;`
- **Tablas Principales:**
  1. `users`: Operadores, administradores y contraseñas hasheadas con PBKDF2-HMAC-SHA256 (600.000 iteraciones, estándar OWASP 2024+), con bloqueo tras 5 intentos fallidos.
  2. `categories`: Clasificación de comidas rápidas (Hamburguesas, Perros Calientes, Combos, Salchipapas, Acompañamientos, Bebidas, Adicionales).
  3. `customers`: Directorio comercial con Cédula/NIT, cupos empresariales y saldo deudor (`debt_balance`).
  4. `products`: Catálogo de platos comerciales, precios de venta, costos de preparación, IVA y estado activo.
  5. `ingredients`: Inventario de subproductos e ingredientes base gestionados estrictamente en gramos (`stock_g`, `min_stock_g`, `cost_per_g`).
  6. `product_recipes`: Composición de cada producto comercial con su cantidad en gramos por ingrediente (`quantity_g`).
  7. `inventory_movements`: Trazabilidad completa de entradas (compras), salidas (ventas), mermas (desperdicios) y ajustes de inventario.
  8. `sales`: Maestro de facturación con consecutivo `XL-######`, estado ('COMPLETADA', 'ANULADA'), medios de pago (Efectivo, Nequi, Daviplata, Tarjeta, Fiado), total, IVA y descuentos.
  9. `sale_items`: Detalle de renglones vendidos con cantidad en unidades, precio unitario, subtotal y descuentos.
  10. `cash_shifts`: Control de turnos y arqueos de caja (apertura, ventas en efectivo/electrónicas/crédito, retiros, efectivo esperado, contado y sobrante/faltante).
  11. `invoice_sequences`: Generador atómico de consecutivos estrictamente monótonos para prefijo `XL`.
  12. `audit_logs`: Bitácora inmutable de auditoría para operaciones críticas del sistema (anulaciones, modificaciones, etc.).

### 2.2. Ubicación de los Datos en Equipos de Producción
Para cumplir con las directivas de seguridad de Windows y evitar fallos de permisos al instalar en `C:\Program Files\`:
- **Ruta Estándar (Instalación con Instalador):**
  ```text
  %APPDATA%\XLBurguer\xlburguer.db
  (Equivalente a: C:\Users\<Usuario>\AppData\Roaming\XLBurguer\xlburguer.db)
  ```
- **Ruta Portable (Memoria USB / Carpeta Local):**
  Si existe un archivo llamado `.portable` junto al ejecutable `XLBurguer.exe`, o si se define la variable de entorno `XLBURGUER_PORTABLE=1`, la base de datos se guarda y lee directamente en la misma carpeta del ejecutable.
- **Ruta de Desarrollo:**
  En entorno de desarrollo (`git clone`), el sistema utiliza directamente el archivo `xlburguer.db` de la raíz del proyecto.

### 2.3. Inicialización Automática y Siembra de Datos
Cuando se instala la aplicación en un computador nuevo donde `%APPDATA%\XLBurguer\xlburguer.db` aún no existe:
1. El motor de conexión detecta la ausencia de la base de datos local.
2. Inicializa el esquema completo desde `schema.sql` y siembra las categorías, ingredientes en gramos, recetas y catálogo base de comidas rápidas desde `seed_data.py`.
3. Valida la integridad (`PRAGMA integrity_check`) y ejecuta cualquier migración de esquema pendiente de manera idempotente.

### 2.4. Copias de Seguridad (Backups)
El módulo [database/connection.py](file:///d:/Varios/Varios/GitHub/POS/xlBurguer/database/connection.py) cuenta con la función `backup_database()`, la cual implementa la **API de Copia de Seguridad en Línea de SQLite (`sqlite3.Connection.backup`)**:
- Se puede ejecutar con el restaurante en pleno funcionamiento sin detener las ventas ni bloquear el archivo.
- Genera un archivo con marca de tiempo: `xlburguer_backup_YYYYMMDD_HHMMSS.db`.
- En equipos instalados, los respaldos se guardan en `%APPDATA%\XLBurguer\backups\`.

---

## 3. CONTROL DE INVENTARIO Y RECETAS POR GRAMOS

### 3.1. Gestión de Ingredientes
- Todos los ingredientes de cocina se miden y almacenan en **gramos (g)**.
- El costo se calcula a nivel de gramo (`cost_per_g`).
- Las compras se pueden registrar en kilogramos o gramos; el sistema convierte automáticamente a gramos ($1\text{ kg} = 1000\text{ g}$) y actualiza el costo ponderado.

### 3.2. Recetas y Porciones Disponibles
- Cada plato preparado se asocia con uno o más ingredientes y sus gramos respectivos.
- La disponibilidad del plato se calcula dinámicamente mediante el **ingrediente limitante**:
  $$\text{Porciones Disponibles} = \min_{i} \left( \left\lfloor \frac{\text{Stock}(i)}{\text{Gramos Requeridos}(i)} \right\rfloor \right)$$
- Al vender un producto en el POS, el sistema descuenta atómicamente los gramos de cada ingrediente. Si no hay existencias suficientes de algún componente, la venta se bloquea informando el ingrediente faltante.
- Si se anula la venta, el sistema devuelve exactamente los gramos al inventario mediante un movimiento de restitución.

---

## 4. INSTALACIÓN EN OTROS COMPUTADORES

### Requisitos del Sistema:
- **Sistema Operativo:** Windows 10 o Windows 11 (64 bits).
- **Hardware Mínimo:** Procesador Intel Core i3 / AMD Ryzen 3 o superior, 4 GB de memoria RAM, 200 MB de espacio en disco.
- **Dependencias Requeridas:** **Ninguna.** El instalador incorpora el entorno de ejecución, bibliotecas, motores gráficos y SQLite.

### Procedimiento de Instalación Paso a Paso:
1. Copie el archivo `Instalador_XLBurguer_v1.0.exe` a una memoria USB o descárguelo en el computador de destino.
2. Haga doble clic sobre `Instalador_XLBurguer_v1.0.exe`.
3. Si el Control de Cuentas de Usuario (UAC) de Windows solicita confirmación, pulse **Sí**.
4. Seleccione el directorio de instalación (por defecto: `C:\Program Files\XL Burguer`).
5. Marque la casilla **Crear un acceso directo en el Escritorio** y haga clic en **Instalar**.
6. En la pantalla final, pulse **Finalizar**. La aplicación se abrirá automáticamente.

### Credenciales de Acceso Iniciales:
- **Administrador:**
  - **Usuario:** `admin`
  - **Contraseña:** `admin123`
- *Nota de Seguridad:* Se recomienda cambiar la contraseña del administrador desde el módulo de "Usuarios / Clientes" tras el primer ingreso.

---

## 5. PROCEDIMIENTO DE RECONSTRUCCIÓN DEL INSTALADOR

Para compilar nuevas versiones:

### Prerrequisitos en la máquina de desarrollo:
- Python 3.10+ con dependencias instaladas: `pip install -r requirements.txt pyinstaller`.
- Inno Setup 6 instalado (disponible mediante: `winget install JRSoftware.InnoSetup`).

### Comando Único de Compilación:
Ejecute desde la raíz del proyecto:
```powershell
python scripts/build_installer.py
```

El script ejecutará automáticamente:
1. Verificación y recolección de recursos gráficos e iconos oficiales de XL Burguer.
2. Compilación del ejecutable standalone con PyInstaller (`build_exe.py`) en modo ventana (`dist/XLBurguer/XLBurguer.exe`).
3. Compilación del instalador comercial con Inno Setup (`installer/XLBurguer.iss`).
4. Generación del instalador final en: `dist/installer/Instalador_XLBurguer_v1.0.exe`.
