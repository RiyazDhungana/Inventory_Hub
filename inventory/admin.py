from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Product,
    Vendor,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    StockAdjustment,
)

# =========================
# INLINE CLASSES
# =========================

class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    readonly_fields = ("total_cost",)
    extra = 0

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    readonly_fields = ("total_price", "cost_total", "profit")
    fields = ("product", "quantity", "total_price", "cost_total", "profit")
    extra = 0

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockAdjustmentInline(admin.TabularInline):
    model = StockAdjustment
    extra = 0
    readonly_fields = (
        "adjustment_type",
        "quantity",
        "reason",
        "user",
        "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# =========================
# PRODUCT ADMIN
# =========================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "stock_quantity",
        "minimum_stock",
        "stock_badge",
    )

    readonly_fields = ("stock_quantity",)
    inlines = [StockAdjustmentInline]
    ordering = ("stock_quantity",)
    search_fields = ("name",)
    list_filter = ("minimum_stock",)

    def has_delete_permission(self, request, obj=None):
        return False  # 🔒 Rule: Products are never deleted

    def stock_badge(self, obj):
        if obj.stock_quantity == 0:
            return format_html(
                '<span style="color:white; background:#f59e0b; padding:4px 8px; border-radius:6px;">OUT</span>'
            )
        elif obj.is_low_stock():
            return format_html(
                '<span style="color:white; background:#dc2626; padding:4px 8px; border-radius:6px;">LOW</span>'
            )
        return format_html(
            '<span style="color:white; background:#16a34a; padding:4px 8px; border-radius:6px;">OK</span>'
        )

    stock_badge.short_description = "Stock"



# =========================
# OTHER ADMINS
# =========================

@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_info")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "user", "purchase_date")
    inlines = [PurchaseItemInline]

    def has_change_permission(self, request, obj=None):
        if obj:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "sale_date", "total_profit")
    inlines = [SaleItemInline]
    change_list_template = "admin/inventory/sale/change_list.html"

    def total_profit(self, obj):
        return obj.total_profit

    total_profit.short_description = "Total Profit"

    def has_change_permission(self, request, obj=None):
        if obj:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["profit_summary"] = {
            "total_revenue": SaleItem.objects.total_revenue(),
            "total_profit": SaleItem.objects.total_profit(),
            "today_profit": SaleItem.objects.today().total_profit(),
            "month_profit": SaleItem.objects.this_month().total_profit(),
        }
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "adjustment_type",
        "quantity",
        "reason",
        "user",
        "created_at",
    )
    readonly_fields = ("user", "created_at")

    def has_change_permission(self, request, obj=None):
        if obj:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.user = request.user
        super().save_model(request, obj, form, change)

