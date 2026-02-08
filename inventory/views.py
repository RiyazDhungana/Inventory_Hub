from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import F
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Product, Sale, SaleItem


# =========================
# HOME
# =========================
def home(request):
    return HttpResponse("Inventory Hub is running 🚀")


# =========================
# PROFIT DASHBOARD
# =========================
@login_required
@permission_required("inventory.view_profit_dashboard", raise_exception=True)
def profit_dashboard(request):
    qs = SaleItem.objects

    context = {
        "total_revenue": qs.total_revenue(),
        "total_profit": qs.total_profit(),
        "today_profit": qs.today().total_profit(),
        "month_profit": qs.this_month().total_profit(),
    }

    return render(request, "inventory/profit_dashboard.html", context)


# =========================
# LOW STOCK ALERTS
# =========================
@login_required
@permission_required("inventory.view_low_stock_alerts", raise_exception=True)
def low_stock_alerts(request):
    products = Product.objects.filter(
        stock_quantity__lte=F("minimum_stock")
    )

    return render(
        request,
        "inventory/low_stock_alerts.html",
        {"products": products}
    )


# =========================
# SALES WORKFLOW (STAFF)
# =========================
@login_required
@permission_required("inventory.add_sale", raise_exception=True)
def create_sale(request):
    products = Product.objects.all()

    if request.method == "POST":
        product_id = request.POST.get("product")
        quantity = request.POST.get("quantity")

        try:
            with transaction.atomic():
                product = Product.objects.get(id=product_id)
                quantity = int(quantity)

                sale = Sale.objects.create(user=request.user)

                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity
                )

            return redirect("sale_success")

        except ValidationError as e:
            return render(request, "inventory/create_sale.html", {
                "products": products,
                "form_error": list(e.message_dict.values())[0][0]
            })

        except Exception as e:
            return render(request, "inventory/create_sale.html", {
                "products": products,
                "form_error": str(e)
            })

    return render(request, "inventory/create_sale.html", {
        "products": products
    })


# =========================
# SALE SUCCESS
# =========================
@login_required
def sale_success(request):
    return render(request, "inventory/sale_success.html")
