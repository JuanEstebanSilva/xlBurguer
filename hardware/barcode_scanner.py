"""Barcode Scanner HID Buffer Handler for XL Burguer POS.
Differentiates between human typing and ultra-fast hardware barcode scanner bursts.
"""

import time
from typing import Callable, Optional


class BarcodeScannerListener:
    """Listens to keyboard events to detect hardware barcode scanner bursts."""

    def __init__(
        self,
        on_scan_callback: Callable[[str], None],
        max_char_interval: float = 0.070,  # 70 milliseconds threshold
        min_barcode_length: int = 3
    ):
        self.on_scan_callback = on_scan_callback
        self.max_char_interval = max_char_interval
        self.min_barcode_length = min_barcode_length
        self._buffer = ""
        self._last_char_time = 0.0

    def handle_key_press(self, char: str, key_name: str) -> Optional[str]:
        """Process a single key press event.
        Returns the scanned code if a full barcode was detected, or None.
        """
        now = time.time()
        elapsed = now - self._last_char_time if self._last_char_time > 0 else 0.0
        self._last_char_time = now

        if key_name in ("Return", "KP_Enter", "\r", "\n"):
            code = self._buffer.strip()
            self._buffer = ""
            if len(code) >= self.min_barcode_length:
                self.on_scan_callback(code)
                return code
            return None

        # Ignore non-printable control keys
        if len(char) == 1 and char.isprintable():
            # If time between characters was too long, start a new burst
            if elapsed > self.max_char_interval and self._buffer:
                self._buffer = ""
            self._buffer += char

        return None

    def reset(self) -> None:
        """Clear the current character buffer."""
        self._buffer = ""
        self._last_char_time = 0.0
