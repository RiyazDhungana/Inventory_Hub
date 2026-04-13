from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Product, Purchase, PurchaseItem, Sale, SaleItem, StockAdjustment, Vendor


class InventorySafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="pass1234")
        self.vendor = Vendor.objects.create(name="Acme Vendor")

    def test_sale_item_rejects_when_fifo_batches_are_insufficient(self):
        product = Product.objects.create(
            name="Milk",
            sku="MILK-001",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("70.00"),
            stock_quantity=5,
            minimum_stock=1,
            shelf_life_days=7,
        )
        purchase = Purchase.objects.create(vendor=self.vendor, user=self.user)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=3,
            cost_price=Decimal("50.00"),
            batch_number="B-1",
        )

        sale = Sale.objects.create(user=self.user)
        with self.assertRaises(ValidationError):
            SaleItem.objects.create(sale=sale, product=product, quantity=5)

    def test_stock_adjustment_cannot_remove_more_than_available(self):
        product = Product.objects.create(
            name="Bread",
            sku="BREAD-001",
            cost_price=Decimal("20.00"),
            selling_price=Decimal("35.00"),
            stock_quantity=2,
            minimum_stock=1,
            shelf_life_days=3,
        )

        adjustment = StockAdjustment(
            product=product,
            adjustment_type=StockAdjustment.REMOVE,
            quantity=3,
            reason="Damage",
            user=self.user,
        )

        with self.assertRaises(ValidationError):
            adjustment.save()


class ViewSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="manager", password="pass1234")
        perm = Permission.objects.get(codename="change_product")
        self.user.user_permissions.add(perm)
        self.client.login(username="manager", password="pass1234")

    def test_product_edit_returns_404_for_missing_product(self):
        response = self.client.get(reverse("product_edit", kwargs={"pk": 999999}))
        self.assertEqual(response.status_code, 404)
