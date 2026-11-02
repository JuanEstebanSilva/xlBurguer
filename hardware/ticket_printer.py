"""Thermal Ticket Printer and ASCII Receipt Generator for XL Burguer.
Formats 40-column monospace receipts adhering strictly to Colombian fiscal/commercial layout.
Includes stdout logging, optional win32print thermal output, and an interactive CustomTkinter preview modal.
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from database.connection import get_writable_path
from models.product import format_currency_short
from utils.asset_manager import get_asset_path

_LAST_PRINTED_TICKET: Optional[str] = None


def strip_accents(text: str) -> str:
    """Remove accents and tildes (á->a, é->e, í->i, ó->o, ú->u, ñ->n, etc.) for clean thermal printing."""
    if not text:
        return ""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
        '¡': '', '¿': '', '°': '', 'º': '', 'ª': ''
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def center_line(text: str, width: int = 38) -> str:
    """Center text inside a specific column width."""
    text_clean = text.strip()
    if len(text_clean) >= width:
        return text_clean[:width]
    padding = width - len(text_clean)
    left_pad = padding // 2
    right_pad = padding - left_pad
    return (" " * left_pad) + text_clean + (" " * right_pad)


def left_right_line(left: str, right: str, width: int = 36) -> str:
    """Format a line with left-aligned label and right-aligned value ensuring exact width."""
    right = right.strip()
    space_avail = width - len(right) - 1
    if space_avail < 1:
        right = right[:width - 2]
        space_avail = 1
    if len(left) > space_avail:
        left = left[:space_avail]
    res = f"{left:<{space_avail}} {right}"
    if len(res) > width:
        res = res[:width]
    elif len(res) < width:
        res = f"{res:<{width}}"
    return res


def box_line(content: str, width: int = 38) -> str:
    """Format content within vertical box boundaries '| content |' guaranteeing exact width 40."""
    if len(content) > width:
        content = content[:width]
    return f"|{content:<{width}}|"


def format_ticket(
    invoice_number: Any,
    timestamp: Optional[str] = None,
    cashier_name: Optional[str] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    subtotal: Optional[float] = None,
    total: Optional[float] = None,
    cash_received: Optional[float] = None,
    cash_change: Optional[float] = None,
    customer_name: Optional[str] = None,
    customer_document: Optional[str] = None,
    payment_method: str = "EFECTIVO"
) -> str:
    """Generate the exact 40-character wide ASCII receipt with decorative box frames without accents.
    Supports either explicit arguments or a single SaleDetail/dict object.
    """
    if hasattr(invoice_number, "invoice_number") or isinstance(invoice_number, dict):
        sale = invoice_number
        if isinstance(sale, dict):
            inv_num = sale.get("invoice_number", "SD-000000")
            ts = sale.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            c_name = sale.get("user_name") or sale.get("cashier_name") or sale.get("cashier") or "Diego Amador"
            its = sale.get("items", [])
            sub = float(sale.get("subtotal", 0.0))
            tot = float(sale.get("total", 0.0))
            rec = float(sale.get("cash_received", tot))
            chg = float(sale.get("cash_change", 0.0))
            cust_name = sale.get("customer_name")
            cust_doc = sale.get("customer_document")
            p_method = sale.get("payment_method", "EFECTIVO")
        else:
            inv_num = getattr(sale, "invoice_number", "SD-000000")
            ts = getattr(sale, "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            c_name = getattr(sale, "user_name", getattr(sale, "cashier_name", getattr(sale, "cashier", "Diego Amador")))
            its = getattr(sale, "items", [])
            sub = float(getattr(sale, "subtotal", 0.0))
            tot = float(getattr(sale, "total", 0.0))
            rec = float(getattr(sale, "cash_received", tot))
            chg = float(getattr(sale, "cash_change", 0.0))
            cust_name = getattr(sale, "customer_name", None)
            cust_doc = getattr(sale, "customer_document", None)
            p_method = getattr(sale, "payment_method", "EFECTIVO")
        return format_ticket(
            invoice_number=inv_num,
            timestamp=ts,
            cashier_name=c_name,
            items=its,
            subtotal=sub,
            total=tot,
            cash_received=rec,
            cash_change=chg,
            customer_name=cust_name,
            customer_document=cust_doc,
            payment_method=p_method
        )

    # Defaults for optional arguments when called with explicit parameters
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cashier_name = cashier_name or "Diego Amador"
    items = items or []
    subtotal = float(subtotal if subtotal is not None else 0.0)
    total = float(total if total is not None else subtotal)
    cash_received = float(cash_received if cash_received is not None else total)
    cash_change = float(cash_change if cash_change is not None else 0.0)
    border = "+" + ("-" * 38) + "+"

    # Parse and format date
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        date_str = dt.strftime("%d/%m/%Y %I:%M %p")
    except Exception:
        date_str = timestamp

    cust_display = "Consumidor Final"
    if customer_name:
        clean_name = strip_accents(customer_name)
        cust_display = clean_name
    if len(cust_display) > 28:
        cust_display = cust_display[:28]

    norm_method = strip_accents(payment_method or "EFECTIVO").upper()
    if "NEQUI" in norm_method:
        method_header = "TRANSF. NEQUI"
        method_summary = "PAGO TRANSF. NEQUI:"
    elif "DAVIPLATA" in norm_method or "DAVI PLATA" in norm_method:
        method_header = "TRANSF. DAVIPLATA"
        method_summary = "PAGO TRANSF. DAVIPLATA:"
    elif "BANCOLOMBIA" in norm_method:
        method_header = "TRANSF. BANCOLOMBIA"
        method_summary = "PAGO TRANSF. BANCOLOMBIA:"
    elif norm_method.startswith("TRANSFERENCIA"):
        method_header = "TRANSFERENCIA"
        method_summary = "PAGO TRANSFERENCIA:"
    elif norm_method == "FIADO":
        method_header = "FIADO (EMPRESA)"
        method_summary = "TOTAL FIADO A CREDITO:"
    else:
        method_header = norm_method
        method_summary = f"PAGO {norm_method}:"

    # Clean operator/cashier name for receipt
    op_name = cashier_name or "Cajero XL Burguer"
    if isinstance(op_name, str):
        cleaned_op = strip_accents(op_name.strip())
        cashier_clean = cleaned_op if cleaned_op else "Cajero XL Burguer"
    else:
        cashier_clean = "Cajero XL Burguer"

    if len(cashier_clean) > 22:
        cashier_clean = cashier_clean[:22]

    lines = [
        border,
        box_line(center_line("XL BURGUER", 38)),
        box_line(center_line("Comidas Rapidas & Hamburguesas", 38)),
        box_line(center_line("Sistema POS & Facturacion", 38)),
        border,
        box_line(f" Comprobante No: {invoice_number}", 38),
        box_line(f" Fecha: {date_str}", 38),
        box_line(f" Atendido por: {cashier_clean}", 38),
        box_line(f" Cliente: {cust_display}", 38),
    ]
    if customer_document and customer_document.strip():
        doc_lbl = "NIT" if norm_method == "FIADO" else "CC/NIT"
        lines.append(box_line(f" {doc_lbl}: {customer_document.strip()}", 38))
    lines.extend([
        box_line(f" Medio Pago: {method_header}", 38),
        border,
        box_line(" CANT/PESO  DESCRIPCION         TOTAL ", 38),
    ])

    for item in items:
        qty = item["quantity"]
        unit = item["unit_selected"]
        if unit == "kg":
            qty_str = f"{qty:.2f} kg"
        elif unit == "g":
            qty_str = f"{qty:.0f} g"
        elif unit == "lb":
            qty_str = f"{qty:.2f} lb"
        elif unit == "ml":
            bottles = int(round(qty / 750.0)) if qty >= 750 else 1
            if bottles > 1:
                qty_str = f"{bottles}x750ml"
            else:
                qty_str = f"750 ml"
        else:
            qty_str = f"{int(qty)} und"

        qty_col = f" {qty_str:<10}"

        name_str = strip_accents(item["product_name"])
        if len(name_str) > 16:
            name_str = name_str[:16]
        name_col = f"{name_str:<17}"

        tot_str = format_currency_short(item["total_price"])
        tot_col = f"{tot_str:>9} "

        row_content = f"{qty_col}{name_col}{tot_col}"
        lines.append(box_line(row_content, 38))

        # Show discount if applied
        disc_pct = float(item.get("discount_percent") or 0.0)
        disc_amt = float(item.get("discount_amount") or 0.0)
        if disc_pct > 0:
            lines.append(box_line(f"   [Desc. {int(disc_pct)}%: -{format_currency_short(disc_amt)}]", 38))

        # Show remaining product quota if it was a fiado purchase
        if item.get("fiado_remaining") is not None:
            rem_val = item["fiado_remaining"]
            rem_unit = unit
            lines.append(box_line(f"   [Le queda de cupo: {rem_val:.2f} {rem_unit}]", 38))

    tot_discount = sum(float(it.get("discount_amount") or 0.0) for it in items)
    lines.append(border)
    if tot_discount > 0:
        lines.append(box_line(" " + left_right_line("SUBTOTAL:", format_currency_short(subtotal + tot_discount), 36) + " ", 38))
        lines.append(box_line(" " + left_right_line("DESCUENTOS:", f"-{format_currency_short(tot_discount)}", 36) + " ", 38))
    else:
        lines.append(box_line(" " + left_right_line("SUB-TOTAL:", format_currency_short(subtotal), 36) + " ", 38))
    # Itemized or total IVA breakdown (B1)
    iva_total = sum(float(it.get("iva_amount") or 0.0) for it in items)
    if iva_total > 0:
        lines.append(box_line(" " + left_right_line("IVA INCLUIDO:", format_currency_short(iva_total), 36) + " ", 38))
    else:
        lines.append(box_line(" " + left_right_line("IVA (0% Alimentos):", "$      0", 36) + " ", 38))
    lines.extend([
        box_line(" " + left_right_line("TOTAL A PAGAR:", format_currency_short(total), 36) + " ", 38),
        border,
    ])

    if norm_method == "EFECTIVO":
        lines.extend([
            box_line(" " + left_right_line("EFECTIVO RECIBIDO:", format_currency_short(cash_received), 36) + " ", 38),
            box_line(" " + left_right_line("CAMBIO:", format_currency_short(cash_change), 36) + " ", 38),
        ])
    elif norm_method == "FIADO":
        lines.extend([
            box_line(" " + left_right_line("TOTAL FIADO A CREDITO:", format_currency_short(total), 36) + " ", 38),
            box_line(" " + left_right_line("ESTADO PAGO:", "PENDIENTE / FIADO", 36) + " ", 38),
        ])
    else:
        lines.extend([
            box_line(" " + left_right_line(method_summary, format_currency_short(total), 36) + " ", 38),
            box_line(" " + left_right_line("ESTADO PAGO:", "APROBADO", 36) + " ", 38),
        ])

    lines.extend([
        border,
        box_line(center_line("GRACIAS POR SU COMPRA!", 38)),
        box_line(center_line("XL BURGUER - Calidad & Sabor", 38)),
        border,
    ])

    return strip_accents("\n".join(lines))


def render_ticket_image(
    ticket_text: str,
    use_dashed_borders: bool = True
) -> Image.Image:
    """Render a pixel-perfect, high-DPI graphical thermal receipt matching Carnicería San Diego branding.
    Parses 40-col ASCII ticket text and overlays official brand assets:
      - Isotipo Negro (imgs/isotipoNegro.png) in the header
      - Elegant italic typography for the Diego Amador quote
      - Visitanos QR (imgs/qr.png) and Logotipo Negro (imgs/logotipo-negro-2000.png) in the footer
    """
    def _load_asset(filename: str) -> Optional[Image.Image]:
        try:
            path = get_asset_path(filename)
            if path and os.path.exists(path):
                return Image.open(path).convert("RGBA")
        except Exception:
            pass
        return None

    iso_img = _load_asset("XL_Burguer_logo.png") or _load_asset("logoHorizontal.png")
    qr_img = None
    logo_img = None

    S = 2  # 2x Retina scale for crispness
    bg_color = (255, 255, 255, 255)
    text_color = (24, 24, 27, 255)

    def _get_font(name: str, size: float, fallback: str = "consola.ttf") -> ImageFont.ImageFont:
        for p in [os.path.join("C:/Windows/Fonts", name), os.path.join("C:/Windows/Fonts", fallback)]:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, int(size * S))
                except Exception:
                    pass
        return ImageFont.load_default()

    font_mono = _get_font("consola.ttf", 9.5)
    font_italic = _get_font("georgiai.ttf", 9.5, "consola.ttf")

    char_w = font_mono.getbbox("XX")[2] - font_mono.getbbox("X")[2]
    line_h = int(14.5 * S)

    pad_x = int(12 * S)
    width = (char_w * 40) + (pad_x * 2)

    border_line = "+" + (" -" * 19) + "+" if use_dashed_borders else "+" + ("-" * 38) + "+"

    sections: List[List[str]] = []
    current_sec: List[str] = []
    for line in ticket_text.splitlines():
        if line.startswith("+"):
            if current_sec:
                sections.append(current_sec)
                current_sec = []
        else:
            current_sec.append(line)
    if current_sec:
        sections.append(current_sec)

    total_text_lines = sum(len(s) for s in sections)
    total_borders = len(sections) + 1
    footer_img_h = int(60 * S)
    estimated_h = (total_text_lines + total_borders) * line_h + footer_img_h + int(24 * S)

    im = Image.new("RGBA", (width, estimated_h), bg_color)
    draw = ImageDraw.Draw(im)

    curr_y = int(8 * S)

    def _draw_border(y: int) -> int:
        draw.text((pad_x, y), border_line, font=font_mono, fill=text_color)
        return y + line_h

    def _draw_row(line_str: str) -> None:
        if not (line_str.startswith("|") and line_str.endswith("|")):
            content = line_str.strip("|")
            line_str = f"|{content:<38}|"
        draw.text((pad_x, curr_y), line_str, font=font_mono, fill=text_color)

    curr_y = _draw_border(curr_y)

    for sec_idx, sec in enumerate(sections):
        if sec_idx == 0:
            hdr_start_y = curr_y
            for line in sec:
                _draw_row(line)
                curr_y += line_h

            if iso_img:
                iso_h = int(28 * S)
                iso_w = int(iso_img.width * (iso_h / iso_img.height))
                iso_resized = iso_img.resize((iso_w, iso_h), Image.Resampling.LANCZOS)
                iso_x = pad_x + (char_w * 39) - iso_w - int(2 * S)
                iso_y = hdr_start_y + int(1 * S)
                im.paste(iso_resized, (iso_x, iso_y), iso_resized)

        elif any("No solo vendemos" in l for l in sec):
            for line in sec:
                clean_txt = line.strip("|").strip()
                draw.text((pad_x, curr_y), "|", font=font_mono, fill=text_color)
                draw.text((pad_x + (char_w * 39), curr_y), "|", font=font_mono, fill=text_color)
                draw.text((pad_x + int(10 * S), curr_y), f"  {clean_txt}", font=font_italic, fill=text_color)
                curr_y += line_h

        elif sec_idx == len(sections) - 1 or any("visitanos" in l.lower() for l in sec):
            _draw_row(f"|{'Visitanos':^38}|")
            curr_y += line_h

            footer_y = curr_y + int(3 * S)
            if qr_img:
                qr_size = int(54 * S)
                qr_resized = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
                qr_x = pad_x + int(14 * S)
                im.paste(qr_resized, (qr_x, footer_y))

            if logo_img:
                logo_w = int(120 * S)
                logo_h = int(logo_img.height * (logo_w / logo_img.width))
                logo_resized = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
                logo_x = pad_x + (char_w * 39) - logo_w - int(6 * S)
                logo_y = footer_y + int(10 * S)
                im.paste(logo_resized, (logo_x, logo_y), logo_resized)

            for y_bar in range(curr_y, curr_y + footer_img_h, line_h):
                draw.text((pad_x, y_bar), "|", font=font_mono, fill=text_color)
                draw.text((pad_x + (char_w * 39), y_bar), "|", font=font_mono, fill=text_color)

            curr_y += footer_img_h + int(2 * S)

        else:
            for line in sec:
                _draw_row(line)
                curr_y += line_h

        curr_y = _draw_border(curr_y)

    final_im = im.crop((0, 0, width, curr_y + int(6 * S)))
    return final_im


CONFIG_PRINTER_FILE = "printer_settings.json"


def get_saved_printer() -> Optional[str]:
    """Retrieve saved printer preference from local config if present."""
    try:
        cfg_path = get_writable_path(CONFIG_PRINTER_FILE)
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("printer_name")
    except Exception as e:
        logging.debug("Error reading %s: %s", CONFIG_PRINTER_FILE, e)
    return None


def save_printer_preference(printer_name: str) -> None:
    """Save chosen printer preference to local config file."""
    try:
        cfg_path = get_writable_path(CONFIG_PRINTER_FILE)
        data = {"printer_name": printer_name}
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info("Preferencia de impresora guardada: '%s'", printer_name)
    except Exception as e:
        logging.warning("Error saving printer preference: %s", e)


def is_thermal_or_text_printer(printer_name: str) -> bool:
    """Return True if the printer is a thermal/receipt or Generic / Text Only printer."""
    if not printer_name:
        return False
    lower = printer_name.lower().strip()
    thermal_indicators = [
        "generic", "text only", "pos", "thermal", "ticket", "recibo",
        "receipt", "tm-t", "rp-", "xp-", "zijiang", "epson tm", "star", "bixolon", "58", "80"
    ]
    return any(ind in lower for ind in thermal_indicators)


def list_available_printers() -> List[str]:
    """Enumerate all available physical printers in Windows, prioritizing Generic / Text Only and thermal printers."""
    if not sys.platform.startswith("win"):
        return []

    virtual_printers = {"microsoft print to pdf", "onenote", "fax", "xps", "pdf", "writer"}
    physical_printers: List[str] = []
    try:
        import win32print  # noqa: PLC0415
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for p in printers:
            name = p[2]
            if name and not any(v in name.lower() for v in virtual_printers):
                if name not in physical_printers:
                    physical_printers.append(name)
    except Exception as e:
        logging.debug("Error enumerating printers: %s", e)

    def sort_key(name: str) -> int:
        nl = name.lower()
        if "generic / text only" in nl or nl == "generic":
            return 0
        if "generic" in nl or "text only" in nl:
            return 1
        if any(t in nl for t in ("pos", "thermal", "ticket", "recibo", "receipt", "tm-t", "rp-", "xp-")):
            return 2
        return 3

    physical_printers.sort(key=sort_key)
    return physical_printers


def get_target_printer(preferred_printer: Optional[str] = None) -> Optional[str]:
    """Find the optimal physical printer available in Windows.
    Strictly prioritizes 'Generic / Text Only' and thermal POS printers over desktop inkjet/laser printers.
    """
    if not sys.platform.startswith("win"):
        return None

    import win32print  # noqa: PLC0415
    available = list_available_printers()
    if not available:
        return None

    # 1. If explicit preferred printer given and exists, return it
    if preferred_printer:
        for p in available:
            if p.lower() == preferred_printer.lower():
                return p

    # 2. If user saved a preference in settings and exists, return it
    saved = get_saved_printer()
    if saved:
        for p in available:
            if p.lower() == saved.lower():
                return p

    # 3. Priority: "Generic / Text Only" (The user's receipt printer!)
    for p in available:
        if "generic / text only" in p.lower() or p.strip().lower() == "generic":
            try:
                win32print.SetDefaultPrinter(p)
            except Exception:
                pass
            return p

    # 4. Priority: Any generic or POS / thermal printer
    for p in available:
        nl = p.lower()
        if "generic" in nl or "text only" in nl or any(t in nl for t in ("pos", "thermal", "ticket", "recibo", "receipt", "tm-t", "rp-", "xp-")):
            try:
                win32print.SetDefaultPrinter(p)
            except Exception:
                pass
            return p

    # 5. Default physical printer if valid
    try:
        default_name = win32print.GetDefaultPrinter() or ""
        for p in available:
            if p.lower() == default_name.lower():
                return p
    except Exception:
        pass

    # 6. Fallback to first available physical printer
    first_choice = available[0]
    try:
        win32print.SetDefaultPrinter(first_choice)
    except Exception:
        pass
    return first_choice


def _print_raw_ticket(printer_name: str, ticket_clean: str, open_drawer: bool = False) -> Tuple[bool, str]:
    """Send raw ASCII/ESC-POS bytes directly to the printer spooler without graphics rasterization.
    Native mode for 'Generic / Text Only' and POS-80/POS-58 thermal printers.
    """
    import win32print  # noqa: PLC0415
    h_printer = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(h_printer, 1, ("Factura San Diego", None, "RAW"))
        win32print.StartPagePrinter(h_printer)

        # ESC/POS sequence:
        # \x1b@   : Initialize printer
        # \x1bt\x00: Standard character code table (PC437 USA)
        # \x1ba\x00: Left alignment
        # \x1b2   : Default 1/6-inch line spacing
        # \x1b!\x00: Font A (standard size, perfect for 40-col layout on POS-80)
        esc_init = b"\x1b@\x1bt\x00\x1ba\x00\x1b2\x1b!\x00"

        # Optional cash drawer kick (pin 2 pulse)
        drawer_cmd = b"\x1bp\x00\x19\xfa" if open_drawer else b""

        # Ticket text normalized to CRLF
        content_bytes = ticket_clean.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii", "replace")

        # Feed paper past tear bar (4 blank lines) & auto-cut (GS V 1 - partial cut)
        esc_cut = b"\r\n\r\n\r\n\r\n\x1dV\x01"

        payload = esc_init + drawer_cmd + content_bytes + esc_cut

        win32print.WritePrinter(h_printer, payload)
        win32print.EndPagePrinter(h_printer)
        win32print.EndDocPrinter(h_printer)

        logging.info("Ticket impreso exitosamente en modo RAW en '%s'.", printer_name)
        return True, f"Factura enviada exitosamente a la impresora:\n'{printer_name}'"
    finally:
        win32print.ClosePrinter(h_printer)


def _print_gdi_ticket(printer_name: str, ticket_text: str) -> Tuple[bool, str]:
    """Print the receipt directly via Windows GDI, compacting width to ~65mm (smartphone width).
    Does NOT create or save any file on the computer. Sends straight to the printer spooler.
    """
    import win32ui  # noqa: PLC0415
    import win32con  # noqa: PLC0415

    dc = win32ui.CreateDC()
    dc.CreatePrinterDC(printer_name)

    dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
    dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)
    horz_res = dc.GetDeviceCaps(win32con.HORZRES)

    printable_w_mm = (horz_res / dpi_x) * 25.4

    # Target width: 66 mm (~2.6 inches, width of a smartphone)
    target_w_mm = min(66.0, max(42.0, printable_w_mm - 8.0))

    # Calculate optimal font height for 40 monospace columns (Consolas)
    font_h = max(10, int(round((target_w_mm / 25.4 * dpi_y) / (40 * 0.55))))
    font = win32ui.CreateFont({
        'name': 'Consolas',
        'height': font_h,
        'weight': 400,
    })
    dc.SelectObject(font)

    sample_line = "+--------------------------------------+"
    w, h = dc.GetTextExtent(sample_line)
    actual_mm = (w / dpi_x) * 25.4

    # Calibrate font height to match target_w_mm closely
    if actual_mm > 0:
        ratio = target_w_mm / actual_mm
        font_h = max(8, int(round(font_h * ratio)))
        font = win32ui.CreateFont({
            'name': 'Consolas',
            'height': font_h,
            'weight': 400,
        })
        dc.SelectObject(font)
        w, h = dc.GetTextExtent(sample_line)

    # Margins:
    # If standard sheet paper (Letter / A4): print in top-left with a clean 16mm left / 12mm top margin
    # If narrow thermal roll (<=80mm): center on roll with 2mm top margin
    if printable_w_mm <= 80.0:
        margin_x = max(0, int((horz_res - w) / 2))
        margin_y = int((2.0 / 25.4) * dpi_y)
    else:
        margin_x = int((16.0 / 25.4) * dpi_x)
        margin_y = int((12.0 / 25.4) * dpi_y)

    # Try printing high-resolution graphic bitmap with logo/QR first
    try:
        from PIL import ImageWin  # noqa: PLC0415
        t_img = render_ticket_image(ticket_text)
        target_px_w = int((target_w_mm / 25.4) * dpi_x)
        target_px_h = int(t_img.height * (target_px_w / t_img.width))

        dc.StartDoc("Factura San Diego")
        dc.StartPage()

        dib = ImageWin.Dib(t_img.convert("RGB"))
        dib.draw(dc.GetHandleOutput(), (margin_x, margin_y, margin_x + target_px_w, margin_y + target_px_h))

        dc.EndPage()
        dc.EndDoc()

        return True, f"Factura enviada exitosamente a la impresora:\n'{printer_name}'"
    except Exception as gdi_img_err:
        logging.warning("Impresion grafica GDI no disponible (%s), recurriendo a texto GDI...", gdi_img_err)

    line_spacing = int(round(h * 1.05))

    dc.StartDoc("Factura San Diego")
    dc.StartPage()

    curr_y = margin_y
    for line in ticket_text.splitlines():
        dc.TextOut(margin_x, curr_y, line)
        curr_y += line_spacing

    dc.EndPage()
    dc.EndDoc()

    return True, f"Factura enviada exitosamente a la impresora:\n'{printer_name}'"


def print_ticket_raw(
    ticket_text: str,
    printer_name: Optional[str] = None,
    open_drawer: bool = False
) -> Tuple[bool, str]:
    """Print ticket text directly to the printer spooler without opening any PDF or save file dialogs.
    If 'Generic / Text Only' or POS thermal printer is used, uses instant native RAW ESC/POS.
    If an office sheet printer (Epson L355, HP, etc.) is used, uses GDI formatted mode.
    """
    ticket_clean = strip_accents(ticket_text)

    # 1. Output to console and log (always safe)
    try:
        print("\n" + "=" * 42)
        print(ticket_clean)
        print("=" * 42 + "\n")
    except Exception:
        pass
    logging.info("Ticket registrado en log/consola.")

    if not sys.platform.startswith("win"):
        return (True, "Ticket registrado en consola y log (entorno no Windows).")

    result = [True, "Ticket registrado en consola."]

    def _spool_worker():
        try:
            target = printer_name or get_target_printer()
            if not target:
                logging.warning("No se encontro ninguna impresora fisica conectada.")
                result[0] = False
                result[1] = (
                    "No se encontro ninguna impresora fisica conectada.\n\n"
                    "(Se omitieron impresoras virtuales como 'Microsoft Print to PDF'\n"
                    "para no solicitar guardar archivos en el equipo)."
                )
                return

            # Determine whether printer is thermal / Generic Text Only
            if is_thermal_or_text_printer(target):
                # 1st attempt: Native RAW ESC/POS (instant, clean, auto-cut)
                try:
                    ok, msg = _print_raw_ticket(target, ticket_clean, open_drawer=open_drawer)
                    result[0] = ok
                    result[1] = msg
                    return
                except Exception as raw_err:
                    logging.warning("Impresion RAW fallo (%s), recurriendo a modo GDI...", raw_err)
                    try:
                        ok, msg = _print_gdi_ticket(target, ticket_clean)
                        result[0] = ok
                        result[1] = msg
                        return
                    except Exception as gdi_err:
                        raise gdi_err
            else:
                # Office sheet printer (Epson L355, HP, etc.): GDI mode first
                try:
                    ok, msg = _print_gdi_ticket(target, ticket_clean)
                    result[0] = ok
                    result[1] = msg
                    return
                except Exception as gdi_err:
                    logging.warning("Impresion GDI fallo (%s), recurriendo a modo RAW...", gdi_err)
                    try:
                        ok, msg = _print_raw_ticket(target, ticket_clean, open_drawer=open_drawer)
                        result[0] = ok
                        result[1] = msg
                        return
                    except Exception as raw_err:
                        raise raw_err

        except Exception as e:
            logging.warning("Error al enviar a impresora fisica: %s", e)
            result[0] = False
            result[1] = f"Error al enviar a la impresora:\n{e}"

    spool_thread = threading.Thread(target=_spool_worker, daemon=True)
    spool_thread.start()
    spool_thread.join(timeout=5.0)

    # Cache the printed ticket text in memory and on disk for reprinting (C3)
    global _LAST_PRINTED_TICKET
    _LAST_PRINTED_TICKET = ticket_clean
    try:
        cache_path = os.path.join(get_writable_path(), "last_ticket.txt")
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(ticket_clean)
    except Exception:
        pass

    return (result[0], result[1])


def get_last_ticket_text() -> Optional[str]:
    """Retrieve the text of the most recently generated or printed ticket."""
    global _LAST_PRINTED_TICKET
    if _LAST_PRINTED_TICKET:
        return _LAST_PRINTED_TICKET
    try:
        cache_path = os.path.join(get_writable_path(), "last_ticket.txt")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return None


def reprint_last_ticket(
    printer_name: Optional[str] = None,
    open_drawer: bool = False
) -> Tuple[bool, str]:
    """Reprint the last printed ticket from disk/memory cache (C3)."""
    last_text = get_last_ticket_text()
    if not last_text:
        return (False, "No hay ningún ticket reciente disponible para reimprimir.")
    return print_ticket_raw(last_text, printer_name=printer_name, open_drawer=open_drawer)


def __getattr__(name: str) -> Any:
    """Lazy module proxy: if UI requests TicketPreviewModal, load it from views."""
    if name == "TicketPreviewModal":
        from views.ticket_preview_modal import TicketPreviewModal
        return TicketPreviewModal
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

