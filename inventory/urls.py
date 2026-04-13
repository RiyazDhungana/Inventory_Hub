from django.urls import path
from django.contrib.auth.views import LoginView
from . import views

urlpatterns = [
    # Landing page: login
    path(
        "",
        LoginView.as_view(
            template_name="inventory/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),

    # Logout (custom view so GET works cleanly)
    path("logout/", views.logout_view, name="logout"),

    # Dashboard (after login)
    path("dashboard/", views.dashboard, name="dashboard"),

    path("reports/profit/", views.profit_report, name="profit_report"),
    path("reports/sales/", views.sales_report, name="sales_report"),
    path("reports/purchases/", views.purchase_report, name="purchase_report"),

    # Stock & Expiry
    path("low-stock/", views.low_stock_alerts, name="low_stock_alerts"),
    path("expiry-report/", views.expiry_report, name="expiry_report"),
    path("discount-report/", views.discount_report, name="discount_report"),

    # Sales workflow
    path("sales/", views.sale_list, name="sale_list"),
    path("sales/create/", views.create_sale, name="create_sale"),

    # Products
    path("products/", views.product_list, name="product_list"),
    path("products/create/", views.product_create, name="product_create"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),

    # Vendors
    path("vendors/", views.vendor_list, name="vendor_list"),
    path("vendors/create/", views.vendor_create, name="vendor_create"),
    path("vendors/<int:pk>/edit/", views.vendor_edit, name="vendor_edit"),
    path("vendors/<int:pk>/delete/", views.vendor_delete, name="vendor_delete"),

    # Purchases
    path("purchases/", views.purchase_list, name="purchase_list"),
    path("purchases/create/", views.purchase_create, name="purchase_create"),

    # Stock Adjustments
    path("stock-adjustments/", views.stock_adjustment_list, name="stock_adjustment_list"),
    path("stock-adjustments/create/", views.stock_adjustment_create, name="stock_adjustment_create"),

    # Settings
    path("settings/alerts/", views.alert_settings, name="alert_settings"),
    path("settings/alerts/test/", views.test_email_alert, name="test_email_alert"),

    # User Management
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/delete/", views.user_delete, name="user_delete"),

    # Forecasting
    path("reports/forecast/", views.forecast_dashboard, name="forecast_dashboard"),
    path("reports/forecast/accuracy/", views.forecast_accuracy_report, name="forecast_accuracy_report"),
    path("products/<int:pk>/forecast/", views.product_forecast_detail, name="product_forecast_detail"),
]
