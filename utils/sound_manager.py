"""Sound Manager for Carnicería San Diego POS System.
Provides elegant, professional, non-blocking acoustic feedback:
- Barcode scanner: crisp single-tone confirmation
- Item added: warm two-note ascending chime
- Sale completed: ascending three-note success fanfare
- Warning: gentle mid-range alert
- Error: low descending two-note tone
- Login success: celebratory ascending arpeggio

Uses Python standard library 'winsound' on Windows with 0 external dependencies.
All sounds are dispatched asynchronously in background daemon threads so the GUI
thread never waits or stutters.

Sound design philosophy:
  - No harsh beeps or single high-frequency tones
  - Sequences of 2-3 notes feel musical and elegant
  - Frequencies chosen from musical scales (A major / C major pentatonic)
  - Durations kept short (≤ 280 ms total) to be non-intrusive
"""

import logging
import sys
import threading
from typing import List, Optional, Tuple


# Musical note frequencies (Hz) — A major pentatonic scale
_A4  = 440
_B4  = 494
_CS5 = 554
_E5  = 659
_FS5 = 740
_A5  = 880
_CS6 = 1109

# C major pentatonic extras
_C5  = 523
_D5  = 587
_G5  = 784
_G4  = 392
_E4  = 330


class SoundManager:
    """Manages audio feedback for POS actions with non-blocking execution and mute toggle."""

    _instance: Optional["SoundManager"] = None

    def __new__(cls) -> "SoundManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.enabled = True
        self._is_windows = sys.platform.startswith("win")
        self._winsound = None

        if self._is_windows:
            try:
                import winsound
                self._winsound = winsound
            except ImportError:
                self._is_windows = False

    def toggle_sound(self) -> bool:
        """Toggle mute state. Returns new enabled status."""
        self.enabled = not self.enabled
        if self.enabled:
            self.play_added()
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def _play_tones(self, tones: List[Tuple[int, int]]) -> None:
        """Internal worker: play a sequence of (frequency_hz, duration_ms) asynchronously."""
        if not self.enabled or not self._is_windows or not self._winsound:
            return

        def _worker():
            try:
                for freq, dur in tones:
                    self._winsound.Beep(int(freq), int(dur))
            except Exception as e:
                logging.debug("Error reproduciendo sonido POS: %s", e)

        t = threading.Thread(target=_worker, daemon=True, name="POS-SoundWorker")
        t.start()

    # ── Sound Effects ────────────────────────────────────────────────────────

    def play_barcode(self) -> None:
        """Crisp two-note scanner confirmation — snappy, professional, non-intrusive.
        Notes: E5 → A5 (ascending perfect fifth, ~90 ms total)
        """
        self._play_tones([(_E5, 40), (_A5, 50)])

    def play_added(self) -> None:
        """Warm rising chime when an item is added to the cart.
        Notes: C5 → E5 → G5 (C major arpeggio, ~140 ms total)
        """
        self._play_tones([(_C5, 40), (_E5, 45), (_G5, 55)])

    def play_sale_success(self) -> None:
        """Triumphant ascending fanfare when a sale is finalized.
        Notes: E5 → A5 → CS6 (A major arpeggio, ~230 ms total — celebratory but brief)
        """
        self._play_tones([(_E5, 60), (_A5, 70), (_CS6, 100)])

    def play_warning(self) -> None:
        """Gentle descending alert for validation warnings or missing inputs.
        Notes: G5 → E5 (minor third descent, ~130 ms total — noticeable but soft)
        """
        self._play_tones([(_G5, 60), (_E5, 70)])

    def play_error(self) -> None:
        """Soft descending two-note tone for rejected actions or errors.
        Notes: D5 → G4 (descending fifth, ~160 ms — clearly negative without being harsh)
        """
        self._play_tones([(_D5, 70), (_G4, 90)])

    def play_login_success(self) -> None:
        """Welcoming ascending arpeggio on successful login.
        Notes: C5 → E5 → A5 → CS6 (A major spread, ~280 ms total)
        """
        self._play_tones([(_C5, 55), (_E5, 60), (_A5, 65), (_CS6, 100)])

    def play_click(self) -> None:
        """Subtle tactile feedback for button clicks."""
        self._play_tones([(_E5, 30)])

    def play_success(self) -> None:
        """Alias for play_sale_success."""
        self.play_sale_success()


# Global singleton instance
sound_manager = SoundManager()
