import os
import sys
import unittest
import time
import customtkinter as ctk

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_db_connection, initialize_database
from views.inventory_frame import InventoryFrame
from views.stats_frame import StatsFrame
from views.users_frame import UsersFrame

class DummyEvent:
    def __init__(self, keysym: str):
        self.keysym = keysym

class TestSearchDebounce(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self.root = ctk.CTk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_inventory_frame_search_debounce(self):
        """Test debouncing in InventoryFrame: fast keystrokes suppress intermediate searches."""
        frame = InventoryFrame(self.root)
        self.root.update()

        call_count = 0
        original_on_filter_changed = frame._on_filter_changed

        def mock_filter_changed():
            nonlocal call_count
            call_count += 1
            original_on_filter_changed()

        frame._on_filter_changed = mock_filter_changed

        # Simulate typing 'C', 'a', 'r', 'l', 'o', 's' rapidly
        word = "Carlos"
        accum = ""
        for char in word:
            accum += char
            frame.search_entry.delete(0, "end")
            frame.search_entry.insert(0, accum)
            frame._on_search_key_debounced(DummyEvent(char))

        # While timer is active, call_count should still be 0
        self.assertEqual(call_count, 0)
        self.assertIsNotNone(frame._search_debounce_job)

        # Wait for debounce duration (350ms)
        self.root.update()
        time.sleep(0.35)
        self.root.update()

        # Debounce should have expired and executed search once
        self.assertEqual(call_count, 1)
        self.assertIsNone(frame._search_debounce_job)

        # Test Enter executes immediately
        frame.search_entry.delete(0, "end")
        frame.search_entry.insert(0, "TestEnter")
        frame._on_search_key_debounced(DummyEvent("r"))
        self.assertIsNotNone(frame._search_debounce_job)

        # Press Enter
        frame._on_search_enter()
        self.assertEqual(call_count, 2)
        self.assertIsNone(frame._search_debounce_job)

    def test_stats_frame_search_debounce(self):
        """Test debouncing in StatsFrame: rapid typing does not trigger immediate filter recomputations."""
        frame = StatsFrame(self.root)
        self.root.update()

        call_count = 0
        original_on_search_key = frame._on_search_key

        def mock_search_key():
            nonlocal call_count
            call_count += 1
            original_on_search_key()

        frame._on_search_key = mock_search_key

        # Rapid typing
        for char in "12345":
            frame.search_entry.insert("end", char)
            frame._on_search_key_debounced(DummyEvent(char))

        self.assertEqual(call_count, 0)
        self.assertIsNotNone(frame._search_debounce_job)

        # Wait 350ms
        self.root.update()
        time.sleep(0.35)
        self.root.update()

        self.assertEqual(call_count, 1)
        self.assertIsNone(frame._search_debounce_job)

        # Enter triggers immediate search
        frame.search_entry.insert("end", "6")
        frame._on_search_key_debounced(DummyEvent("6"))
        frame._on_search_enter()
        self.assertIsNone(frame._search_debounce_job)

    def test_users_frame_search_debounce(self):
        """Test debouncing in UsersFrame: rapid typing does not fire queries until typing stops."""
        frame = UsersFrame(self.root)
        self.root.update()

        call_count = 0
        original_do_search = frame._do_search

        def mock_do_search():
            nonlocal call_count
            call_count += 1
            original_do_search()

        frame._do_search = mock_do_search

        # Rapid typing
        for char in "Carlos":
            frame.search_entry.insert("end", char)
            frame._on_search_key(DummyEvent(char))

        self.assertEqual(call_count, 0)
        self.assertIsNotNone(frame._search_job)

        # Wait 350ms
        self.root.update()
        time.sleep(0.35)
        self.root.update()

        self.assertEqual(call_count, 1)
        self.assertIsNone(frame._search_job)

        # Enter triggers immediate search
        frame.search_entry.insert("end", "x")
        frame._on_search_key(DummyEvent("x"))
        frame._on_search_enter()
        self.assertEqual(call_count, 2)
        self.assertIsNone(frame._search_job)

if __name__ == "__main__":
    unittest.main()
