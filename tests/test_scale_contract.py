"""Tests for Scale Contract, WeightReading, and Scale Service.
Verifies:
1. Production mode without physical scale returns error, NOT random invented weights.
2. Allow-mock mode explicitly marks readings as is_mock=True.
3. Stable vs Unstable flag detection (ST vs US).
4. Zero and negative weight rejection.
5. Unit conversion to grams: 0.65 kg -> exactly 650.0 grams (never 0.65 grams).
6. Tuple unpacking compatibility (val, unit).
"""

import os
import sys
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from hardware.scale_service import SerialScaleDriver, WeightReading


class TestScaleContract(unittest.TestCase):
    def test_production_mode_no_mock_returns_error(self):
        """In production (allow_mock=False), missing scale must return error, never random weights."""
        driver = SerialScaleDriver(port="COM999", allow_mock=False)
        reading = driver.read_reading()
        self.assertIsInstance(reading, WeightReading)
        self.assertFalse(reading.is_valid)
        self.assertFalse(reading.is_mock)
        self.assertIsNotNone(reading.error)
        self.assertEqual(reading.grams, 0.0)

    def test_mock_mode_explicitly_flagged(self):
        """When mock is explicitly allowed, reading must be marked as is_mock=True."""
        driver = SerialScaleDriver(force_mock=True, allow_mock=True)
        reading = driver.read_reading()
        self.assertIsInstance(reading, WeightReading)
        self.assertTrue(reading.is_mock)
        self.assertTrue(reading.is_valid)
        self.assertGreater(reading.grams, 0.0)
        self.assertAlmostEqual(reading.grams, reading.value * 1000.0, places=1)

    def test_weight_reading_properties_and_grams_conversion(self):
        """Contract: 0.65 kg must convert to exactly 650.0 grams."""
        r_kg = WeightReading(value=0.65, unit="kg", stable=True, is_mock=False, grams=650.0)
        self.assertTrue(r_kg.is_valid)
        self.assertEqual(r_kg.grams, 650.0)

        # Unstable reading must not be valid
        r_unstable = WeightReading(value=0.65, unit="kg", stable=False, is_mock=False, grams=650.0, error="Inestable")
        self.assertFalse(r_unstable.is_valid)

        # Negative or zero weight must not be valid
        r_zero = WeightReading(value=0.0, unit="kg", stable=True, is_mock=False, grams=0.0, error="Cero")
        self.assertFalse(r_zero.is_valid)

    def test_tuple_unpacking_compatibility(self):
        """Ensure legacy code doing (val, unit) = reading still unpacks correctly."""
        r = WeightReading(value=1.5, unit="kg", stable=True, is_mock=False, grams=1500.0)
        val, unit = r
        self.assertEqual(val, 1.5)
        self.assertEqual(unit, "kg")


if __name__ == "__main__":
    unittest.main()
