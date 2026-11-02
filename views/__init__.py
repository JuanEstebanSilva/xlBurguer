"""Views package for Carnicería San Diego POS System."""

from views.about_modal import AboutModal
from views.calendar_modal import CalendarPickerModal
from views.inventory_frame import (
    InventoryFrame,
    InventoryFrame as InventoryView,
    ProductFormModal,
    ProductDetailModal,
    AddStockModal
)
from views.login_frame import LoginFrame, LoginView
from views.main_window import MainWindow
from views.pos_frame import (
    POSFrame,
    POSFrame as POSView,
    CheckoutModal,
    CheckoutModal as PaymentModal,
    QuantityModal,
    TouchKeypadModal,
    ProductDiscountModal,
    CompanyQuickQuotasModal
)
from views.stats_frame import StatsFrame, StatsFrame as StatsView
from views.users_frame import (
    UsersFrame,
    UserFormModal,
    UserDetailModal,
    CustomerFormModal,
    CustomerDetailModal,
    CompanyDiscountModal,
    FiadosDashboardModal
)

__all__ = [
    "AboutModal",
    "CalendarPickerModal",
    "InventoryFrame",
    "InventoryView",
    "ProductFormModal",
    "ProductDetailModal",
    "AddStockModal",
    "LoginFrame",
    "LoginView",
    "MainWindow",
    "POSFrame",
    "POSView",
    "CheckoutModal",
    "PaymentModal",
    "QuantityModal",
    "TouchKeypadModal",
    "ProductDiscountModal",
    "CompanyQuickQuotasModal",
    "StatsFrame",
    "StatsView",
    "UsersFrame",
    "UserFormModal",
    "UserDetailModal",
    "CustomerFormModal",
    "CustomerDetailModal",
    "CompanyDiscountModal",
    "FiadosDashboardModal",
]
