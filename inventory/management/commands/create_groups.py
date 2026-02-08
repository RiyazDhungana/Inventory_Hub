from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from inventory.models import Product, Sale, SaleItem

class Command(BaseCommand):
    help = "Create default groups and assign permissions"

    def handle(self, *args, **kwargs):
        admin, _ = Group.objects.get_or_create(name="Admin")
        manager, _ = Group.objects.get_or_create(name="Manager")
        staff, _ = Group.objects.get_or_create(name="Staff")

        # Custom permissions
        product_ct = ContentType.objects.get_for_model(Product)
        view_profit = Permission.objects.get(
            codename="view_profit_dashboard",
            content_type=product_ct
        )
        view_low_stock = Permission.objects.get(
            codename="view_low_stock_alerts",
            content_type=product_ct
        )

        # Built-in permissions
        add_sale = Permission.objects.get(codename="add_sale")
        add_saleitem = Permission.objects.get(codename="add_saleitem")

        # Admin → everything
        admin.permissions.set(Permission.objects.all())

        # Manager → sales + reports
        manager.permissions.set([
            add_sale,
            add_saleitem,
            view_profit,
            view_low_stock,
        ])

        # Staff → sales + alerts
        staff.permissions.set([
            add_sale,
            add_saleitem,
            view_low_stock,
        ])

        self.stdout.write(self.style.SUCCESS("Groups and permissions set"))
