from django.utils.timezone import now
from django.db.models import F
from .models import Product, PurchaseItem, AlertSettings
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
import datetime

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