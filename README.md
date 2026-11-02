# XL BURGUER
## Sistema Profesional POS, Recetas por Gramos, Control de Inventario y Facturación

Sistema de escritorio nativo, moderno y 100% offline desarrollado en **Python 3.10+** y **CustomTkinter** con arquitectura **Single-Window Frame Switcher** para la gestión comercial y operativa integral de **XL Burguer**, restaurante de comidas rápidas.

---

## 🍔 Características Principales

* **Entorno 100% Offline y Local:** Sin dependencias de internet, servidores web, Docker o bases de datos en la nube. Máxima velocidad de respuesta en caja.
* **Diseño Oscuro Gourmet:** Interfaz moderna acelerada por hardware en CustomTkinter con paleta oscura elegante (`#0F1115`), tarjetas de producto en contraste (`#161920`), acentos ámbar y dorado (`#D4A853` / `#E67E22`) y tipografía de alta legibilidad.
* **Catálogo Textual Ultraligero (Sin Imágenes de Productos):** Diseñado específicamente para atención veloz en caja. Las tarjetas de producto son textuales, limpias y organizadas por categorías temáticas, evitando sobrecarga visual o lentitud.
* **Control de Inventario en Gramos (g):**
  * Subproductos e ingredientes base (carne molida, tocineta, queso cheddar, pan brioche, vegetales, salsas) se gestionan y auditan estrictamente en **gramos (g)**.
  * Registro de compras en kilogramos con conversión matemática automática a gramos ($1\text{ kg} = 1000\text{ g}$) y recálculo dinámico del costo unitario por gramo (\$/g).
* **Administración de Recetas y Porciones Disponibles:**
  * Cada producto comercial (hamburguesa, perro caliente, combo) cuenta con su receta desagregada en gramos.
  * Cálculo dinámico de porciones disponibles según el **ingrediente limitante**: $\min(\text{stock\_g}_i / \text{cant\_requerida\_g}_i)$.
* **Descuento Atómico y Restitución de Ingredientes:**
  * Al completar una venta en el POS, el sistema descuenta automáticamente los gramos exactos de cada ingrediente asociado en la receta.
  * Si algún ingrediente no cuenta con stock suficiente, la venta se bloquea de forma preventiva indicando el faltante exacto.
  * Al anular una factura, los gramos se restituyen atómicamente al inventario con trazabilidad completa.
* **Manejo de Mermas y Ajustes Físicos:** Registro de desperdicios, mermas de cocina y ajustes por conteo físico con bitácora inmutable de movimientos.
* **Sin Báscula Física:** Operación optimizada para restaurante de comidas rápidas donde los platos preparados se venden por unidades (`UNIDAD`), eliminando dependencias de puertos seriales COM y hardware de pesaje.
* **Moneda Colombiana Estricta (COP):** Formato contable sin centavos: `COP $ #.###` (ej: `$ 24.000`).
* **Búsqueda Avanzada Normalizada:** Función SQLite personalizada `NORMALIZE_TEXT` para buscar platos como `hamburguesa` o `Hamburguesa Clásica` insensibles a tildes o mayúsculas.
* **Persistencia Transaccional ACID:** Base de datos relacional embebida `sqlite3` con llaves foráneas (`PRAGMA foreign_keys = ON`), modo WAL y transacciones protegidas con rollback.
* **Impresión de Tickets Térmicos (40 columnas):** Formateador monospaciado exacto de 40 columnas con marcos ASCII, visor pop-up interactivo y spooler directo para Windows (`win32print`). Consecutivo fiscal: `XL-000001`.
* **Exportación Profesional a Excel (`openpyxl`):** Reporte integral de inventario de productos e ingredientes con fórmulas contables y anchos de columna automatizados.

---

## 📁 Arquitectura del Proyecto

```text
xlBurguer/
├── icons/                     # Biblioteca de iconos SVG vectoriales y PNG
├── imgs/                      # Identidad visual oficial de XL Burguer (logos e icono)
├── database/                  # Capa de datos y persistencia SQLite
│   ├── __init__.py
│   ├── connection.py          # Conexión SQLite3, normalizador NFKD, migraciones y WAL
│   ├── schema.sql             # Script DDL de creación de tablas, llaves foráneas e índices
│   └── seed_data.py           # Datos iniciales (categorías de comidas rápidas, ingredientes y catálogo)
├── models/                    # Modelos de dominio y lógica de negocio
│   ├── __init__.py
│   ├── customer.py            # Modelo de clientes, identificación Cédula/NIT y cupos de crédito
│   ├── ingredient.py          # Modelo de ingredientes (g), recetas, compras kg-to-g y porciones
│   ├── product.py             # Modelo CRUD de productos preparados, bebidas y combos
│   ├── sale.py                # Modelo de ventas, items, descuento de recetas y consecutivos XL
│   ├── user.py                # Modelo de usuarios del sistema y hashing PBKDF2-SHA256
│   └── cash_shift.py          # Modelo de control de turnos y arqueos de caja
├── hardware/                  # Periféricos y controladores
│   ├── __init__.py
│   ├── barcode_scanner.py     # Buffer rápido para escáneres de código de barras HID
│   ├── scale_service.py       # Driver de compatibilidad (deprecado para comidas rápidas)
│   └── ticket_printer.py      # Generador de ticket ASCII 40 col estricto con membrete XL Burguer
├── views/                     # Componentes visuales (Single-Window Frames)
│   ├── __init__.py
│   ├── about_modal.py         # Modal institucional de identidad y diagnóstico del sistema
│   ├── calendar_modal.py      # Selector interactivo de rango de fechas
│   ├── ingredients_modal.py   # Gestión de ingredientes en gramos, compras y mermas
│   ├── recipe_modal.py        # Gestor de recetas, costos de preparación y márgenes
│   ├── inventory_frame.py     # Catálogo, CRUD de productos, recetas e ingredientes
│   ├── login_frame.py         # Panel de autenticación responsivo con branding XL Burguer
│   ├── pos_frame.py           # Punto de Venta, carrito, botones rápidos y cobro
│   ├── stats_frame.py         # Dashboard analítico, gráficas de ventas y reportes
│   ├── users_frame.py         # Directorio de clientes, historial de compras y usuarios sistema
│   └── main_window.py         # Ventana principal Single-Window y controlador de navegación
├── utils/                     # Utilidades, servicios y subsistemas de diseño
│   ├── __init__.py
│   ├── asset_manager.py       # Creador automático de gráficos, iconos y caché en memoria
│   ├── excel_exporter.py      # Generador estilizado de hojas de cálculo .xlsx ejecutivas
│   ├── navbar_animator.py     # Micro-interacciones y animaciones de navegación
│   ├── sound_manager.py       # Feedback acústico elegante y no bloqueante con winsound
│   └── theme.py               # Sistema de diseño centralizado Dark Gourmet y paletas
├── installer/                 # Definición del instalador profesional para Windows
│   └── XLBurguer.iss          # Script de Inno Setup 6 (asistente en español, UAC y accesos directos)
├── docs/                      # Documentación técnica y manuales
│   └── MANUAL_SISTEMA.md      # Manual operativo, inventario en gramos, recetas y backups
├── scripts/                   # Scripts de automatización y compilación
│   ├── build_installer.py     # Pipeline automatizado (PyInstaller + Inno Setup)
│   ├── setup_git.ps1          # Sincronización Git para Windows PowerShell
│   └── setup_git.sh           # Sincronización Git para Bash
├── tests/                     # Suites de pruebas unitarias y de integración (100% pasando)
├── main.py                    # Controlador Single-Window y ciclo de vida de la aplicación
├── requirements.txt           # Dependencias exactas del entorno
├── build_exe.py               # Compilador PyInstaller a ejecutable Windows independiente
├── Ejecutar_XLBurguer.bat     # Lanzador directo de doble clic en Windows
├── .gitignore                 # Configuración de exclusión para Git
└── README.md                  # Documentación del sistema
```

---

## 🚀 Instalación y Ejecución Local

### 1. Requisitos Previos
* Python 3.10, 3.11, 3.12 o 3.13 en Windows 10/11 (64 bits).
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
O simplemente haz doble clic en `Ejecutar_XLBurguer.bat`.

Al iniciar por primera vez, el sistema autogenera:
1. La base de datos SQLite `xlburguer.db` en `%APPDATA%\XLBurguer\` (o en la raíz en desarrollo).
2. La estructura completa de tablas, recetas, categorías de comidas rápidas y catálogo inicial.
3. El usuario administrador inicial (`admin`).

---

## 🔑 Autenticación y Seguridad

* **Usuario Administrador:** `admin` (se recomienda cambiar la contraseña en el primer inicio de sesión desde el módulo de Usuarios).
* **Seguridad Criptográfica:** Hashing con algoritmo PBKDF2-HMAC-SHA256 y 600.000 iteraciones (Estándar OWASP 2024+).
* **Protección contra Fuerza Bruta:** Bloqueo temporal automático de cuenta por 15 minutos tras 5 intentos fallidos consecutivos.
* **Control de Operadores:** Creación y asignación de cajeros desde el panel de administración.

---

## 🧾 Formato del Comprobante de Venta (40 Columnas)

El sistema genera un comprobante de venta monospaciado con marcos ASCII estandarizados y membrete oficial:

```text
+----------------------------------------+
|               XL BURGUER               |
|          NIT: 901.845.321-0            |
|       Calle 45 # 18-32, Local 2        |
|            Tel: 300 123 4567           |
+----------------------------------------+
| Comprobante No: XL-000001              |
| Fecha: 02/11/2026 11:30 AM             |
| Atendido por: Administrador            |
| Cliente: Consumidor Final              |
+----------------------------------------+
| CANT/UND   DESCRIPCION          TOTAL  |
| 2 und      Hamburguesa Clasica$ 44.000 |
| 1 und      Papas Francesa     $  7.000 |
| 2 und      Coca-Cola 400ml    $  9.000 |
+----------------------------------------+
| SUB-TOTAL:                    $ 60.000 |
| IVA INCLUIDO:                 $      0 |
| TOTAL A PAGAR:                $ 60.000 |
+----------------------------------------+
| EFECTIVO RECIBIDO:            $ 70.000 |
| CAMBIO / VUELTAS:             $ 10.000 |
+----------------------------------------+
|      ¡Gracias por elegir XL Burguer!   |
|         El sabor que te llena.         |
+----------------------------------------+
```

---

## 📦 Compilación a Ejecutable Windows (.exe)

Para compilar la aplicación en un paquete independiente que no requiera tener Python instalado:

```bash
python build_exe.py
```

El ejecutable listo para producción quedará generado en `dist/XLBurguer/XLBurguer.exe`.

Para compilar el instalador completo con Inno Setup:
```bash
python scripts/build_installer.py
```

---

## 🌐 Repositorio Oficial en GitHub

`https://github.com/JuanEstebanSilva/xlBurguer`

---

*XL Burguer — Sistema POS Profesional de Comidas Rápidas.*
