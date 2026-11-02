"""UI Smoke Test for Carnicería San Diego.
Validates that CustomTkinter windows, frames, views, and the new Single-Window App
instantiate and transition between frames without syntax or runtime errors.
"""

import os
import sys
import unittest
from unittest.mock import patch

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import initialize_database
from main import App
from models.user import User
from utils.asset_manager import ensure_assets
from views import LoginView
from views.main_window import MainWindow


class TestUISmoke(unittest.TestCase):
    """Ensure CustomTkinter GUI components build and transition cleanly."""

    @classmethod
    def setUpClass(cls):
        ensure_assets()
        initialize_database()

    def test_login_view_instantiation(self):
        """Verify legacy LoginView window builds without crashing."""
        app = LoginView(on_login_success=lambda u: None)
        self.assertIsNotNone(app)
        app.update_idletasks()
        try:
            app.destroy()
            app.update()
        except Exception:
            pass

    def test_main_window_and_views_instantiation(self):
        """Verify legacy MainWindow and all subviews instantiate properly."""
        test_user = User(id=1, username="admin", password_hash="", full_name="Administrador", role="ADMIN")
        main_win = MainWindow(current_user=test_user, on_logout_callback=lambda: None)
        self.assertIsNotNone(main_win)

        main_win._show_view("pos")
        main_win.update_idletasks()

        main_win._show_view("inventory")
        main_win.update_idletasks()

        main_win._show_view("stats")
        main_win.update_idletasks()

        main_win._show_view("users")
        main_win.update_idletasks()
        self.assertIn("users", main_win.views)

        try:
            main_win._on_close()
            main_win.update()
        except Exception:
            pass

    def test_single_window_app_lifecycle_and_frame_switching(self):
        """Verify the new single-window App class, login transition, and frame switching."""
        app = App()
        self.assertIsNotNone(app)
        app.update_idletasks()

        # Initial frame should be login and window should be maximized (zoomed)
        self.assertIn("login", app.frames)
        login_frame = app.frames["login"]
        self.assertIsNotNone(login_frame)
        self.assertEqual(app.state(), "zoomed")

        # Simulate user login with admin user
        test_user = User(id=1, username="admin", password_hash="", full_name="Administrador", role="ADMIN")
        app.on_login_success(test_user)
        app.update_idletasks()

        # Top navbar should now be visible, pos frame loaded, and state still zoomed
        self.assertEqual(app.state(), "zoomed")
        self.assertTrue(app.top_navbar.winfo_ismapped())
        self.assertFalse(app.sidebar.winfo_ismapped())
        self.assertIn("pos", app.frames)
        self.assertTrue(app.frames["pos"].winfo_ismapped())

        # Switch to inventory
        app.show_frame("inventory")
        app.update_idletasks()
        self.assertIn("inventory", app.frames)
        self.assertTrue(app.frames["inventory"].winfo_ismapped())

        # Switch to stats
        app.show_frame("stats")
        app.update_idletasks()
        self.assertIn("stats", app.frames)
        self.assertTrue(app.frames["stats"].winfo_ismapped())

        # Switch to users
        app.show_frame("users")
        app.update_idletasks()
        self.assertIn("users", app.frames)
        self.assertTrue(app.frames["users"].winfo_ismapped())

        # Switch back to pos
        app.show_frame("pos")
        app.update_idletasks()
        self.assertTrue(app.frames["pos"].winfo_ismapped())

        # Simulate logout (mock messagebox.askyesno to return True)
        with patch("tkinter.messagebox.askyesno", return_value=True):
            app.logout()
            app.update_idletasks()

        # Top navbar should be unmapped, login visible, and state maintained zoomed
        self.assertFalse(app.top_navbar.winfo_ismapped())
        self.assertTrue(app.frames["login"].winfo_ismapped())
        self.assertEqual(app.state(), "zoomed")

        # Clean teardown
        app._on_close()


if __name__ == "__main__":
    unittest.main()
