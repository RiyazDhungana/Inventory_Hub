from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),

    # Profit & Reports
    path("profits/", views.profit_dashboard, name="profit_dashboard"),

    # Stock
    path('low-stock/', views.low_stock_alerts, name='low_stock_alerts'),

    # Sales workflow
    path("sales/create/", views.create_sale, name="create_sale"),
    path("sales/success/", views.sale_success, name="sale_success"),
]
