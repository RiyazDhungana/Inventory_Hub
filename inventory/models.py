# inventory/models.py
from decimal import Decimal
from datetime import timedelta, date

from django.db import models, transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.utils.timezone import now
from django.db.models.signals import post_save
from django.dispatch import receiver

from .utils import send_low_stock_email, send_expiry_alert_email

# ----------------------
# CORE MODELS
# ----------------------

class Vendor(models.Model):
    name = models.CharField(max_length=100)
    contact_info = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)

    stock_quantity = models.IntegerField(default=0)
    minimum_stock = models.IntegerField(default=10)

    # Shelf life in days
    shelf_life_days = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---------- BUSINESS RULES ----------

    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock

    def clean(self):
        if self.stock_quantity < 0:
            raise ValidationError("Stock quantity cannot be negative.")

        if self.pk:
            from .models import SaleItem, PurchaseItem
            has_transactions = (
                SaleItem.objects.filter(product=self).exists() or
                PurchaseItem.objects.filter(product=self).exists()
            )
            if has_transactions:
                old = Product.objects.get(pk=self.pk)
                if self.cost_price != old.cost_price:
                    raise ValidationError("Cannot change cost price after transactions exist.")

    def save(self, *args, **kwargs):
        skip_stock_validation = kwargs.pop("skip_stock_validation", False)
        if not skip_stock_validation:
            self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        permissions = [
            ("view_profit_dashboard", "Can view profit dashboard"),
            ("view_low_stock_alerts", "Can view low stock alerts"),
        ]

    def __str__(self):
        return self.name


class Purchase(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purchase_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Purchase #{self.id} from {self.vendor.name}"


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="purchase_items")

    quantity = models.PositiveIntegerField()
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    batch_number = models.CharField(max_length=100, blank=True, help_text="Lot/Batch number for tracking")
    current_stock = models.PositiveIntegerField(default=0, help_text="Remaining stock in this specific batch")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                # Calculate total cost
                self.total_cost = self.quantity * self.cost_price

                # Initial stock for this batch
                self.current_stock = self.quantity

                # Update stock
                self.product.stock_quantity += self.quantity
                self.product.save(update_fields=["stock_quantity"], skip_stock_validation=True)

                # Calculate expiry date
                if self.manufacture_date and self.product.shelf_life_days > 0:
                    self.expiry_date = self.manufacture_date + timedelta(days=self.product.shelf_life_days)

            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class Sale(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    sale_date = models.DateTimeField(auto_now_add=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount_authorized_by = models.CharField(max_length=100, blank=True)

    @property
    def total_revenue(self):
        gross_revenue = sum((item.total_price for item in self.items.all() if item.total_price), start=Decimal("0.00"))
        return max(Decimal("0.00"), gross_revenue - self.discount_amount)

    @property
    def total_profit(self):
        gross_profit = sum((item.profit for item in self.items.all()), start=Decimal("0.00"))
        return gross_profit - self.discount_amount

    def __str__(self):
        return f"Sale #{self.id}"


# ----------------------
# REPORTING / QUERIES
# ----------------------

class SaleItemQuerySet(models.QuerySet):
    def with_profit(self):
        return self.annotate(
            cost_total=F("cost_at_sale"),
            profit=ExpressionWrapper(
                F("total_price") - F("cost_at_sale"),
                output_field=DecimalField()
            )
        )

    def total_revenue(self):
        gross_revenue = self.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
        sale_ids = self.values_list("sale_id", flat=True).distinct()
        total_discount = Sale.objects.filter(id__in=sale_ids).aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")
        return max(Decimal("0.00"), gross_revenue - total_discount)

    def total_profit(self):
        gross_profit = self.with_profit().aggregate(total=Sum("profit"))["total"] or Decimal("0.00")
        sale_ids = self.values_list("sale_id", flat=True).distinct()
        total_discount = Sale.objects.filter(id__in=sale_ids).aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")
        return gross_profit - total_discount

    def today(self):
        today_date = now().date()
        return self.filter(sale__sale_date__date=today_date)

    def this_month(self):
        dt = now()
        return self.filter(sale__sale_date__year=dt.year, sale__sale_date__month=dt.month)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="sale_items")
    quantity = models.PositiveIntegerField()

    total_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False, null=True, blank=True)
    cost_at_sale = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=Decimal("0.00"))

    objects = SaleItemQuerySet.as_manager()

    def clean(self):
        if self.product and self.quantity:
            if self.product.stock_quantity < self.quantity:
                raise ValidationError({"quantity": f"Only {self.product.stock_quantity} items available."})
            if self.product.selling_price < self.product.cost_price:
                raise ValidationError("Selling price is lower than cost price.")

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            if not self.pk:
                self.total_price = self.quantity * self.product.selling_price

                # --- FIFO Logic ---
                remaining_to_fulfill = self.quantity
                total_cost_accumulated = Decimal("0.00")
                # Get non-empty batches, oldest expiry first
                from .models import PurchaseItem, SaleItemBatch
                batches = PurchaseItem.objects.filter(
                    product=self.product, 
                    current_stock__gt=0
                ).order_by('expiry_date', 'id')

                for batch in batches:
                    if remaining_to_fulfill <= 0:
                        break

                    take = min(batch.current_stock, remaining_to_fulfill)
                    batch.current_stock -= take
                    batch.save(update_fields=['current_stock'])

                    # Record which batch was used
                    SaleItemBatch.objects.create(
                        sale_item=self,
                        purchase_item=batch,
                        quantity=take
                    )
                    
                    total_cost_accumulated += (Decimal(str(take)) * batch.cost_price)
                    remaining_to_fulfill -= take

                # Update global product stock
                self.product.stock_quantity -= self.quantity
                self.product.save(update_fields=["stock_quantity"], skip_stock_validation=True)
                
                # Store historical cost for profit reporting
                self.cost_at_sale = total_cost_accumulated

            super().save(*args, **kwargs)

    @property
    def cost_total(self):
        return self.cost_at_sale

    @property
    def profit(self):
        return (self.total_price or Decimal("0.00")) - self.cost_at_sale

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class StockAdjustment(models.Model):
    ADD = "ADD"
    REMOVE = "REMOVE"
    ADJUSTMENT_CHOICES = [(ADD, "Add Stock"), (REMOVE, "Remove Stock")]

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    adjustment_type = models.CharField(max_length=6, choices=ADJUSTMENT_CHOICES)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            if not self.pk:
                if self.adjustment_type == self.ADD:
                    self.product.stock_quantity += self.quantity
                else:
                    self.product.stock_quantity -= self.quantity
                self.product.save(update_fields=["stock_quantity"], skip_stock_validation=True)

            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.adjustment_type} {self.quantity} - {self.product.name}"


# ----------------------
# SIGNALS (AFTER ALL MODELS)
# ----------------------

@receiver(post_save, sender=Product)
def check_low_stock(sender, instance, **kwargs):
    if instance.is_low_stock():
        recipients = [u.email for u in User.objects.filter(is_superuser=True) if u.email]
        if recipients:
            send_low_stock_email(instance.name, instance.stock_quantity, recipients)


@receiver(post_save, sender=PurchaseItem)
def check_expiry(sender, instance, **kwargs):
    if instance.expiry_date:
        alert_threshold = date.today() + timedelta(days=7)  # alert if expiring within 7 days
        if instance.expiry_date <= alert_threshold:
            recipients = [u.email for u in User.objects.filter(is_superuser=True) if u.email]
            if recipients:
                send_expiry_alert_email(
                    product_name=instance.product.name,
                    expiry_date=instance.expiry_date,
                    recipients=recipients,
                    quantity=instance.quantity
                )

# ----------------------
# ALERT SETTINGS
# ----------------------

class AlertSettings(models.Model):
    recipient_emails = models.TextField(default='', help_text='Comma-separated email addresses.')
    alert_hour = models.PositiveSmallIntegerField(default=19)
    alert_minute = models.PositiveSmallIntegerField(default=0)
    low_stock_enabled = models.BooleanField(default=True)
    expiry_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Alert Settings'

    def __str__(self):
        return f'Alert Settings (daily at {self.alert_hour:02d}:{self.alert_minute:02d})'

    def get_recipient_list(self):
        return [e.strip() for e in self.recipient_emails.split(',') if e.strip()]

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SaleItemBatch(models.Model):
    """Links a SaleItem to the specific PurchaseItem (batch) it was fulfilled from."""
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE, related_name="batch_fulfillment")
    purchase_item = models.ForeignKey(PurchaseItem, on_delete=models.CASCADE, related_name="item_sales")
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} from Batch {self.purchase_item.batch_number or self.purchase_item.id}"
