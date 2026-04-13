from django.utils.timezone import now
from django.db.models import F
from .models import Product, PurchaseItem, AlertSettings
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
import datetime
import os
import logging
from .forecasting import run_forecast_for_product, ingest_excel_history

logger = logging.getLogger(__name__)

def update_demand_forecasts():
    """
    Refreshes the 30-day demand forecast for all products.
    """
    excel_path = os.path.join(settings.BASE_DIR, "Online Retail.xlsx")
    excel_df = None
    if os.path.exists(excel_path):
        excel_df = ingest_excel_history(excel_path)
    
    products = Product.objects.all()
    count = 0
    for p in products:
        # Note: In a production environment with thousands of products, 
        # this should be processed in background tasks (like Huey/Celery) 
        # to avoid blocking the main scheduler for too long.
        if run_forecast_for_product(p.id, excel_df):
            count += 1
    
    logger.info(f"Successfully updated forecasts for {count} products.")


def check_stock_and_expiry():
    alert_settings = AlertSettings.get_settings()
    recipients = alert_settings.get_recipient_list()
    
    if not recipients:
        # Fallback to superusers if no specific recipients configured
        recipients = [u.email for u in User.objects.filter(is_superuser=True) if u.email]
    
    if not recipients:
        return

    # --- Low Stock Alert ---
    if alert_settings.low_stock_enabled:
        low_stock_products = Product.objects.filter(stock_quantity__lte=F('minimum_stock'))
        if low_stock_products.exists():
            lines = [f"  - {p.name}: {p.stock_quantity} units (min: {p.minimum_stock})" for p in low_stock_products]
            body = "The following products are running low on stock:\n\n" + "\n".join(lines)
            send_mail(
                subject="[Inventory Hub] Low Stock Alert",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
            )

    # --- Expiry Alert ---
    if alert_settings.expiry_enabled:
        today = now().date()
        warning_days = 7
        threshold = today + datetime.timedelta(days=warning_days)
        expiring_items = PurchaseItem.objects.filter(
            expiry_date__isnull=False,
            expiry_date__lte=threshold,
            current_stock__gt=0,
        ).select_related("product")

        if expiring_items.exists():
            lines = []
            for item in expiring_items:
                status = "EXPIRED" if item.expiry_date < today else f"expires {item.expiry_date}"
                batch_info = f" [Batch: {item.batch_number}]" if item.batch_number else ""
                lines.append(f"  - {item.product.name}{batch_info}: {item.current_stock} units ({status})")
            body = "The following product batches are expiring soon or already expired:\n\n" + "\n".join(lines)
            send_mail(
                subject="[Inventory Hub] Expiry Alert",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
            )