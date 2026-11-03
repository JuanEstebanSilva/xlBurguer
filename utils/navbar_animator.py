"""Navbar Animator and Dynamic Micro-Interactions for XL Burguer POS.

Provides smooth 60fps eased tab morphing, interactive button micro-expansions,
hover glow transitions, and tactile button press animations for the top navigation bar.
"""

import math
from typing import Callable, Dict, Optional, Tuple
import customtkinter as ctk

from utils.asset_manager import get_ctk_icon
from utils.theme import DarkTheme


class NavbarAnimator:
    """Manages animations and interactive micro-interactions for the top navigation bar."""

    NAVBAR_HEIGHT = 68
    ITEM_HEIGHT = 42
    BTN_COLLAPSED_WIDTH = 52
    BTN_HOVER_WIDTH = 58
    BTN_EXPANDED_WIDTH = 135
    LOGO_WIDTH = 148
    LOGO_HEIGHT = 58
    LOGOUT_WIDTH = 44
    LOGOUT_HEIGHT = 42
    USER_BADGE_HEIGHT = 42

    def __init__(self, master_window: ctk.CTk):
        self.window = master_window
        self.active_tab_key: Optional[str] = None
        self._tab_switch_job: Optional[str] = None
        self._button_hover_jobs: Dict[str, str] = {}
        self._button_widths: Dict[str, int] = {}

    def cleanup(self) -> None:
        """Cancel all pending animation jobs to prevent exceptions on window close."""
        if self._tab_switch_job:
            try:
                self.window.after_cancel(self._tab_switch_job)
            except Exception:
                pass
            self._tab_switch_job = None

        for key, job in list(self._button_hover_jobs.items()):
            if job:
                try:
                    self.window.after_cancel(job)
                except Exception:
                    pass
        self._button_hover_jobs.clear()

    def animate_tab_switch(
        self,
        nav_buttons: Dict[str, ctk.CTkButton],
        nav_items_meta: Dict[str, Tuple[str, str]],
        target_key: str,
        total_steps: int = 10,
        interval_ms: int = 16
    ) -> None:
        """Morph widths and crossfade active vs inactive navigation buttons with easing."""
        if self._tab_switch_job:
            try:
                self.window.after_cancel(self._tab_switch_job)
            except Exception:
                pass
            self._tab_switch_job = None

        self.active_tab_key = target_key

        start_widths: Dict[str, int] = {}
        target_widths: Dict[str, int] = {}

        for k, btn in nav_buttons.items():
            icon_key, name = nav_items_meta.get(k, ("", ""))
            try:
                cur_w = self._button_widths.get(k, btn.cget("width"))
            except Exception:
                cur_w = self.BTN_COLLAPSED_WIDTH
            start_widths[k] = cur_w

            if k == target_key:
                target_widths[k] = self.BTN_EXPANDED_WIDTH
                icon_img = get_ctk_icon(f"{icon_key}_gold", size=(18, 18))
                btn.configure(
                    image=icon_img,
                    text=f"  {name}" if name else "",
                    compound="left",
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                    fg_color="#20180B",
                    border_color="#C5A059",
                    border_width=1.5,
                    text_color="#FFDC8D",
                    hover_color="#2B210F",
                    corner_radius=9
                )
            else:
                target_widths[k] = self.BTN_COLLAPSED_WIDTH
                icon_img = get_ctk_icon(f"{icon_key}_slate", size=(18, 18))
                btn.configure(
                    image=icon_img,
                    text="",
                    fg_color="#111624",
                    border_color="#283347",
                    border_width=1,
                    text_color=DarkTheme.TEXT_SECONDARY,
                    hover_color="#182033",
                    corner_radius=9
                )

        # Check if already at exact target widths or not currently mapped
        try:
            is_mapped = self.window.winfo_ismapped()
        except Exception:
            is_mapped = False

        all_equal = all(start_widths.get(k) == target_widths.get(k) for k in nav_buttons)
        if all_equal or not is_mapped:
            for k, btn in nav_buttons.items():
                self._button_widths[k] = target_widths[k]
                try:
                    btn.configure(width=target_widths[k])
                except Exception:
                    pass
            return

        def _step(step_idx: int):
            try:
                if not self.window.winfo_exists():
                    return
            except Exception:
                return

            p = step_idx / float(total_steps)
            # Cubic ease-out curve for natural fluid motion
            ease = 1.0 - math.pow(1.0 - p, 2.4)

            for k, btn in nav_buttons.items():
                try:
                    if not btn.winfo_exists():
                        continue
                    w_start = start_widths.get(k, self.BTN_COLLAPSED_WIDTH)
                    w_target = target_widths.get(k, self.BTN_COLLAPSED_WIDTH)
                    cur_w = round(w_start + (w_target - w_start) * ease)
                    self._button_widths[k] = cur_w
                    btn.configure(width=cur_w)
                except Exception:
                    pass

            if step_idx < total_steps:
                try:
                    self._tab_switch_job = self.window.after(interval_ms, _step, step_idx + 1)
                except Exception:
                    self._tab_switch_job = None
            else:
                self._tab_switch_job = None
                for k, btn in nav_buttons.items():
                    try:
                        if btn.winfo_exists():
                            self._button_widths[k] = target_widths[k]
                            btn.configure(width=target_widths[k])
                    except Exception:
                        pass

        _step(1)

    def attach_button_hover(self, btn: ctk.CTkButton, key: str) -> None:
        """Attach smooth micro-expansion and highlight animation on hover for inactive buttons."""
        orig_enter = getattr(btn, "_on_enter", None)
        orig_leave = getattr(btn, "_on_leave", None)

        def _on_hover_enter(event=None):
            if orig_enter:
                orig_enter(event)
            if self.active_tab_key == key:
                return
            try:
                btn.configure(
                    border_width=1,
                    border_color="#3B4A68",
                    fg_color="#182033"
                )
            except Exception:
                pass
            self._animate_button_width(btn, key, self.BTN_HOVER_WIDTH, steps=4, interval_ms=12)

        def _on_hover_leave(event=None):
            if orig_leave:
                orig_leave(event)
            if self.active_tab_key == key:
                return
            try:
                btn.configure(
                    border_width=1,
                    border_color="#283347",
                    fg_color="#111624"
                )
            except Exception:
                pass
            self._animate_button_width(btn, key, self.BTN_COLLAPSED_WIDTH, steps=4, interval_ms=12)

        btn._on_enter = _on_hover_enter
        btn._on_leave = _on_hover_leave

    def _animate_button_width(
        self,
        btn: ctk.CTkButton,
        key: str,
        target_w: int,
        steps: int = 4,
        interval_ms: int = 12
    ) -> None:
        """Smooth micro-transition of individual button width."""
        if self._button_hover_jobs.get(key):
            try:
                self.window.after_cancel(self._button_hover_jobs[key])
            except Exception:
                pass
            self._button_hover_jobs[key] = None

        try:
            start_w = self._button_widths.get(key, btn.cget("width"))
        except Exception:
            start_w = self.BTN_COLLAPSED_WIDTH

        if start_w == target_w:
            return

        def _step(step_idx: int):
            try:
                if not btn.winfo_exists() or self.active_tab_key == key:
                    return
            except Exception:
                return

            p = step_idx / float(steps)
            ease = 1.0 - math.pow(1.0 - p, 2)
            cur_w = round(start_w + (target_w - start_w) * ease)
            self._button_widths[key] = cur_w
            try:
                btn.configure(width=cur_w)
            except Exception:
                return

            if step_idx < steps:
                try:
                    self._button_hover_jobs[key] = self.window.after(interval_ms, _step, step_idx + 1)
                except Exception:
                    self._button_hover_jobs[key] = None
            else:
                self._button_hover_jobs[key] = None
                self._button_widths[key] = target_w
                try:
                    btn.configure(width=target_w)
                except Exception:
                    pass

        _step(1)

    def attach_badge_hover(self, frame: ctk.CTkFrame, label: ctk.CTkLabel) -> None:
        """Attach smooth blue glow hover animation to user badge."""
        def _on_enter(e=None):
            try:
                frame.configure(
                    border_color="#3B82F6",
                    fg_color="#182338"
                )
                label.configure(text_color="#FFFFFF")
            except Exception:
                pass

        def _on_leave(e=None):
            try:
                frame.configure(
                    border_color="#253147",
                    fg_color="#111724"
                )
                label.configure(text_color="#CBD5E1")
            except Exception:
                pass

        for widget in (frame, label):
            try:
                widget.configure(cursor="hand2")
                widget.bind("<Enter>", _on_enter, add="+")
                widget.bind("<Leave>", _on_leave, add="+")
            except Exception:
                pass

    def attach_logout_hover(self, btn: ctk.CTkButton, on_logout_action: Callable) -> None:
        """Attach smooth crimson glow and tactile press animation to logout button."""
        orig_enter = getattr(btn, "_on_enter", None)
        orig_leave = getattr(btn, "_on_leave", None)

        def _on_hover_enter(event=None):
            if orig_enter:
                orig_enter(event)
            try:
                btn.configure(
                    border_width=2,
                    border_color="#EF4444",
                    fg_color="#381419"
                )
            except Exception:
                pass

        def _on_hover_leave(event=None):
            if orig_leave:
                orig_leave(event)
            try:
                btn.configure(
                    border_width=1.5,
                    border_color="#DC2626",
                    fg_color="#220D11"
                )
            except Exception:
                pass

        btn._on_enter = _on_hover_enter
        btn._on_leave = _on_hover_leave

        def _animated_click():
            try:
                btn.configure(border_width=3, fg_color="#5D1820")
                self.window.after(75, lambda: _finish_click())
            except Exception:
                on_logout_action()

        def _finish_click():
            try:
                btn.configure(border_width=1, fg_color=DarkTheme.DANGER_BG)
            except Exception:
                pass
            on_logout_action()

        btn.configure(command=_animated_click)

    def attach_logo_interaction(self, widget, on_click_action: Callable) -> None:
        """Set pointer cursor, click event and subtle hover feedback for logo."""
        try:
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda e: on_click_action(), add="+")
        except Exception:
            pass
