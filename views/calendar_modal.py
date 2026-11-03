"""Calendar Date Picker Modal for XL Burguer POS & Analytics.
Provides a luxury, dark-themed interactive calendar picker:
- Standardized modal topbar (XL Burguer logo + HunzaIA emblem, no close X button)
- Centered executive title banner with calendar icon in brand golden-ochre (#C5A059)
- Month / Year navigation with customized vector icons:
    * Left side: [ Año Ant (⏪) ] [ Mes Ant (◀) ]
    * Center: Month & Year display
    * Right side: [ Mes Sig (▶) ] [ Año Sig (⏩) ]
- High-contrast interactive hover states on day cells for clear selection affordance
- Instant visual click feedback (day highlights before confirming)
- Quick action buttons: "Hoy", "Sin fecha", "Cerrar" with Tab navigation support
- Returns selected date in standard ISO format (YYYY-MM-DD) or empty string when cleared
"""

import os
import io
import calendar
from datetime import datetime, timedelta
from typing import Callable, Optional, Tuple, Dict, List, Any
from PIL import Image, ImageColor
import customtkinter as ctk

from utils.asset_manager import (
    center_modal,
    build_standard_modal_header,
    get_ctk_icon,
    get_tinted_ctk_icon,
    get_asset_path
)
from utils.sound_manager import sound_manager
from utils.theme import DarkTheme


SPANISH_MONTHS = [
    "",
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

SPANISH_WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _get_nav_icon(
    icon_name: str,
    flip: bool = False,
    color_hex: str = "#CBD5E1",
    size: Tuple[int, int] = (12, 12)
) -> Optional[ctk.CTkImage]:
    """Load an icon from icons/ or imgs/, tint it to color_hex, and optionally flip horizontally."""
    try:
        path = get_asset_path(icon_name if "." in icon_name else f"{icon_name}.svg")
        if not os.path.exists(path):
            path = get_asset_path(icon_name if "." in icon_name else f"{icon_name}.png")
        if not os.path.exists(path):
            return None

        if path.lower().endswith(".svg"):
            import resvg_py
            with open(path, "r", encoding="utf-8") as f:
                svg_data = f.read()
            png_bytes = resvg_py.svg_to_bytes(svg_data)
            raw_pil = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        else:
            raw_pil = Image.open(path).convert("RGBA")

        alpha = raw_pil.split()[-1]
        rgb = ImageColor.getrgb(color_hex)[:3]
        tinted = Image.new("RGBA", raw_pil.size, (*rgb, 255))
        tinted.putalpha(alpha)

        if flip:
            tinted = tinted.transpose(Image.FLIP_LEFT_RIGHT)

        return ctk.CTkImage(light_image=tinted, dark_image=tinted, size=size)
    except Exception:
        return None


class CalendarPickerModal(ctk.CTkToplevel):
    """Luxury modal window for interactive date selection. Supports 'day', 'week', and 'month' modes."""

    def __init__(
        self,
        parent,
        title: str = "Seleccionar Fecha",
        initial_date: Optional[str] = None,
        on_select: Optional[Callable[..., None]] = None,
        mode: str = "day"
    ):
        super().__init__(parent)
        self.parent = parent
        self.on_select = on_select
        self.mode = mode.lower().strip() if mode else "day"

        # Parse initial date or default to current date
        now = datetime.now()
        self.today_year = now.year
        self.today_month = now.month
        self.today_day = now.day

        self.selected_year: Optional[int] = None
        self.selected_month: Optional[int] = None
        self.selected_day: Optional[int] = None

        if initial_date and isinstance(initial_date, str) and len(initial_date.strip()) >= 8:
            try:
                dt = datetime.strptime(initial_date.strip()[:10], "%Y-%m-%d")
                self.current_year = dt.year
                self.current_month = dt.month
                self.selected_year = dt.year
                self.selected_month = dt.month
                self.selected_day = dt.day
            except Exception:
                self.current_year = self.today_year
                self.current_month = self.today_month
        else:
            self.current_year = self.today_year
            self.current_month = self.today_month

        # Window settings
        self.title(title)
        self.configure(fg_color=DarkTheme.BG_MODAL)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # Center over screen
        center_modal(self, 360, 485 if self.mode != "day" else 465, parent)

        # Build UI
        self._build_header(title)
        self._build_month_nav()
        self._build_calendar_grid()
        self._build_footer()

        # Keyboard shortcuts
        self.bind("<Escape>", lambda e: self.destroy())

        # Grab modality
        self.transient(parent)
        self.after(50, self._safe_grab)

    def _safe_grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _build_header(self, title: str) -> None:
        """Standardized modal header with XL Burguer logo, HunzaIA emblem, and centered title."""
        cal_ico = get_tinted_ctk_icon("calendar_regular_white", "#C5A059", size=(16, 16)) or get_ctk_icon("calendar_regular_white", size=(16, 16))
        build_standard_modal_header(
            parent_modal=self,
            title_text=title,
            title_icon=cal_ico,
            on_close_cmd=self.destroy,
            show_close_btn=False,
            text_color="#C5A059",
            height=44
        )

        if self.mode == "week":
            sub_title = "Seleccione un día para marcar toda la semana (Lun - Dom)"
        elif self.mode == "month":
            sub_title = "Seleccione cualquier fecha para confirmar el mes completo"
        else:
            sub_title = None

        if sub_title:
            inst_box = ctk.CTkFrame(self, fg_color="#0A1628", border_color="#1E3A8A", border_width=1, corner_radius=6)
            inst_box.pack(fill="x", padx=16, pady=(4, 0))
            ctk.CTkLabel(
                inst_box,
                text=sub_title,
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color="#93C5FD"
            ).pack(padx=8, pady=3)

    def _build_month_nav(self) -> None:
        """Navigation bar with year/month jump controls:
        - Left: [ Año Ant (⏪) ] [ Mes Ant (◀) ]
        - Center: Month & Year Label
        - Right: [ Mes Sig (▶) ] [ Año Sig (⏩) ]
        """
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(fill="x", padx=16, pady=(10, 6))

        # Vector icons for navigation
        prev_yr_ico = _get_nav_icon("forward-solid-full.svg", flip=True, color_hex="#CBD5E1", size=(12, 12))
        prev_mo_ico = _get_nav_icon("play-solid-full.svg", flip=True, color_hex="#CBD5E1", size=(11, 11))
        next_mo_ico = _get_nav_icon("play-solid-full.svg", flip=False, color_hex="#CBD5E1", size=(11, 11))
        next_yr_ico = _get_nav_icon("forward-solid-full.svg", flip=False, color_hex="#CBD5E1", size=(12, 12))

        # ── LEFT SECTION: [ Año Ant ] [ Mes Ant ] ──
        left_box = ctk.CTkFrame(nav_frame, fg_color="transparent")
        left_box.pack(side="left")

        # Año Anterior (Extremo izquierdo)
        prev_yr_btn = ctk.CTkButton(
            left_box,
            image=prev_yr_ico,
            text="" if prev_yr_ico else "«",
            width=32,
            height=30,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#334155",
            border_width=1,
            corner_radius=6,
            cursor="hand2",
            command=self._prev_year
        )
        prev_yr_btn.pack(side="left", padx=(0, 4))
        self._bind_nav_btn_hover(prev_yr_btn)

        # Mes Anterior (Interno izquierdo)
        prev_mo_btn = ctk.CTkButton(
            left_box,
            image=prev_mo_ico,
            text="" if prev_mo_ico else "◀",
            width=32,
            height=30,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#334155",
            border_width=1,
            corner_radius=6,
            cursor="hand2",
            command=self._prev_month
        )
        prev_mo_btn.pack(side="left")
        self._bind_nav_btn_hover(prev_mo_btn)

        # ── RIGHT SECTION: [ Mes Sig ] [ Año Sig ] ──
        right_box = ctk.CTkFrame(nav_frame, fg_color="transparent")
        right_box.pack(side="right")

        # Mes Siguiente (Interno derecho)
        next_mo_btn = ctk.CTkButton(
            right_box,
            image=next_mo_ico,
            text="" if next_mo_ico else "▶",
            width=32,
            height=30,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#334155",
            border_width=1,
            corner_radius=6,
            cursor="hand2",
            command=self._next_month
        )
        next_mo_btn.pack(side="left", padx=(0, 4))
        self._bind_nav_btn_hover(next_mo_btn)

        # Año Siguiente (Extremo derecho)
        next_yr_btn = ctk.CTkButton(
            right_box,
            image=next_yr_ico,
            text="" if next_yr_ico else "»",
            width=32,
            height=30,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#334155",
            border_width=1,
            corner_radius=6,
            cursor="hand2",
            command=self._next_year
        )
        next_yr_btn.pack(side="left")
        self._bind_nav_btn_hover(next_yr_btn)

        # ── CENTER SECTION: Month and Year label ──
        self.month_lbl = ctk.CTkLabel(
            nav_frame,
            text=f"{SPANISH_MONTHS[self.current_month]} {self.current_year}",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#F8FAFC"
        )
        self.month_lbl.pack(side="left", fill="x", expand=True)

    def _bind_nav_btn_hover(self, btn: ctk.CTkButton) -> None:
        """Add subtle electric sky border illumination on navigation button hover."""
        def on_enter(e):
            btn.configure(border_color="#38BDF8")
        def on_leave(e):
            btn.configure(border_color="#334155")
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    def _build_calendar_grid(self) -> None:
        self.grid_container = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_container.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        # Weekday headers
        weekday_frame = ctk.CTkFrame(self.grid_container, fg_color="transparent")
        weekday_frame.pack(fill="x", pady=(0, 4))
        for col, w_name in enumerate(SPANISH_WEEKDAYS):
            weekday_frame.grid_columnconfigure(col, weight=1)
            lbl = ctk.CTkLabel(
                weekday_frame,
                text=w_name,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#94A3B8"
            )
            lbl.grid(row=0, column=col, sticky="ew")

        # Days container
        self.days_frame = ctk.CTkFrame(self.grid_container, fg_color="transparent")
        self.days_frame.pack(fill="both", expand=True)
        for col in range(7):
            self.days_frame.grid_columnconfigure(col, weight=1)

        self._render_days()

    def _render_days(self) -> None:
        for w in self.days_frame.winfo_children():
            w.destroy()

        self.week_rows: Dict[int, List[Tuple[int, ctk.CTkButton]]] = {}
        self.all_day_buttons: List[ctk.CTkButton] = []

        cal = calendar.Calendar(firstweekday=0)
        month_weeks = cal.monthdayscalendar(self.current_year, self.current_month)

        for row_idx, week in enumerate(month_weeks):
            self.days_frame.grid_rowconfigure(row_idx, weight=1)
            self.week_rows[row_idx] = []
            for col_idx, day in enumerate(week):
                if day == 0:
                    # Blank space
                    ctk.CTkLabel(self.days_frame, text="", width=38, height=30).grid(
                        row=row_idx, column=col_idx, padx=1, pady=1
                    )
                else:
                    is_today = (
                        self.current_year == self.today_year
                        and self.current_month == self.today_month
                        and day == self.today_day
                    )
                    is_selected = (
                        self.current_year == self.selected_year
                        and self.current_month == self.selected_month
                        and day == self.selected_day
                    )

                    if self.mode == "month":
                        fg_col = "#0C2340"
                        hover_col = "#0369A1"
                        text_col = "#38BDF8"
                        border_col = "#0284C7"
                        border_w = 1.0
                        font_w = "bold" if is_today else "normal"
                    elif is_selected:
                        fg_col = "#059669"
                        hover_col = "#047857"
                        text_col = "#FFFFFF"
                        border_col = "#34D399"
                        border_w = 1.5
                        font_w = "bold"
                    elif is_today:
                        fg_col = "#141C2B"
                        hover_col = "#1E293B"
                        text_col = "#FBBF24"
                        border_col = "#F59E0B"
                        border_w = 1.2
                        font_w = "bold"
                    else:
                        fg_col = "#0C121E"
                        hover_col = "#162032"
                        text_col = "#E2E8F0"
                        border_col = "#1E293B"
                        border_w = 1.0
                        font_w = "normal"

                    day_btn = ctk.CTkButton(
                        self.days_frame,
                        text=str(day),
                        width=38,
                        height=30,
                        fg_color=fg_col,
                        hover_color=hover_col,
                        text_color=text_col,
                        border_color=border_col,
                        border_width=border_w,
                        font=ctk.CTkFont(family="Segoe UI", size=11, weight=font_w),
                        corner_radius=6,
                        cursor="hand2"
                    )

                    self.week_rows[row_idx].append((day, day_btn))
                    self.all_day_buttons.append(day_btn)

                    if self.mode == "week":
                        day_btn.configure(command=lambda d=day, r=row_idx: self._on_week_clicked(d, r))
                        self._bind_week_hover(day_btn, row_idx)
                    elif self.mode == "month":
                        day_btn.configure(command=self._on_month_clicked)
                        self._bind_month_hover(day_btn)
                    else:
                        day_btn.configure(command=lambda d=day, b=day_btn: self._on_day_clicked(d, b))
                        self._bind_day_hover(day_btn, is_selected, is_today)

                    day_btn.grid(row=row_idx, column=col_idx, padx=1, pady=1, sticky="nsew")

    def _bind_week_hover(self, btn: ctk.CTkButton, row_idx: int) -> None:
        def on_enter(e):
            for _, b in self.week_rows.get(row_idx, []):
                b.configure(border_color="#38BDF8", border_width=1.5, fg_color="#182438", text_color="#FFFFFF")
        def on_leave(e):
            for d, b in self.week_rows.get(row_idx, []):
                is_tod = (self.current_year == self.today_year and self.current_month == self.today_month and d == self.today_day)
                if is_tod:
                    b.configure(border_color="#F59E0B", border_width=1.2, fg_color="#141C2B", text_color="#FBBF24")
                else:
                    b.configure(border_color="#1E293B", border_width=1.0, fg_color="#0C121E", text_color="#E2E8F0")
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    def _on_week_clicked(self, day: int, row_idx: int) -> None:
        sound_manager.play_click()
        # Light up all days of the selected week in emerald green
        for _, b in self.week_rows.get(row_idx, []):
            b.configure(fg_color="#059669", border_color="#34D399", border_width=2.0, text_color="#FFFFFF")

        target_date = datetime(self.current_year, self.current_month, day)
        monday = target_date - timedelta(days=target_date.weekday())
        sunday = monday + timedelta(days=6)
        start_str = monday.strftime("%Y-%m-%d")
        end_str = sunday.strftime("%Y-%m-%d")
        self.after(90, lambda: self._finish_select_range(start_str, end_str))

    def _bind_month_hover(self, btn: ctk.CTkButton) -> None:
        def on_enter(e):
            btn.configure(border_color="#38BDF8", border_width=1.5, fg_color="#182438", text_color="#FFFFFF")
        def on_leave(e):
            btn.configure(border_color="#0284C7", border_width=1.0, fg_color="#0C2340", text_color="#38BDF8")
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    def _on_month_clicked(self) -> None:
        sound_manager.play_click()
        for b in self.all_day_buttons:
            b.configure(fg_color="#059669", border_color="#34D399", border_width=1.5, text_color="#FFFFFF")
        _, last_day = calendar.monthrange(self.current_year, self.current_month)
        start_str = f"{self.current_year:04d}-{self.current_month:02d}-01"
        end_str = f"{self.current_year:04d}-{self.current_month:02d}-{last_day:02d}"
        self.after(90, lambda: self._finish_select_range(start_str, end_str))

    def _bind_day_hover(self, btn: ctk.CTkButton, is_selected: bool, is_today: bool) -> None:
        """Apply vibrant hover border illumination indicating upcoming selection target."""
        def on_enter(e):
            if is_selected:
                btn.configure(border_color="#6EE7B7", border_width=2.0)
            elif is_today:
                btn.configure(border_color="#FBBF24", border_width=1.8, fg_color="#1E2A42")
            else:
                btn.configure(border_color="#38BDF8", border_width=1.5, fg_color="#182438", text_color="#FFFFFF")

        def on_leave(e):
            if is_selected:
                btn.configure(border_color="#34D399", border_width=1.5, fg_color="#059669")
            elif is_today:
                btn.configure(border_color="#F59E0B", border_width=1.2, fg_color="#141C2B")
            else:
                btn.configure(border_color="#1E293B", border_width=1.0, fg_color="#0C121E", text_color="#E2E8F0")

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    def _build_footer(self) -> None:
        """Bottom action buttons: Hoy/Semana/Mes, Sin fecha, Cerrar with Tab navigation."""
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(4, 12))

        # Main selection shortcut button
        if self.mode == "week":
            btn_txt = " Esta semana"
            btn_w = 98
        elif self.mode == "month":
            btn_txt = " Este mes"
            btn_w = 88
        else:
            btn_txt = " Hoy"
            btn_w = 76

        chk_ico = get_ctk_icon("check_green.png", size=(13, 13))
        self.today_btn = ctk.CTkButton(
            footer,
            image=chk_ico,
            text=btn_txt,
            width=btn_w,
            height=30,
            fg_color="#064E3B",
            hover_color="#065F46",
            border_color="#10B981",
            border_width=1,
            text_color="#34D399",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            cursor="hand2",
            command=self._select_today_or_range
        )
        self.today_btn.pack(side="left", padx=(0, 6))

        # "Sin fecha" button
        self.clear_btn = ctk.CTkButton(
            footer,
            text="Sin fecha",
            width=82,
            height=30,
            fg_color="#1E293B",
            hover_color="#334155",
            border_color="#475569",
            border_width=1,
            text_color="#CBD5E1",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6,
            cursor="hand2",
            command=self._clear_date
        )
        self.clear_btn.pack(side="left")

        # "Cerrar" button
        self.close_btn = ctk.CTkButton(
            footer,
            text="Cerrar",
            width=70,
            height=30,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6,
            cursor="hand2",
            command=self.destroy
        )
        self.close_btn.pack(side="right")

        # Tab navigation cycling across footer buttons
        footer_widgets = [self.today_btn, self.clear_btn, self.close_btn]
        for idx, w in enumerate(footer_widgets):
            nxt = footer_widgets[(idx + 1) % len(footer_widgets)]
            prv = footer_widgets[(idx - 1) % len(footer_widgets)]
            w.bind("<Tab>", lambda e, target=nxt: (target.focus_set(), "break")[1])
            w.bind("<Shift-Tab>", lambda e, target=prv: (target.focus_set(), "break")[1])

    def _prev_month(self) -> None:
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._update_display()

    def _next_month(self) -> None:
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._update_display()

    def _prev_year(self) -> None:
        self.current_year -= 1
        self._update_display()

    def _next_year(self) -> None:
        self.current_year += 1
        self._update_display()

    def _update_display(self) -> None:
        self.month_lbl.configure(text=f"{SPANISH_MONTHS[self.current_month]} {self.current_year}")
        self._render_days()

    def _on_day_clicked(self, day: int, btn: ctk.CTkButton) -> None:
        """Instant visual click feedback and sound before committing selected date."""
        sound_manager.play_click()
        btn.configure(
            fg_color="#10B981",
            border_color="#A7F3D0",
            border_width=2.0,
            text_color="#FFFFFF"
        )
        self.selected_day = day
        self.selected_month = self.current_month
        self.selected_year = self.current_year
        date_str = f"{self.current_year:04d}-{self.current_month:02d}-{day:02d}"
        self.after(90, lambda: self._finish_select(date_str))

    def _finish_select(self, date_str: str) -> None:
        if self.on_select:
            try:
                self.on_select(date_str)
            except Exception:
                pass
        self.destroy()

    def _finish_select_range(self, start_str: str, end_str: str) -> None:
        if self.on_select:
            try:
                self.on_select(start_str, end_str)
            except TypeError:
                self.on_select((start_str, end_str))
            except Exception:
                pass
        self.destroy()

    def _select_today_or_range(self) -> None:
        sound_manager.play_click()
        if self.mode == "week":
            now = datetime(self.today_year, self.today_month, self.today_day)
            mon = now - timedelta(days=now.weekday())
            sun = mon + timedelta(days=6)
            self._finish_select_range(mon.strftime("%Y-%m-%d"), sun.strftime("%Y-%m-%d"))
        elif self.mode == "month":
            _, last_day = calendar.monthrange(self.today_year, self.today_month)
            s = f"{self.today_year:04d}-{self.today_month:02d}-01"
            e = f"{self.today_year:04d}-{self.today_month:02d}-{last_day:02d}"
            self._finish_select_range(s, e)
        else:
            self._select_today()

    def _select_today(self) -> None:
        sound_manager.play_click()
        date_str = f"{self.today_year:04d}-{self.today_month:02d}-{self.today_day:02d}"
        if self.on_select:
            try:
                self.on_select(date_str)
            except Exception:
                pass
        self.destroy()

    def _clear_date(self) -> None:
        sound_manager.play_click()
        if self.on_select:
            try:
                if self.mode in ("week", "month"):
                    self.on_select("", "")
                else:
                    self.on_select("")
            except TypeError:
                self.on_select("")
            except Exception:
                pass
        self.destroy()
