from decimal import Decimal

from django.db import models, transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.utils.timezone import now


# ---------- CORE MODELS ----------

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---------- BUSINESS RULES ----------

    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock

    def clean(self):
        # Rule 1: stock can never be negative
        if self.stock_quantity < 0:
            raise ValidationError("Stock quantity cannot be negative.")

        # Rule 2: lock prices after any transaction
        if self.pk:
            from .models import SaleItem, PurchaseItem

            has_transactions = (
                SaleItem.objects.filter(product=self).exists()
                or PurchaseItem.objects.filter(product=self).exists()
            )

            if has_transactions:
                old = Product.objects.get(pk=self.pk)
                if (
                    self.cost_price != old.cost_price
                    or self.selling_price != old.selling_price
                ):
                    raise ValidationError(
                        "Cannot change prices after transactions exist."
                    )

    def save(self, *args, **kwargs):
        # Rule 3: stock_quantity cannot be manually edited
        if self.pk:
            old = Product.objects.get(pk=self.pk)
            if self.stock_quantity != old.stock_quantity:
                raise ValidationError(
                    "Stock quantity cannot be modified directly."
                )

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
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    quantity = models.PositiveIntegerField()
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False
    )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                self.total_cost = self.quantity * self.cost_price

                self.product.stock_quantity += self.quantity
                self.product.save(update_fields=["stock_quantity"])

            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class Sale(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    sale_date = models.DateTimeField(auto_now_add=True)

    @property
    def total_profit(self):
        return sum(
            (item.profit for item in self.items.all()),
            start=Decimal("0.00")
        )

    def __str__(self):
        return f"Sale #{self.id}"


# ---------- REPORTING / QUERIES ----------

class SaleItemQuerySet(models.QuerySet):
    def with_profit(self):
        return self.annotate(
            cost_total=ExpressionWrapper(
                F("quantity") * F("product__cost_price"),
                output_field=DecimalField()
            ),
            profit=ExpressionWrapper(
                F("total_price") - (F("quantity") * F("product__cost_price")),
                output_field=DecimalField()
            )
        )

    def total_revenue(self):
        return self.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")

    def total_profit(self):
        return self.with_profit().aggregate(total=Sum("profit"))["total"] or Decimal("0.00")

    def today(self):
        today = now().date()
        return self.filter(sale__sale_date__date=today)

    def this_month(self):
        dt = now()
        return self.filter(
            sale__sale_date__year=dt.year,
            sale__sale_date__month=dt.month
        )


class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        null=True,
        blank=True
    )

    objects = SaleItemQuerySet.as_manager()

    def clean(self):
        if self.product and self.quantity:
            if self.product.stock_quantity < self.quantity:
                raise ValidationError(
                    {"quantity": f"Only {self.product.stock_quantity} items available."}
                )

            if self.product.selling_price < self.product.cost_price:
                raise ValidationError(
                    "Selling price is lower than cost price."
                )

    def save(self, *args, **kwargs):
        self.full_clean()

        with transaction.atomic():
            if not self.pk:
                self.total_price = self.quantity * self.product.selling_price

                self.product.stock_quantity -= self.quantity
                self.product.save(update_fields=["stock_quantity"])

            super().save(*args, **kwargs)

    @property
    def cost_total(self):
        return self.quantity * self.product.cost_price

    @property
    def profit(self):
        return (self.total_price or Decimal("0.00")) - self.cost_total

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class StockAdjustment(models.Model):
    ADD = "ADD"
    REMOVE = "REMOVE"

    ADJUSTMENT_CHOICES = [
        (ADD, "Add Stock"),
        (REMOVE, "Remove Stock"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    adjustment_type = models.CharField(max_length=6, choices=ADJUSTMENT_CHOICES)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                if self.adjustment_type == self.ADD:
                    self.product.stock_quantity += self.quantity
                else:
                    if self.product.stock_quantity < self.quantity:
                        raise ValidationError("Not enough stock to remove.")
                    self.product.stock_quantity -= self.quantity

                self.product.save(update_fields=["stock_quantity"])

            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.adjustment_type} {self.quantity} - {self.product.name}"
