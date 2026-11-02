-- Schema DDL para Carnicería San Diego (Villa de Leyva)
-- Versión del esquema: 3 (Transaccional, Multi-Turno, IVA, Consecutivos Inalterables y Auditoría)
PRAGMA foreign_keys = ON;

-- Tabla de Usuarios y Autenticación
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'CAJERO' CHECK (role IN ('ADMIN', 'CAJERO')),
    document_id TEXT,
    phone TEXT,
    email TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until DATETIME DEFAULT NULL
);

-- Tabla de Categorías de Productos
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- Tabla de Clientes y Empresas (Identificación, Registro en Caja y Cartera)
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT,
    customer_type TEXT NOT NULL DEFAULT 'PERSONA' CHECK (customer_type IN ('PERSONA', 'EMPRESA')),
    discount_percent REAL NOT NULL DEFAULT 0,
    debt_balance REAL NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Convenios y Cupos de Fiados por Producto para Empresas
CREATE TABLE IF NOT EXISTS company_product_quotas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quota_quantity REAL NOT NULL DEFAULT 0,
    unit TEXT NOT NULL DEFAULT 'kg',
    consumed_quantity REAL NOT NULL DEFAULT 0,
    remaining_quantity REAL NOT NULL DEFAULT 0,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
    UNIQUE (customer_id, product_id)
);

-- Tabla de Productos e Inventario
-- Si sale_type = 'PESO': price_base es precio por gramo ($/g), stock en gramos (g)
-- Si sale_type = 'UNIDAD': price_base es precio por unidad ($/und), stock en unidades
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    sale_type TEXT CHECK (sale_type IN ('PESO', 'UNIDAD')) NOT NULL,
    price_base REAL NOT NULL,
    cost REAL NOT NULL DEFAULT 0,
    iva REAL NOT NULL DEFAULT 0,
    unit_measure TEXT NOT NULL DEFAULT 'kg',
    stock REAL NOT NULL DEFAULT 0,
    min_stock REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE RESTRICT
);

-- Tabla de Facturas / Ventas
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    subtotal REAL NOT NULL,
    total REAL NOT NULL,
    cash_received REAL NOT NULL,
    cash_change REAL NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'EFECTIVO',
    customer_id INTEGER,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'COMPLETADA' CHECK (status IN ('COMPLETADA', 'ANULADA')),
    iva_total REAL NOT NULL DEFAULT 0,
    voided_at DATETIME DEFAULT NULL,
    voided_by INTEGER DEFAULT NULL,
    void_reason TEXT DEFAULT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY (voided_by) REFERENCES users (id) ON DELETE RESTRICT
);

-- Tabla de Detalle de Venta
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    unit_selected TEXT NOT NULL CHECK (unit_selected IN ('g', 'kg', 'lb', 'und', 'ml', 'l')),
    unit_price REAL NOT NULL,
    total_price REAL NOT NULL,
    fiado_remaining REAL,
    discount_percent REAL NOT NULL DEFAULT 0,
    discount_amount REAL NOT NULL DEFAULT 0,
    iva_rate REAL NOT NULL DEFAULT 0,
    iva_amount REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (sale_id) REFERENCES sales (id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE RESTRICT
);

-- Tabla de Consecutivos Fiscales Inalterables
CREATE TABLE IF NOT EXISTS invoice_sequences (
    prefix TEXT PRIMARY KEY,
    last_number INTEGER NOT NULL DEFAULT 0
);

-- Tabla de Arqueos y Cierres de Turno de Caja
CREATE TABLE IF NOT EXISTS cash_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME DEFAULT NULL,
    initial_cash REAL NOT NULL DEFAULT 0,
    cash_sales REAL NOT NULL DEFAULT 0,
    electronic_sales REAL NOT NULL DEFAULT 0,
    credit_sales REAL NOT NULL DEFAULT 0,
    cash_withdrawals REAL NOT NULL DEFAULT 0,
    expected_cash REAL NOT NULL DEFAULT 0,
    actual_cash REAL DEFAULT NULL,
    difference REAL DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'ABIERTA' CHECK (status IN ('ABIERTA', 'CERRADA')),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT
);

-- Tabla de Bitácora y Auditoría de Acciones Críticas
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    table_name TEXT,
    record_id INTEGER,
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Índices de Rendimiento
CREATE INDEX IF NOT EXISTS idx_customers_document ON customers (document_id);
CREATE INDEX IF NOT EXISTS idx_customers_type ON customers (customer_type);
CREATE INDEX IF NOT EXISTS idx_company_quotas_customer ON company_product_quotas (customer_id);
CREATE INDEX IF NOT EXISTS idx_company_quotas_product ON company_product_quotas (product_id);
CREATE INDEX IF NOT EXISTS idx_products_barcode ON products (barcode);
CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_sales_timestamp ON sales (timestamp);
CREATE INDEX IF NOT EXISTS idx_sales_invoice ON sales (invoice_number);
CREATE INDEX IF NOT EXISTS idx_sales_status ON sales (status);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale_id ON sale_items (sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_product_id ON sale_items (product_id);
CREATE INDEX IF NOT EXISTS idx_cash_shifts_user ON cash_shifts (user_id);
CREATE INDEX IF NOT EXISTS idx_cash_shifts_status ON cash_shifts (status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);
