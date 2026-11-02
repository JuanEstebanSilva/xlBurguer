# CARNICERÍA SAN DIEGO - VILLA DE LEYVA (BOYACÁ)
## Sistema Profesional POS, Inventario, Hardware & Reportes en Excel

Sistema de escritorio nativo, moderno y 100% offline desarrollado en **Python 3.10+** y **CustomTkinter** con arquitectura **Single-Window Frame Switcher** para la gestión comercial integral de la **Carnicería San Diego**, ubicada en Villa de Leyva, Boyacá.

---

## 🥩 Características Principales

* **Entorno 100% Offline y Local:** Sin dependencias de internet, servidores web, Docker o bases de datos en la nube. Máxima velocidad y confiabilidad.
* **Diseño Gourmet & Artesanal:** Interfaz moderna acelerada por hardware en CustomTkinter con paleta burdeos oscuro (`#0F1115`), tarjetas artesanales (`#161920`), acentos en rojo sangre (`#C0392B`), marfil (`#F4EBD9`) y detalles dorados (`#D4A853`).
* **Moneda Estricta Colombiana:** Formato contable sin centavos: `COP $ #.###` (ej: `$ 57.000`).
* **Conversión de Pesos y Gramaje:**
  * Base de cálculo interna: **Gramos (g)**.
  * Equivalencias colombianas estándar: $1\text{ lb} = 500\text{ g}$, $1\text{ kg} = 1000\text{ g}$.
* **Búsqueda Avanzada Insensible a Acentos y Tildes:** Función SQLite personalizada `NORMALIZE_TEXT` para buscar cortes como `almojabana` o `Almojábana` sin fallos.
* **Persistencia Transaccional ACID:** Base de datos relacional embebida `sqlite3` con llaves foráneas (`PRAGMA foreign_keys = ON`), modo WAL y transacciones seguras con rollback.
* **Integración de Hardware:**
  * **Lector de Código de Barras (HID):** Detección de ráfagas rápidas de pulsaciones (<70ms entre caracteres) para escáneres USB HID.
  * **Báscula Digital Serial:** Driver RS-232 / USB COM a 9600 baudios 8N1 con reconexión interactiva en caliente y conmutación automática a modo **MOCK** para pruebas fluidas sin congelar la interfaz.
  * **Impresión Térmica de Recibos (40 columnas):** Formateador monospaciado exacto de 40 columnas con marcos ASCII, visor pop-up interactivo y spooler no bloqueante para Windows (`win32print`).
* **Atajos de Teclado de Alta Eficiencia:**
  * **F12:** Abrir modal de cobro y facturación desde cualquier pantalla del POS.
  * **F2:** Enfocar y seleccionar inmediatamente el campo de código de barras / ID.
  * **Delete:** Eliminar el último ítem del carrito rápidamente.
* **Exportación Profesional a Excel (`openpyxl`):**
  * Reporte con encabezados burdeos `#800020`, texto blanco en negrita, formato de moneda `$ #,##0`, anchos automáticos y fórmula final `=SUM(...)`.
  * Procesamiento asíncrono en subprocesos (`threading.Thread`) sin congelar la ventana principal.

---

## 📁 Arquitectura del Proyecto

```text
sanDiego/
├── icons/                     # Biblioteca de iconos SVG vectoriales y PNG de alta resolución
├── imgs/                      # Identidad visual de marca, emblemas oficiales y fondos gourmet
├── database/                  # Capa de datos y persistencia SQLite
│   ├── __init__.py
│   ├── connection.py          # Conexión SQLite3, normalizador NFKD, migraciones y WAL
│   ├── schema.sql             # Script DDL de creación de tablas, llaves foráneas e índices
│   └── seed_data.py           # Datos iniciales (cortes típicos, víveres, quesos y clientes)
├── models/                    # Modelos de dominio y lógica de negocio
│   ├── __init__.py
│   ├── customer.py            # Modelo de clientes, identificación Cédula/NIT e historial
│   ├── product.py             # Modelo CRUD de productos, conversión de pesaje y márgenes
│   ├── sale.py                # Modelo de ventas, items, transacciones ACID y KPIs
│   └── user.py                # Modelo de usuarios del sistema y hashing PBKDF2-SHA256
├── hardware/                  # Drivers y controladores de periféricos
│   ├── __init__.py
│   ├── barcode_scanner.py     # Buffer rápido para escáneres de código de barras HID
│   ├── scale_service.py       # Driver RS-232/USB con reconexión y mock automático
│   └── ticket_printer.py      # Generador de ticket ASCII 40 col estricto y previsualizador
├── views/                     # Componentes visuales (Single-Window Frames)
│   ├── __init__.py
│   ├── about_modal.py         # Modal institucional de identidad y diagnóstico del sistema
│   ├── calendar_modal.py      # Selector interactivo de rango de fechas
│   ├── inventory_frame.py     # Catálogo, CRUD, ficha técnica, ordenamiento y exportador Excel
│   ├── login_frame.py         # Panel de autenticación responsivo con fondo gourmet
│   ├── pos_frame.py           # Punto de Venta, carrito, teclado numérico táctil y cobro
│   ├── stats_frame.py         # Dashboard analítico, gráficas vectoriales y reporte Excel
│   ├── users_frame.py         # Directorio de clientes, historial de compras y usuarios sistema
│   └── main_window.py         # Contenedor de compatibilidad multi-ventana para testing
├── utils/                     # Utilidades, servicios y subsistemas de diseño
│   ├── __init__.py
│   ├── asset_manager.py       # Creador automático de gráficos, iconos y caché en memoria
│   ├── excel_exporter.py      # Generador estilizado de hojas de cálculo .xlsx ejecutivas
│   ├── navbar_animator.py     # Micro-interacciones y animaciones suaves a 60 fps
│   ├── sound_manager.py       # Feedback acústico elegante y no bloqueante con winsound
│   └── theme.py               # Sistema de diseño centralizado Dark Gourmet y paletas
├── installer/                 # Definición del instalador profesional para Windows
│   └── CarniceriaSanDiego.iss # Script de Inno Setup 6 (asistente en español, UAC y accesos directos)
├── docs/                      # Documentación técnica y manuales
│   └── MANUAL_SISTEMA.md      # Manual operativo, persistencia de datos, backups y mantenimiento
├── scripts/                   # Scripts de automatización y compilación
│   ├── build_installer.py     # Pipeline automatizado (PyInstaller + Inno Setup)
│   ├── setup_git.ps1          # Sincronización Git para Windows PowerShell
│   └── setup_git.sh           # Sincronización Git para Bash
├── tests/                     # Suites de pruebas unitarias y de integración
├── main.py                    # Controlador Single-Window y ciclo de vida de la aplicación
├── requirements.txt           # Dependencias exactas del entorno
├── build_exe.py               # Compilador PyInstaller a ejecutable Windows independiente
├── Ejecutar_Carniceria.bat    # Lanzador directo de doble clic en Windows
├── .gitignore                 # Configuración de exclusión para Git
└── README.md                  # Documentación del sistema
```

---

## 🚀 Instalación y Ejecución Local

### 1. Requisitos Previos
* Python 3.10, 3.11, 3.12 o 3.13 en Windows 10/11.
* Gestor de paquetes `pip`.

### 2. Instalación de Dependencias
Abre una terminal (PowerShell o CMD) en la raíz del proyecto y ejecuta:

```bash
pip install -r requirements.txt
```

### 3. Ejecución de la Aplicación
```bash
python main.py
```
O simplemente haz doble clic en `Ejecutar_Carniceria.bat`.

Al iniciar por primera vez, el sistema autogenera:
1. El logo y fondo en la carpeta `imgs/`.
2. La base de datos SQLite `sandiego.db` con las categorías y catálogo inicial de Boyacá.

---

## 🔑 Autenticación y Seguridad

* **Usuario Administrador:** `admin` (se recomienda cambiar la contraseña en el primer inicio de sesión desde el módulo de Usuarios).
* **Seguridad Criptográfica:** Hashing con algoritmo PBKDF2-HMAC-SHA256 y 600.000 iteraciones (Estándar OWASP 2024+). No se aceptan ni almacenan contraseñas en texto plano.
* **Protección contra Fuerza Bruta:** Bloqueo temporal automático de cuenta por 15 minutos tras 5 intentos fallidos consecutivos.
* **Control de Operadores:** Sin cuentas cajero ficticias preinstaladas. Los cajeros se crean de manera individual y segura desde el panel del Administrador.

---

## 🧾 Formato del Comprobante de Venta (40 Columnas)

El sistema genera un comprobante de venta monospaciado con marcos ASCII estandarizados, cumpliendo con la normativa de comprobantes internos no fiscales (documento no DIAN):

```text
+----------------------------------------+
|          CARNICERIA SAN DIEGO          |
|          NIT: 222222222222             |
|     Cra 10 No. 7-46, Villa de Leyva    |
|            Tel: 3136098114             |
+----------------------------------------+
| Comprobante No: CSD-000124             |
| Fecha: 14/10/2026 11:42 AM             |
| Atendido por: Diego Amador             |
| Cliente: Consumidor Final              |
+----------------------------------------+
| CANT/PESO  DESCRIPCION          TOTAL  |
| 1.50 kg    Chatas Res         $ 57.000 |
| 500 g      Ribeye Choice      $ 22.500 |
| 1 und      Cubeta Huevos x30  $ 18.000 |
| 2 und      Almojabana Boyaca  $  5.000 |
+----------------------------------------+
| SUB-TOTAL:                    $102.500 |
| IVA (19% Vinos/Licores):      $      0 |
| TOTAL A PAGAR:                $102.500 |
+----------------------------------------+
| EFECTIVO RECIBIDO:            $120.000 |
| CAMBIO / VUELTAS:             $ 17.500 |
+----------------------------------------+
|      ¡Gracias por apoyar el campo      |
|           y el comercio local!         |
+----------------------------------------+
```

---

## 📦 Compilación a Ejecutable Windows (.exe)

Para compilar la aplicación en un paquete independiente que no requiera tener Python instalado en el equipo de caja:

```bash
python build_exe.py
```

El ejecutable listo para producción quedará generado en la carpeta `dist/CarniceriaSanDiego/CarniceriaSanDiego.exe`.

---

## 🌐 Sincronización con GitHub

El repositorio remoto del proyecto está configurado en:
`https://github.com/juanSilvaE/sanDiego.git`

### Ejecutar el script automatizado
* En **PowerShell (Windows)**:
  ```powershell
  .\scripts\setup_git.ps1
  ```
* En **Bash / Git Bash**:
  ```bash
  bash scripts/setup_git.sh
  ```

---

## 🥩 Catálogo Inicial de Productos
* **Carnes de Res:** Ribeye Choice ($45/g), Chatas de Res ($38/g), Lomo Fino ($55/g), Carne para Moler ($26/g).
* **Carnes de Cerdo:** Costilla ($28/g), Chuleta ($24/g).
* **Pollo y Aves:** Pechuga Fresca ($18/g), Alas Campesinas ($14/g).
* **Pescados:** Trucha Arcoíris de Boyacá ($32/g).
* **Víveres:** Cubeta de Huevos x30 ($18.000/und), Huevo Campesino ($700/und).
* **Amasijos Típicos:** Almojábana Tradicional ($2.500/und), Arepa Boyacense ($2.000/und).
* **Quesos:** Queso Paipa Semicurado ($35/g).
* **Vinos:** Botella Vino Tinto Reserva ($65.000/und).

---
*Carnicería San Diego - Orgullo Campesino de Villa de Leyva, Boyacá.*
