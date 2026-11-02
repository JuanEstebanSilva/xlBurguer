"""Design System Tokens & Dark Mode Theme Configuration for Carnicería San Diego POS.

Provides an authoritative, centralized dark theme palette inspired by modern
gourmet steakhouse aesthetics: deep obsidian/charcoal surfaces, warm amber-gold
brand accents, crisp white typography (WCAG AA/AAA compliant), and emerald-green
positive indicators for cashier readability and zero eye-strain.

Additionally exposes a rich multi-palette catalog (ThemeManager) with the full
color gama library for card accent theming in the Statistics module.
"""

from __future__ import annotations
from typing import Any, Callable, Dict, List, NamedTuple, Optional
import customtkinter as ctk


# ─────────────────────────────────────────────────────────────────────────────
# Core accent palette descriptor (used by stats cards & ThemeManager)
# ─────────────────────────────────────────────────────────────────────────────
class AccentPalette(NamedTuple):
    """A named accent palette tuple for card / badge theming."""
    name: str           # Human-readable display name
    bg: str             # Card badge background
    border: str         # Card badge border / accent glow
    text: str           # Badge label / icon color
    category: str       # Logical group (frios, verdes, calidos, purpuras, neutros)


class DarkTheme:
    """Design tokens and palette constants for Dark Mode."""

    # ── Background Canvas & Surfaces ──────────────────────────────────────────
    BG_ROOT          = "#0D0E12"   # Deep obsidian base canvas
    BG_SIDEBAR       = "#13151B"   # Elevated sidebar navigation container
    BG_NAVBAR        = "#13151B"   # Top horizontal navigation header
    BG_CONTENT       = "#0D0E12"   # Active view content area
    BG_CARD          = "#181A22"   # Standard cards, containers, panels
    BG_CARD_ELEVATED = "#1E212B"   # Higher elevation (numpad, display, selected item)
    BG_INPUT         = "#14161E"   # Input entries, search fields, text boxes
    BG_MODAL         = "#15171F"   # Toplevel dialog window background
    BG_MODAL_HEADER  = "#111218"   # Dialog header bars

    # ── Borders & Dividers ───────────────────────────────────────────────────
    BORDER_SUBTLE    = "#252836"   # Gentle 1px container borders & separators
    BORDER_MUTED     = "#32374A"   # Secondary borders (input fields, table cells)
    BORDER_FOCUS     = "#F59E0B"   # Primary brand amber-gold focus ring
    BORDER_SUCCESS   = "#059669"   # Emerald green success border
    BORDER_DANGER    = "#7F1D1D"   # Crimson red error border
    BORDER_WARNING   = "#78350F"   # Amber warning border

    # ── Typography & Text Scales ─────────────────────────────────────────────
    TEXT_PRIMARY     = "#F8FAFC"   # 100% Crisp white for headlines, numbers, totals
    TEXT_SECONDARY   = "#CBD5E1"   # 85% Soft off-white for regular labels and body
    TEXT_MUTED       = "#94A3B8"   # 60% Muted slate for captions, units, subtitles
    TEXT_FAINT       = "#64748B"   # 40% Faint slate for secondary hints & icons
    TEXT_PLACEHOLDER = "#4B5563"   # Placeholder text in inputs

    # ── Brand Accents (Golden Amber & Gourmet Wine) ───────────────────────────
    ACCENT_GOLD      = "#F59E0B"   # Primary brand amber-gold
    ACCENT_GOLD_HOVER= "#D97706"   # Warm darker amber on hover
    ACCENT_GOLD_ACTIVE="#B45309"   # Active press amber
    ACCENT_GOLD_MUTED= "#78350F"   # Amber border/glow outline
    ACCENT_GOLD_BG   = "#2A1B0A"   # Subtle amber dark chip background
    ACCENT_GOLD_TEXT = "#FBBF24"   # Bright gold text

    # ── Semantic Accents ─────────────────────────────────────────────────────
    SUCCESS_PRIMARY  = "#10B981"
    SUCCESS_HOVER    = "#059669"
    SUCCESS_BG       = "#06281E"
    SUCCESS_BORDER   = "#047857"
    SUCCESS_TEXT     = "#34D399"

    DANGER_PRIMARY   = "#EF4444"
    DANGER_HOVER     = "#DC2626"
    DANGER_BG        = "#2E0D11"
    DANGER_BORDER    = "#7F1D1D"
    DANGER_TEXT      = "#F87171"

    WARNING_PRIMARY  = "#F59E0B"
    WARNING_HOVER    = "#D97706"
    WARNING_BG       = "#2E1B05"
    WARNING_BORDER   = "#78350F"
    WARNING_TEXT     = "#FBBF24"

    INFO_PRIMARY     = "#2563EB"
    INFO_HOVER       = "#1D4ED8"
    INFO_BG          = "#0F1F38"
    INFO_BORDER      = "#1E40AF"
    INFO_TEXT        = "#60A5FA"

    BTN_NEUTRAL_BG   = "#222532"
    BTN_NEUTRAL_HOVER= "#2C3040"
    BTN_NEUTRAL_TEXT = "#E2E8F0"
    BTN_NEUTRAL_BORDER = "#33384C"

    TEXT_ON_GOLD     = "#0A0A0A"
    TEXT_ON_PRIMARY  = "#0A0A0A"

    # ── PALETA DE COLORES OFICIAL SAN DIEGO ──────────────────────────────────
    # 1. Guardar (Verde)
    PALETTE_GUARDAR_BORDER     = "#80C567"
    PALETTE_GUARDAR_BG         = "#23361C"
    PALETTE_GUARDAR_HOVER_BG   = "#2C4223"
    PALETTE_GUARDAR_TEXT       = "#80C567"
    PALETTE_GUARDAR_TEXT_HOVER = "#FFFFFF"

    # 2. Títulos y Subtítulos (Dorado / Ocre)
    PALETTE_TITULOS_BORDER     = "#C5A059"
    PALETTE_TITULOS_BG         = "#4A3C21"
    PALETTE_TITULOS_HOVER_BG   = "#5A4928"
    PALETTE_TITULOS_TEXT       = "#C5A059"
    PALETTE_TITULOS_TEXT_HOVER = "#FFFFFF"

    # 3. Editar (Naranja)
    PALETTE_EDITAR_BORDER      = "#DE6E22"
    PALETTE_EDITAR_BG          = "#572B0D"
    PALETTE_EDITAR_HOVER_BG    = "#693510"
    PALETTE_EDITAR_TEXT        = "#DE6E22"
    PALETTE_EDITAR_TEXT_HOVER  = "#FFFFFF"

    # 4. Ver (Azul / Periwinkle)
    PALETTE_VER_BORDER         = "#666BC5"
    PALETTE_VER_BG             = "#212340"
    PALETTE_VER_HOVER_BG       = "#2A2D52"
    PALETTE_VER_TEXT           = "#666BC5"
    PALETTE_VER_TEXT_HOVER     = "#FFFFFF"

    # 5. Eliminar (Rosa / Vino)
    PALETTE_ELIMINAR_BORDER     = "#C5616F"
    PALETTE_ELIMINAR_BG         = "#3D1E22"
    PALETTE_ELIMINAR_HOVER_BG   = "#4D262B"
    PALETTE_ELIMINAR_TEXT       = "#C5616F"
    PALETTE_ELIMINAR_TEXT_HOVER = "#FFFFFF"

    # 6. Adicional 1 (Gris Carbón / Neutro)
    PALETTE_ADICIONAL1_BORDER     = "#4A4A4A"
    PALETTE_ADICIONAL1_BG         = "#2C2C2C"
    PALETTE_ADICIONAL1_HOVER_BG   = "#3D3D3D"
    PALETTE_ADICIONAL1_TEXT       = "#C5C5C5"
    PALETTE_ADICIONAL1_TEXT_HOVER = "#FFFFFF"

    # 7. Adicional 2 (Lila / Púrpura)
    PALETTE_ADICIONAL2_BORDER     = "#C8BFE7"
    PALETTE_ADICIONAL2_BG         = "#33303B"
    PALETTE_ADICIONAL2_HOVER_BG   = "#413D4B"
    PALETTE_ADICIONAL2_TEXT       = "#C8BFE7"
    PALETTE_ADICIONAL2_TEXT_HOVER = "#FFFFFF"

    PALETTE_SPECS: Dict[str, Dict[str, str]] = {
        "guardar": {
            "border": PALETTE_GUARDAR_BORDER,
            "bg": PALETTE_GUARDAR_BG,
            "hover_bg": PALETTE_GUARDAR_HOVER_BG,
            "text": PALETTE_GUARDAR_TEXT,
            "hover_text": PALETTE_GUARDAR_TEXT_HOVER,
        },
        "titulos": {
            "border": PALETTE_TITULOS_BORDER,
            "bg": PALETTE_TITULOS_BG,
            "hover_bg": PALETTE_TITULOS_HOVER_BG,
            "text": PALETTE_TITULOS_TEXT,
            "hover_text": PALETTE_TITULOS_TEXT_HOVER,
        },
        "editar": {
            "border": PALETTE_EDITAR_BORDER,
            "bg": PALETTE_EDITAR_BG,
            "hover_bg": PALETTE_EDITAR_HOVER_BG,
            "text": PALETTE_EDITAR_TEXT,
            "hover_text": PALETTE_EDITAR_TEXT_HOVER,
        },
        "ver": {
            "border": PALETTE_VER_BORDER,
            "bg": PALETTE_VER_BG,
            "hover_bg": PALETTE_VER_HOVER_BG,
            "text": PALETTE_VER_TEXT,
            "hover_text": PALETTE_VER_TEXT_HOVER,
        },
        "eliminar": {
            "border": PALETTE_ELIMINAR_BORDER,
            "bg": PALETTE_ELIMINAR_BG,
            "hover_bg": PALETTE_ELIMINAR_HOVER_BG,
            "text": PALETTE_ELIMINAR_TEXT,
            "hover_text": PALETTE_ELIMINAR_TEXT_HOVER,
        },
        "adicional1": {
            "border": PALETTE_ADICIONAL1_BORDER,
            "bg": PALETTE_ADICIONAL1_BG,
            "hover_bg": PALETTE_ADICIONAL1_HOVER_BG,
            "text": PALETTE_ADICIONAL1_TEXT,
            "hover_text": PALETTE_ADICIONAL1_TEXT_HOVER,
        },
        "adicional2": {
            "border": PALETTE_ADICIONAL2_BORDER,
            "bg": PALETTE_ADICIONAL2_BG,
            "hover_bg": PALETTE_ADICIONAL2_HOVER_BG,
            "text": PALETTE_ADICIONAL2_TEXT,
            "hover_text": PALETTE_ADICIONAL2_TEXT_HOVER,
        },
    }

    FONT_FAMILY      = "Cambria"
    FONT_FAMILY_TITLE = "Cambria"
    RADIUS_SM        = 6
    RADIUS_MD        = 8
    RADIUS_LG        = 10
    RADIUS_PILL      = 16

    PRIMARY          = ACCENT_GOLD
    PRIMARY_HOVER    = ACCENT_GOLD_HOVER
    PRIMARY_BORDER   = BORDER_FOCUS
    PRIMARY_BG       = ACCENT_GOLD_BG
    ACCENT_PRIMARY   = ACCENT_GOLD
    ACCENT_HOVER     = ACCENT_GOLD_HOVER
    BG_ELEVATED      = BG_CARD_ELEVATED
    BG_ROW_ALT       = "#14161E"
    BG_ROW_HOVER     = "#162036"
    BG_CARD_HOVER    = BTN_NEUTRAL_HOVER
    INPUT_BG         = BG_INPUT
    INPUT_BORDER     = BORDER_MUTED
    INPUT_TEXT       = TEXT_PRIMARY
    SUCCESS          = SUCCESS_PRIMARY
    DANGER           = DANGER_PRIMARY
    WARNING          = WARNING_PRIMARY
    INFO             = INFO_PRIMARY

    @classmethod
    def title_font(cls, size: int = 14) -> ctk.CTkFont:
        """Returns standard Cambria Bold Italic font for Titles and Subtitles."""
        return ctk.CTkFont(family=cls.FONT_FAMILY, size=size, weight="bold", slant="italic")

    @classmethod
    def subtitle_font(cls, size: int = 12) -> ctk.CTkFont:
        """Returns standard Cambria Bold Italic font for Subtitles."""
        return ctk.CTkFont(family=cls.FONT_FAMILY, size=size, weight="bold", slant="italic")

    @classmethod
    def button_font(cls, size: int = 12) -> ctk.CTkFont:
        """Returns standard Cambria Bold font for Buttons."""
        return ctk.CTkFont(family=cls.FONT_FAMILY, size=size, weight="bold", slant="roman")

    @classmethod
    def body_font(cls, size: int = 12, weight: str = "bold", slant: str = "roman") -> ctk.CTkFont:
        """Returns standard Cambria font."""
        return ctk.CTkFont(family=cls.FONT_FAMILY, size=size, weight=weight, slant=slant)


def apply_palette_button(
    btn: ctk.CTkButton,
    variant: str = "guardar",
    icon_name: Optional[str] = None,
    icon_size: tuple = (16, 16),
    font_size: int = 12,
    slant: str = "roman",
    normal_image: Optional[Any] = None,
    hover_image: Optional[Any] = None
) -> ctk.CTkButton:
    """Applies the canonical San Diego color palette and Cambria Bold typography to a CTkButton.
    When mouse hovers over, dynamically changes text and icon to crisp white (#FFFFFF),
    and restores normal palette color on mouse leave.
    """
    from utils.asset_manager import get_tinted_ctk_icon

    v = variant.lower().strip()
    spec = DarkTheme.PALETTE_SPECS.get(v, DarkTheme.PALETTE_SPECS["guardar"])

    norm_img = normal_image
    hov_img = hover_image

    if not norm_img and icon_name:
        norm_img = get_tinted_ctk_icon(icon_name, spec["text"], size=icon_size)
    if not hov_img and icon_name:
        hov_img = get_tinted_ctk_icon(icon_name, spec["hover_text"], size=icon_size)

    btn_font = ctk.CTkFont(family=DarkTheme.FONT_FAMILY, size=font_size, weight="bold", slant=slant)

    btn_cfg: Dict[str, Any] = {
        "fg_color": spec["bg"],
        "border_color": spec["border"],
        "border_width": 1,
        "hover_color": spec["hover_bg"],
        "text_color": spec["text"],
        "font": btn_font,
    }
    if norm_img:
        btn_cfg["image"] = norm_img
    btn.configure(**btn_cfg)

    btn._sd_palette_variant = v
    btn._sd_normal_text = spec["text"]
    btn._sd_hover_text = spec["hover_text"]
    btn._sd_normal_image = norm_img
    btn._sd_hover_image = hov_img

    orig_enter = getattr(btn, "_on_enter", None)
    orig_leave = getattr(btn, "_on_leave", None)

    def _custom_on_enter(event=None):
        if orig_enter:
            orig_enter(event)
        if getattr(btn, "_state", "normal") == "normal":
            try:
                btn.configure(text_color=spec["hover_text"])
                if getattr(btn, "_sd_hover_image", None):
                    btn.configure(image=btn._sd_hover_image)
            except Exception:
                pass

    def _custom_on_leave(event=None):
        if orig_leave:
            orig_leave(event)
        if getattr(btn, "_state", "normal") == "normal":
            try:
                btn.configure(text_color=spec["text"])
                if getattr(btn, "_sd_normal_image", None):
                    btn.configure(image=btn._sd_normal_image)
            except Exception:
                pass

    btn._on_enter = _custom_on_enter
    btn._on_leave = _custom_on_leave
    return btn


class PaletteButton(ctk.CTkButton):
    """CTkButton subclass styled natively with the official Carnicería San Diego palette.
    Supports dynamic white text & icon transition on hover.
    """
    def __init__(
        self,
        parent,
        variant: str = "guardar",
        icon_name: Optional[str] = None,
        icon_size: tuple = (16, 16),
        font_size: int = 12,
        slant: str = "roman",
        normal_image: Optional[Any] = None,
        hover_image: Optional[Any] = None,
        **kwargs
    ):
        v = variant.lower().strip()
        spec = DarkTheme.PALETTE_SPECS.get(v, DarkTheme.PALETTE_SPECS["guardar"])
        btn_font = kwargs.pop("font", None) or ctk.CTkFont(family=DarkTheme.FONT_FAMILY, size=font_size, weight="bold", slant=slant)

        super().__init__(
            parent,
            fg_color=spec["bg"],
            border_color=spec["border"],
            border_width=1,
            hover_color=spec["hover_bg"],
            text_color=spec["text"],
            font=btn_font,
            **kwargs
        )
        apply_palette_button(
            self,
            variant=v,
            icon_name=icon_name,
            icon_size=icon_size,
            font_size=font_size,
            slant=slant,
            normal_image=normal_image,
            hover_image=hover_image
        )



# ─────────────────────────────────────────────────────────────────────────────
# ACCENT PALETTE CATALOG — Full gama library for card accent theming
# ─────────────────────────────────────────────────────────────────────────────

ACCENT_PALETTES: Dict[str, AccentPalette] = {

    # ── PRINCIPAL: Negro + Dorado ────────────────────────────────────────────
    "gold": AccentPalette(
        name="Dorado",
        bg="#2A1B0A", border="#F59E0B", text="#FBBF24",
        category="principal"
    ),

    # ── GAMA FRÍOS Y TECNOLÓGICOS ────────────────────────────────────────────
    "cobalt": AccentPalette(
        name="Azul Cobalto",
        bg="#081226", border="#1A3B7A", text="#7AAFFF",
        category="frios"
    ),
    "navy": AccentPalette(
        name="Azul Marino",
        bg="#09162B", border="#1B4582", text="#90C2FF",
        category="frios"
    ),
    "ice": AccentPalette(
        name="Cian Hielo",
        bg="#051C21", border="#104E5C", text="#80EEFF",
        category="frios"
    ),
    "aquamarine": AccentPalette(
        name="Aguamarina",
        bg="#041F1A", border="#0B5E4F", text="#52F0D0",
        category="frios"
    ),
    "teal": AccentPalette(
        name="Turquesa",
        bg="#041A18", border="#0D4F4A", text="#38DEC9",
        category="frios"
    ),
    "indigo": AccentPalette(
        name="Índigo Noche",
        bg="#100D2B", border="#2F277D", text="#9E94FF",
        category="frios"
    ),

    # ── GAMA VERDES Y NATURALEZA ─────────────────────────────────────────────
    "mint": AccentPalette(
        name="Verde Menta",
        bg="#061F17", border="#145741", text="#79F2C3",
        category="verdes"
    ),
    "olive": AccentPalette(
        name="Verde Oliva",
        bg="#191E07", border="#475417", text="#D4E866",
        category="verdes"
    ),
    "chartreuse": AccentPalette(
        name="Pistacho",
        bg="#1B2605", border="#4F6E13", text="#CCFF52",
        category="verdes"
    ),
    "forest": AccentPalette(
        name="Verde Bosque",
        bg="#061A0C", border="#144A23", text="#5CE683",
        category="verdes"
    ),
    "sage": AccentPalette(
        name="Verde Salvia",
        bg="#121C16", border="#33523F", text="#9EE0B5",
        category="verdes"
    ),

    # ── GAMA CÁLIDOS (ROJOS, NARANJAS Y AMARILLOS) ───────────────────────────
    "ruby": AccentPalette(
        name="Rojo Rubí",
        bg="#24060A", border="#6E1320", text="#FF5E7E",
        category="calidos"
    ),
    "crimson": AccentPalette(
        name="Carmesí",
        bg="#200509", border="#5E0E1B", text="#FF8099",
        category="calidos"
    ),
    "amber": AccentPalette(
        name="Ámbar",
        bg="#1F1102", border="#6B3A00", text="#FFB340",
        category="calidos"
    ),
    "orange": AccentPalette(
        name="Naranja",
        bg="#200D02", border="#6B2D00", text="#FF7A30",
        category="calidos"
    ),
    "copper": AccentPalette(
        name="Cobre",
        bg="#1C0F05", border="#5C2E10", text="#E8924A",
        category="calidos"
    ),
    "lemon": AccentPalette(
        name="Limón",
        bg="#1C1C02", border="#595900", text="#F0F060",
        category="calidos"
    ),

    # ── GAMA VIOLETAS / PURPURAS ─────────────────────────────────────────────
    "violet": AccentPalette(
        name="Violeta",
        bg="#130B22", border="#3D1F70", text="#BF80FF",
        category="purpuras"
    ),
    "magenta": AccentPalette(
        name="Magenta",
        bg="#1F0818", border="#6B1A52", text="#FF69C2",
        category="purpuras"
    ),
    "lavender": AccentPalette(
        name="Lavanda",
        bg="#14101F", border="#3D3070", text="#A090FF",
        category="purpuras"
    ),
    "rose": AccentPalette(
        name="Rosa",
        bg="#200A14", border="#6B1F3A", text="#FF6FA0",
        category="purpuras"
    ),
    "lilac": AccentPalette(
        name="Lila",
        bg="#180F1F", border="#4F2870", text="#D480FF",
        category="purpuras"
    ),

    # ── GAMA NEUTROS Y CLÁSICOS ──────────────────────────────────────────────
    "platinum": AccentPalette(
        name="Platino",
        bg="#141418", border="#3C3C4A", text="#C8C8D8",
        category="neutros"
    ),
    "steel": AccentPalette(
        name="Acero",
        bg="#101418", border="#2A3848", text="#90A8C0",
        category="neutros"
    ),
    "smoke": AccentPalette(
        name="Humo",
        bg="#181818", border="#404040", text="#B0B0B0",
        category="neutros"
    ),
    "silver": AccentPalette(
        name="Plata",
        bg="#141620", border="#303850", text="#A8B4C8",
        category="neutros"
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# THEME MANAGER — Global singleton for palette state & observer pattern
# ─────────────────────────────────────────────────────────────────────────────
class ThemeManager:
    """Global singleton managing the active accent palette for Stats cards."""

    _instance: Optional["ThemeManager"] = None

    def __new__(cls) -> "ThemeManager":
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._active_key = "gold"
            obj._callbacks: List = []
            cls._instance = obj
        return cls._instance

    @property
    def active_key(self) -> str:
        return self._active_key

    @property
    def active(self) -> AccentPalette:
        return ACCENT_PALETTES.get(self._active_key, ACCENT_PALETTES["gold"])

    def set_palette(self, key: str) -> None:
        """Switch palette and notify all registered observers."""
        if key in ACCENT_PALETTES:
            self._active_key = key
            for cb in list(self._callbacks):
                try:
                    cb(key)
                except Exception:
                    pass

    def subscribe(self, callback) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unsubscribe(self, callback) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    @staticmethod
    def all_palettes() -> Dict[str, AccentPalette]:
        return ACCENT_PALETTES

    @staticmethod
    def palettes_by_category(category: str) -> Dict[str, AccentPalette]:
        return {k: v for k, v in ACCENT_PALETTES.items() if v.category == category}

    @staticmethod
    def categories() -> List[str]:
        seen: List[str] = []
        for p in ACCENT_PALETTES.values():
            if p.category not in seen:
                seen.append(p.category)
        return seen


# Convenience global instance
theme_manager = ThemeManager()


def safe_reset_entry(entry) -> None:
    """Safely clear a CTkEntry widget and guarantee its placeholder is properly restored
    even if cleared repeatedly or clicked without text.
    """
    try:
        entry.delete(0, "end")
        ph = getattr(entry, "_placeholder_text", None)
        if ph:
            entry._placeholder_text_active = True
            entry._entry.delete(0, "end")
            entry._entry.insert(0, ph)
            ph_color = getattr(entry, "_placeholder_text_color", "#64748B")
            entry._entry.config(fg=entry._apply_appearance_mode(ph_color))
    except Exception:
        pass


def bind_tab_navigation(
    modal: Any,
    widgets_supplier: Any,
    on_enter: Optional[Callable[[], None]] = None,
    focus_color: str = "#38BDF8",
    on_focus_callback: Optional[Callable[[Any], None]] = None
) -> None:
    """Bind Tab and Shift-Tab to traverse smoothly across the given form widgets with clear visual focus highlight.
    widgets_supplier can be a List[Any] or a Callable[[], List[Any]] to dynamically resolve active widgets.
    """
    def _get_active_list():
        raw_list = widgets_supplier() if callable(widgets_supplier) else widgets_supplier
        active = []
        for w in raw_list:
            if not w:
                continue
            try:
                if not getattr(w, "winfo_exists", lambda: False)():
                    continue
                state = str(w.cget("state")) if hasattr(w, "cget") else "normal"
                if state == "disabled":
                    continue
                active.append(w)
            except Exception:
                pass
        return active

    def _on_tab(event, reverse=False):
        curr = event.widget
        active_list = _get_active_list()
        if not active_list:
            return None
        match_idx = None
        for idx, w in enumerate(active_list):
            if (
                w == curr
                or getattr(w, "_entry", None) == curr
                or getattr(w, "_canvas", None) == curr
                or getattr(w, "_text_label", None) == curr
            ):
                match_idx = idx
                break
        if match_idx is not None:
            next_idx = (match_idx - 1) if reverse else (match_idx + 1)
            if next_idx >= len(active_list):
                next_idx = 0
            elif next_idx < 0:
                next_idx = len(active_list) - 1
            target = active_list[next_idx]
            target.focus_set()
            if isinstance(target, ctk.CTkEntry):
                target.select_range(0, "end")
            if on_focus_callback:
                try:
                    on_focus_callback(target)
                except Exception:
                    pass
            return "break"
        else:
            if active_list:
                active_list[0].focus_set()
                if isinstance(active_list[0], ctk.CTkEntry):
                    active_list[0].select_range(0, "end")
                if on_focus_callback:
                    try:
                        on_focus_callback(active_list[0])
                    except Exception:
                        pass
            return "break"

    modal.bind("<Tab>", lambda e: _on_tab(e, reverse=False))
    modal.bind("<Shift-Tab>", lambda e: _on_tab(e, reverse=True))
    modal.bind("<ISO_Left_Tab>", lambda e: _on_tab(e, reverse=True))

    all_widgets = widgets_supplier() if callable(widgets_supplier) else widgets_supplier
    for w in all_widgets:
        if not w:
            continue
        try:
            orig_border = w.cget("border_color") if hasattr(w, "cget") else "#3B4A66"

            def _focus_in(event, widget=w):
                try:
                    widget.configure(border_color=focus_color)
                except Exception:
                    pass
                if on_focus_callback:
                    try:
                        on_focus_callback(widget)
                    except Exception:
                        pass

            def _focus_out(event, widget=w, base_b=orig_border):
                try:
                    widget.configure(border_color=base_b)
                except Exception:
                    pass

            w.bind("<FocusIn>", _focus_in, add="+")
            w.bind("<FocusOut>", _focus_out, add="+")
            w.bind("<Tab>", lambda e: _on_tab(e, reverse=False))
            w.bind("<Shift-Tab>", lambda e: _on_tab(e, reverse=True))
            w.bind("<ISO_Left_Tab>", lambda e: _on_tab(e, reverse=True))

            inner_entry = getattr(w, "_entry", None)
            if inner_entry:
                inner_entry.bind("<FocusIn>", _focus_in, add="+")
                inner_entry.bind("<FocusOut>", _focus_out, add="+")
                inner_entry.bind("<Tab>", lambda e: _on_tab(e, reverse=False))
                inner_entry.bind("<Shift-Tab>", lambda e: _on_tab(e, reverse=True))
                inner_entry.bind("<ISO_Left_Tab>", lambda e: _on_tab(e, reverse=True))

            inner_canvas = getattr(w, "_canvas", None)
            if inner_canvas:
                inner_canvas.bind("<Tab>", lambda e: _on_tab(e, reverse=False))
                inner_canvas.bind("<Shift-Tab>", lambda e: _on_tab(e, reverse=True))
                inner_canvas.bind("<ISO_Left_Tab>", lambda e: _on_tab(e, reverse=True))
        except Exception:
            pass

    if on_enter:
        modal.bind("<Return>", lambda e: on_enter())
        modal.bind("<KP_Enter>", lambda e: on_enter())


