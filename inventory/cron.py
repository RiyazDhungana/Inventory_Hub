from django.utils.timezone import now, timedelta
from .models import Product
from .utils import send_low_stock_email, send_expiry_alert_email
from django.contrib.auth.models import User

def check_stock_and_expiry():
    superusers = [u.email for u in User.objects.filter(is_superuser=True) if u.email]
    if not superusers:
        return

    # --- Low Stock Alert ---
    low_stock_products = Product.objects.filter(stock_quantity__lte=models.F('minimum_stock'))
    for product in low_stock_products:
        send_low_stock_email(product.name, product.stock_quantity, superusers)

    # --- Expiry Alert ---
    today = now().date()
    warning_days = 7  # notify 7 days before expiry
    products = Product.objects.all()
    for product in products:
        # Check all purchase items for this product
        for item in product.purchaseitem_set.all():
            if item.expiry_date and 0 <= (item.expiry_date - today).days <= warning_days:
                send_expiry_alert_email(
                    product_name=product.name,
                    quantity=item.quantity,
                    expiry_date=item.expiry_date,
                    recipients=superusers
                )