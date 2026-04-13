import csv
import json
import subprocess
import threading
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.db.models import F, Sum, DecimalField, ExpressionWrapper, Count
from django.db.models.functions import TruncDate
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now
from datetime import timedelta, datetime, date

from .models import Product, Sale, SaleItem, Vendor, Purchase, PurchaseItem, StockAdjustment, AlertSettings, DemandForecast
from .forms import VendorForm, PurchaseForm, PurchaseItemForm, StockAdjustmentForm, ProductForm, ProductEditForm, AlertSettingsForm, AppUserCreationForm, AppUserUpdateForm
from .utils_auth import setup_user_groups
from django.contrib import messages
# =========================
# DASHBOARD (post-login)
# =========================
@login_required
def dashboard(request):
    # Determine requested period
    period = request.GET.get("period", "today")  # default today
    dt_now = now()
    today_date = dt_now.date()

    if period == "week":
        start_date = today_date - timedelta(days=6)
    elif period == "month":
        start_date = dt_now.replace(day=1).date()
    else:
        # Default to today
        start_date = today_date

    end_date = today_date

    # Period metrics
    period_qs = SaleItem.objects.filter(
        sale__sale_date__date__gte=start_date,
        sale__sale_date__date__lte=end_date
    )
    
    period_revenue = period_qs.total_revenue() or 0
    period_profit = period_qs.total_profit() or 0

    period_sales = Sale.objects.filter(
        sale_date__date__gte=start_date,
        sale_date__date__lte=end_date
    )
    period_discount = period_sales.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")

    # Low Stock Items (always global)
    low_stock_count = Product.objects.filter(stock_quantity__lte=F("minimum_stock")).count()

    # Chart 1: Revenue & Profit (over the selected period, max 31 days)
    # If the period is 'today', creating a daily chart isn't super useful but we will show the single day.
    daily = (
        period_qs
        .annotate(
            date=TruncDate("sale__sale_date"),
            item_profit=ExpressionWrapper(
                F("total_price") - F("cost_at_sale"),
                output_field=DecimalField(),
            ),
        )
        .values("date")
        .annotate(
            revenue=Sum("total_price"),
            profit=Sum("item_profit"),
        )
        .order_by("date")
    )

    def _norm_date(dt):
        return dt.date() if hasattr(dt, "date") else dt

    date_labels = []
    revenue_data = []
    profit_data = []
    
    days_range = (end_date - start_date).days + 1
    
    for i in range(days_range):
        d = start_date + timedelta(days=i)
        
        # Format label based on range size
        if days_range <= 7:
            date_labels.append(d.strftime("%a")) # Mon, Tue short names
        else:
            date_labels.append(d.strftime("%b %d")) # Jan 01
            
        row = next((x for x in daily if _norm_date(x["date"]) == d), None)
        revenue_data.append(float(row["revenue"]) if row and row["revenue"] else 0)
        profit_data.append(float(row["profit"]) if row and row["profit"] else 0)

    # Chart 2: Top Selling Products By Revenue (in selected period)
    top_products = (
        period_qs.values("product__name")
        .annotate(revenue=Sum("total_price"))
        .order_by("-revenue")[:5]
    )
    top_product_names = [p["product__name"] or "Unknown" for p in top_products]
    top_product_revenue = [float(p["revenue"] or 0) for p in top_products]

    # Chart 3: Top Selling Products by Quantity (in selected period)
    top_products_qty = (
        period_qs.values("product__name")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")[:5]
    )
    top_qty_names = [p["product__name"] or "Unknown" for p in top_products_qty]
    top_qty_values = [int(p["total_qty"] or 0) for p in top_products_qty]

    # Fast Moving Products (Most quantity sold in selected period)
    fast_moving = (
        period_qs
        .values("product__id", "product__name", "product__stock_quantity")
        .annotate(sold=Sum("quantity"))
        .order_by("-sold")[:5]
    )

    # Slow Moving Products (Items in stock but with 0 sales in selected period)
    recently_sold_product_ids = (
        period_qs.values_list("product_id", flat=True)
    )
    slow_moving = (
        Product.objects.filter(stock_quantity__gt=0)
        .exclude(id__in=recently_sold_product_ids)
        .order_by("-stock_quantity")[:5]
    )

    context = {
        "period": period,
        "period_revenue": period_revenue,
        "period_profit": period_profit,
        "period_discount": period_discount,
        "low_stock_count": low_stock_count,
        "date_labels": json.dumps(date_labels),
        "revenue_data": json.dumps(revenue_data),
        "profit_data": json.dumps(profit_data),
        "top_product_names": json.dumps(top_product_names),
        "top_product_revenue": json.dumps(top_product_revenue),
        "top_qty_names": json.dumps(top_qty_names),
        "top_qty_values": json.dumps(top_qty_values),
        "fast_moving": fast_moving,
        "slow_moving": slow_moving,
    }

    return render(request, "inventory/dashboard.html", context)


# =========================
# LOGOUT (redirect to login)
# =========================
@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


# =========================
# PROFIT DASHBOARD
# =========================
@login_required
@permission_required("inventory.view_profit_dashboard", raise_exception=True)
def profit_report(request):
    # Date filter from GET (optional)
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    # Base queryset (optionally filtered by date range)
    qs = SaleItem.objects
    if date_from:
        qs = qs.filter(sale__sale_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale__sale_date__date__lte=date_to)

    # Summary stats (all-time or filtered)
    total_revenue = qs.total_revenue()
    total_profit = qs.total_profit()
    today_profit = qs.today().total_profit()
    month_profit = qs.this_month().total_profit()
    today_revenue = qs.today().total_revenue()
    month_revenue = qs.this_month().total_revenue()

    today_margin = (today_profit / today_revenue * Decimal("100")) if today_revenue else Decimal("0.00")
    month_margin = (month_profit / month_revenue * Decimal("100")) if month_revenue else Decimal("0.00")

    # Explicit Calculation table variables
    gross_revenue = qs.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
    sale_ids = qs.values_list("sale_id", flat=True).distinct()
    total_discount = Sale.objects.filter(id__in=sale_ids).aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")
    total_cogs = qs.with_profit().aggregate(total=Sum("cost_total"))["total"] or Decimal("0.00")

    # Chart date range: use filter if set, else last 14 days
    start_date = date_from or (now().date() - timedelta(days=14))
    end_date = date_to or now().date()

    daily = (
        qs.filter(
            sale__sale_date__date__gte=start_date,
            sale__sale_date__date__lte=end_date,
        )
        .annotate(
            date=TruncDate("sale__sale_date"),
            item_profit=ExpressionWrapper(
                F("total_price") - F("cost_at_sale"),
                output_field=DecimalField(),
            ),
        )
        .values("date")
        .annotate(
            revenue=Sum("total_price"),
            profit=Sum("item_profit"),
        )
        .order_by("date")
    )
    # Build full date range (fill gaps with zeros)
    def _norm_date(dt):
        return dt.date() if hasattr(dt, "date") else dt

    num_days = max(1, (end_date - start_date).days + 1)
    date_labels = []
    revenue_data = []
    profit_data = []
    for i in range(min(num_days, 60)):  # cap at 60 days for chart
        d = start_date + timedelta(days=i)
        if d > end_date:
            break
        date_labels.append(d.strftime("%b %d"))
        row = next((x for x in daily if _norm_date(x["date"]) == d), None)
        revenue_data.append(float(row["revenue"]) if row and row["revenue"] else 0)
        profit_data.append(float(row["profit"]) if row and row["profit"] else 0)

    # Top products by revenue (filtered range or last 30 days)
    top_start = date_from or (now().date() - timedelta(days=30))
    top_end = date_to or now().date()
    top_products = (
        SaleItem.objects.filter(
            sale__sale_date__date__gte=top_start,
            sale__sale_date__date__lte=top_end,
        )
        .values("product__name")
        .annotate(revenue=Sum("total_price"), qty=Sum("quantity"))
        .order_by("-revenue")[:8]
    )
    top_product_names = [p["product__name"] or "Unknown" for p in top_products]
    top_product_revenue = [float(p["revenue"] or 0) for p in top_products]

    # Monthly comparison: this month vs last month (only when no date filter)
    dt = now()
    if not date_from and not date_to:
        this_month_rev = qs.this_month().total_revenue()
        last_month_start = (dt.replace(day=1) - timedelta(days=1)).replace(day=1)
        last_month_end = dt.replace(day=1) - timedelta(days=1)
        last_month_rev = (
            SaleItem.objects.filter(
                sale__sale_date__date__gte=last_month_start,
                sale__sale_date__date__lte=last_month_end,
            ).total_revenue()
        )
    else:
        this_month_rev = total_revenue
        last_month_rev = None

    context = {
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "today_profit": today_profit,
        "month_profit": month_profit,
        "today_revenue": today_revenue,
        "month_revenue": month_revenue,
        "today_margin": today_margin,
        "month_margin": month_margin,
        "date_labels": json.dumps(date_labels),
        "revenue_data": json.dumps(revenue_data),
        "profit_data": json.dumps(profit_data),
        "top_product_names": json.dumps(top_product_names),
        "top_product_revenue": json.dumps(top_product_revenue),
        "this_month_revenue": this_month_rev,
        "last_month_revenue": last_month_rev,
        "date_from": date_from_str or "",
        "date_to": date_to_str or "",
        "has_date_filter": bool(date_from or date_to),
        "gross_revenue": gross_revenue,
        "total_discount": total_discount,
        "net_revenue": max(Decimal("0.00"), gross_revenue - total_discount),
        "total_cogs": total_cogs,
    }

    return render(request, "inventory/profit_report.html", context)


# =========================
# LOW STOCK ALERTS
# =========================
@login_required
@permission_required("inventory.view_low_stock_alerts", raise_exception=True)
def low_stock_alerts(request):
    # Filters
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")

    base_qs = Product.objects.filter(stock_quantity__lte=F("minimum_stock"))

    if query:
        base_qs = base_qs.filter(name__icontains=query)

    if status == "out":
        base_qs = base_qs.filter(stock_quantity=0)
    elif status == "low":
        base_qs = base_qs.filter(stock_quantity__gt=0)

    from django.db.models import Prefetch
    from .models import PurchaseItem

    # Only get batches that have stock, ordered by expiry
    active_batches = PurchaseItem.objects.filter(current_stock__gt=0).order_by('expiry_date')
    
    products = base_qs.prefetch_related(
        Prefetch('purchase_items', queryset=active_batches, to_attr='active_batches')
    ).order_by("stock_quantity", "name")

    # Summary counts
    total_low = Product.objects.filter(stock_quantity__lte=F("minimum_stock")).count()
    out_of_stock = Product.objects.filter(stock_quantity=0).count()
    low_but_available = total_low - out_of_stock

    # Chart data for current filtered set
    labels = [p.name for p in products]
    stock_data = [p.stock_quantity for p in products]
    min_data = [p.minimum_stock for p in products]

    context = {
        "products": products,
        "search_query": query,
        "status": status,
        "has_filters": bool(query or status != "all"),
        "total_low": total_low,
        "out_of_stock": out_of_stock,
        "low_but_available": low_but_available,
        "chart_labels": json.dumps(labels),
        "chart_stock": json.dumps(stock_data),
        "chart_min": json.dumps(min_data),
    }

    return render(request, "inventory/low_stock_alerts.html", context)


@login_required
@permission_required("inventory.view_low_stock_alerts", raise_exception=True)
def expiry_report(request):
    """
    Shows items from PurchaseHistory that are nearing expiry or already expired.
    We only show items if the product itself still has stock globally.
    """
    today = date.today()
    thirty_days = today + timedelta(days=30)
    
    # Get purchase items that have an expiry date, and still have stock in that specific batch
    records = PurchaseItem.objects.filter(
        expiry_date__isnull=False,
        current_stock__gt=0
    ).select_related("product", "purchase__vendor").order_by("expiry_date")

    expired = []
    expiring_soon = []
    
    for r in records:
        if r.expiry_date < today:
            expired.append(r)
        elif r.expiry_date <= thirty_days:
            expiring_soon.append(r)

    context = {
        "expired": expired,
        "expiring_soon": expiring_soon,
    }
    return render(request, "inventory/expiry_report.html", context)


@login_required
@permission_required("inventory.view_profit_dashboard", raise_exception=True)
def discount_report(request):
    """
    Shows all sales that have a discount applied.
    """
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")

    discounted_sales = Sale.objects.filter(discount_amount__gt=0).prefetch_related("items", "user").order_by("-sale_date")

    try:
        if date_from_str:
            from_dt = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            discounted_sales = discounted_sales.filter(sale_date__date__gte=from_dt)
    except (ValueError, TypeError):
        date_from_str = None

    try:
        if date_to_str:
            to_dt = datetime.strptime(date_to_str, "%Y-%m-%d").date()
            discounted_sales = discounted_sales.filter(sale_date__date__lte=to_dt)
    except (ValueError, TypeError):
        date_to_str = None
    
    total_discounts_given = discounted_sales.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")
    
    context = {
        "date_from": date_from_str,
        "date_to": date_to_str,
        "total_discounts_given": total_discounts_given,
        "discounted_sales": discounted_sales,
    }

    return render(request, "inventory/discount_report.html", context)


@login_required
@permission_required("inventory.view_sale", raise_exception=True)
def sales_report(request):
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    
    qs = SaleItem.objects.all()
    sale_qs = Sale.objects.all()

    try:
        if date_from_str:
            from_dt = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            qs = qs.filter(sale__sale_date__date__gte=from_dt)
            sale_qs = sale_qs.filter(sale_date__date__gte=from_dt)
    except (ValueError, TypeError):
        date_from_str = None

    try:
        if date_to_str:
            to_dt = datetime.strptime(date_to_str, "%Y-%m-%d").date()
            qs = qs.filter(sale__sale_date__date__lte=to_dt)
            sale_qs = sale_qs.filter(sale_date__date__lte=to_dt)
    except (ValueError, TypeError):
        date_to_str = None

    total_gross_revenue = qs.aggregate(total=Sum('total_price'))['total'] or Decimal("0.00")
    total_items_sold = qs.aggregate(total=Sum('quantity'))['total'] or 0
    total_transactions = sale_qs.count()
    total_discounts = sale_qs.aggregate(total=Sum('discount_amount'))['total'] or Decimal("0.00")
    total_net_revenue = max(Decimal("0.00"), total_gross_revenue - total_discounts)
    
    product_sales = qs.values(
        'product__name'
    ).annotate(
        qty_sold=Sum('quantity'),
        gross_revenue=Sum('total_price')
    ).order_by('-gross_revenue')

    # Chart Data
    start_date = (date_from_str and datetime.strptime(date_from_str, "%Y-%m-%d").date()) or (now().date() - timedelta(days=14))
    end_date = (date_to_str and datetime.strptime(date_to_str, "%Y-%m-%d").date()) or now().date()
    
    daily_sales = (
        qs.filter(sale__sale_date__date__gte=start_date, sale__sale_date__date__lte=end_date)
        .annotate(date=TruncDate("sale__sale_date"))
        .values("date")
        .annotate(revenue=Sum("total_price"))
        .order_by("date")
    )
    
    num_days = max(1, (end_date - start_date).days + 1)
    sales_date_labels = []
    sales_revenue_data = []
    
    def _norm_date(dt):
        return dt.date() if hasattr(dt, "date") else dt

    for i in range(min(num_days, 60)):
        d = start_date + timedelta(days=i)
        if d > end_date:
            break
        sales_date_labels.append(d.strftime("%b %d"))
        row = next((x for x in daily_sales if _norm_date(x["date"]) == d), None)
        sales_revenue_data.append(float(row["revenue"]) if row and row["revenue"] else 0)

    context = {
        "date_from": date_from_str,
        "date_to": date_to_str,
        "total_gross_revenue": total_gross_revenue,
        "total_net_revenue": total_net_revenue,
        "total_items_sold": total_items_sold,
        "total_transactions": total_transactions,
        "total_discounts": total_discounts,
        "product_sales": product_sales,
        "sales_date_labels": json.dumps(sales_date_labels),
        "sales_revenue_data": json.dumps(sales_revenue_data),
    }
    return render(request, "inventory/sales_report.html", context)


@login_required
@permission_required("inventory.view_purchase", raise_exception=True)
def purchase_report(request):
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    
    qs = PurchaseItem.objects.all()

    try:
        if date_from_str:
            from_dt = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            qs = qs.filter(purchase__purchase_date__date__gte=from_dt)
    except (ValueError, TypeError):
        date_from_str = None

    try:
        if date_to_str:
            to_dt = datetime.strptime(date_to_str, "%Y-%m-%d").date()
            qs = qs.filter(purchase__purchase_date__date__lte=to_dt)
    except (ValueError, TypeError):
        date_to_str = None

    total_spend = qs.aggregate(total=Sum('total_cost'))['total'] or Decimal("0.00")
    total_items_bought = qs.aggregate(total=Sum('quantity'))['total'] or 0
    total_transactions = qs.values('purchase').distinct().count()
    
    product_purchases = qs.values(
        'product__name'
    ).annotate(
        qty_bought=Sum('quantity'),
        total_cost_sum=Sum('total_cost')
    ).order_by('-total_cost_sum')
    
    vendor_purchases = qs.values(
        'purchase__vendor__name'
    ).annotate(
        total_spent=Sum('total_cost'),
        transaction_count=Count('purchase', distinct=True)
    ).order_by('-total_spent')

    # Chart Data
    start_date = (date_from_str and datetime.strptime(date_from_str, "%Y-%m-%d").date()) or (now().date() - timedelta(days=14))
    end_date = (date_to_str and datetime.strptime(date_to_str, "%Y-%m-%d").date()) or now().date()
    
    daily_purchases = (
        qs.filter(purchase__purchase_date__date__gte=start_date, purchase__purchase_date__date__lte=end_date)
        .annotate(date=TruncDate("purchase__purchase_date"))
        .values("date")
        .annotate(spend=Sum("total_cost"))
        .order_by("date")
    )
    
    num_days = max(1, (end_date - start_date).days + 1)
    purchase_date_labels = []
    purchase_spend_data = []
    
    def _norm_date(dt):
        return dt.date() if hasattr(dt, "date") else dt

    for i in range(min(num_days, 60)):
        d = start_date + timedelta(days=i)
        if d > end_date:
            break
        purchase_date_labels.append(d.strftime("%b %d"))
        row = next((x for x in daily_purchases if _norm_date(x["date"]) == d), None)
        purchase_spend_data.append(float(row["spend"]) if row and row["spend"] else 0)

    context = {
        "date_from": date_from_str,
        "date_to": date_to_str,
        "total_spend": total_spend,
        "total_items_bought": total_items_bought,
        "total_transactions": total_transactions,
        "product_purchases": product_purchases,
        "vendor_purchases": vendor_purchases,
        "purchase_date_labels": json.dumps(purchase_date_labels),
        "purchase_spend_data": json.dumps(purchase_spend_data),
    }
    return render(request, "inventory/purchase_report.html", context)

# =========================
# SALES WORKFLOW (STAFF)
# =========================
@login_required
@permission_required("inventory.add_sale", raise_exception=True)
def sale_list(request):
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")

    sales = Sale.objects.prefetch_related("items").order_by("-sale_date")

    try:
        if date_from_str:
            from_dt = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            sales = sales.filter(sale_date__date__gte=from_dt)
    except (ValueError, TypeError):
        date_from_str = None

    try:
        if date_to_str:
            to_dt = datetime.strptime(date_to_str, "%Y-%m-%d").date()
            sales = sales.filter(sale_date__date__lte=to_dt)
    except (ValueError, TypeError):
        date_to_str = None

    context = {
        "sales": sales,
        "date_from": date_from_str,
        "date_to": date_to_str,
    }
    return render(request, "inventory/sale_list.html", context)

@login_required
@permission_required("inventory.add_sale", raise_exception=True)
def create_sale(request):
    products = Product.objects.all().order_by("name")

    available_stock_map = {}
    for product in products:
        batch_stock = (
            product.purchase_items.filter(current_stock__gt=0).aggregate(total=Sum("current_stock"))["total"] or 0
        )
        # If legacy products have opening stock but no batches, allow sales from global stock.
        effective_stock = batch_stock if batch_stock > 0 else product.stock_quantity
        available_stock_map[product.id] = effective_stock
        product.available_stock = effective_stock
        product.batch_stock = batch_stock
        product.is_available_for_sale = effective_stock > 0

    has_available_products = any(p.is_available_for_sale for p in products)

    if request.method == "POST":
        try:
            with transaction.atomic():
                product_ids = request.POST.getlist("product")
                quantities = request.POST.getlist("quantity")

                line_items = []
                for pid, qty_str in zip(product_ids, quantities):
                    if not pid or not qty_str:
                        continue
                    try:
                        qty = int(qty_str)
                    except (TypeError, ValueError):
                        raise ValidationError("Quantity must be a positive integer.")
                    if qty <= 0:
                        raise ValidationError("Quantity must be at least 1.")
                    line_items.append((pid, qty))

                if not line_items:
                    raise ValidationError("Please add at least one product.")

                discount_amount_str = request.POST.get("discount_amount", "0").strip()
                if not discount_amount_str:
                    discount_amount_str = "0"
                try:
                    discount_amount = Decimal(discount_amount_str)
                except (InvalidOperation, ValueError, TypeError):
                    raise ValidationError("Discount amount must be a valid number.")

                if discount_amount < Decimal("0.00"):
                    raise ValidationError("Discount cannot be negative.")

                discount_authorized_by = request.POST.get("discount_authorized_by", "").strip()
                if discount_amount > Decimal("0.00") and not discount_authorized_by:
                    raise ValidationError("Discount requires an authorizing manager's name.")

                sale = Sale.objects.create(
                    user=request.user,
                    discount_amount=discount_amount,
                    discount_authorized_by=discount_authorized_by
                )

                for pid, qty in line_items:
                    product = Product.objects.filter(id=pid).first()
                    if not product:
                        raise ValidationError("One or more selected products are invalid.")
                    SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=qty,
                    )
                
                messages.success(request, f"Sale recorded successfully with {len(line_items)} item(s)!")
            return redirect("sale_list")

        except ValidationError as e:
            # Handle both field and non-field validation errors
            message = None
            if hasattr(e, "message_dict"):
                message = list(e.message_dict.values())[0][0]
            elif hasattr(e, "message"):
                message = e.message
            else:
                message = str(e)

            return render(request, "inventory/create_sale.html", {
                "products": products,
                "available_stock_map": available_stock_map,
                "has_available_products": has_available_products,
                "form_error": message,
            })

        except Exception as e:
            return render(request, "inventory/create_sale.html", {
                "products": products,
                "available_stock_map": available_stock_map,
                "has_available_products": has_available_products,
                "form_error": str(e)
            })

    return render(request, "inventory/create_sale.html", {
        "products": products,
        "available_stock_map": available_stock_map,
        "has_available_products": has_available_products,
    })


# =========================
# SALE SUCCESS
# =========================

# =========================
# VENDORS
# =========================
@login_required
@permission_required("inventory.add_vendor", raise_exception=True)
def vendor_list(request):
    vendors = Vendor.objects.all().order_by("name")
    return render(request, "inventory/vendor_list.html", {"vendors": vendors})

@login_required
@permission_required("inventory.add_vendor", raise_exception=True)
def vendor_create(request):
    if request.method == "POST":
        form = VendorForm(request.POST)
        if form.is_valid():
            vendor = form.save()
            messages.success(request, f"Vendor '{vendor.name}' created successfully!")
            return redirect("vendor_list")
    else:
        form = VendorForm()
    return render(request, "inventory/vendor_form.html", {"form": form})

@login_required
@permission_required("inventory.change_vendor", raise_exception=True)
def vendor_edit(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if request.method == "POST":
        form = VendorForm(request.POST, instance=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, f"Vendor {vendor.name} updated.")
            return redirect("vendor_list")
    else:
        form = VendorForm(instance=vendor)
    return render(request, "inventory/vendor_form.html", {"form": form, "is_edit": True, "vendor": vendor})

@login_required
@permission_required("inventory.delete_vendor", raise_exception=True)
def vendor_delete(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    
    # Check for existing purchases
    if Purchase.objects.filter(vendor=vendor).exists():
        messages.error(request, f"Cannot delete vendor '{vendor.name}' because there are existing purchases linked to it.")
        return redirect("vendor_list")
        
    if request.method == "POST":
        name = vendor.name
        vendor.delete()
        messages.success(request, f"Vendor {name} deleted.")
        return redirect("vendor_list")
        
    return render(request, "inventory/vendor_confirm_delete.html", {"vendor_to_delete": vendor})

# =========================
# PRODUCTS
# =========================
@login_required
@permission_required("inventory.add_product", raise_exception=True)
def product_list(request):
    products = Product.objects.all().order_by("name")
    return render(request, "inventory/product_list.html", {"products": products})

@login_required
@permission_required("inventory.add_product", raise_exception=True)
def product_create(request):
    if request.method == "POST":
        try:
            with transaction.atomic():
                names = request.POST.getlist("name")
                skus = request.POST.getlist("sku")
                descriptions = request.POST.getlist("description")
                cost_prices = request.POST.getlist("cost_price")
                selling_prices = request.POST.getlist("selling_price")
                stock_quantities = request.POST.getlist("stock_quantity")
                minimum_stocks = request.POST.getlist("minimum_stock")
                shelf_lives = request.POST.getlist("shelf_life_days")

                created_count = 0

                for idx in range(len(names)):
                    name = names[idx].strip()
                    if not name:
                        continue # Skip empty rows

                    sku = skus[idx].strip() if idx < len(skus) else ""
                    desc = descriptions[idx].strip() if idx < len(descriptions) else ""
                    
                    try:
                        cost = Decimal(cost_prices[idx] or "0")
                        sell = Decimal(selling_prices[idx] or "0")
                        stock = int(stock_quantities[idx] or "0")
                        min_stock = int(minimum_stocks[idx] or "10")
                        shelf = int(shelf_lives[idx] or "0")
                    except (ValueError, TypeError, IndexError, InvalidOperation):
                        raise ValidationError(f"Invalid numeric values for product: {name}")

                    if cost < 0 or sell < 0 or stock < 0 or min_stock < 0 or shelf < 0:
                        raise ValidationError(f"Numeric values cannot be negative for product: {name}")

                    if sell < cost:
                        raise ValidationError(f"Selling price cannot be lower than cost price for product: {name}")

                    prod = Product(
                        name=name,
                        sku=sku if sku else None,
                        description=desc,
                        cost_price=cost,
                        selling_price=sell,
                        stock_quantity=stock,
                        minimum_stock=min_stock,
                        shelf_life_days=shelf
                    )
                    prod.save()
                    created_count += 1
                
                if created_count == 0:
                    raise ValidationError("Please enter at least one valid product name.")
                
                messages.success(request, f"Successfully created {created_count} product{'s' if created_count != 1 else ''}!")
            return redirect("product_list")

        except ValidationError as e:
            message = list(e.message_dict.values())[0][0] if hasattr(e, "message_dict") else str(e.message) if hasattr(e, "message") else str(e)
            return render(request, "inventory/product_form.html", {"form_error": message})
        except Exception as e:
            return render(request, "inventory/product_form.html", {"form_error": str(e)})

    return render(request, "inventory/product_form.html")

@login_required
@permission_required("inventory.change_product", raise_exception=True)
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Product {product.name} updated.")
            return redirect("product_list")
        else:
            # Form has errors, render with errors visible
            return render(request, "inventory/product_edit.html", {"form": form, "is_edit": True, "product": product, "has_errors": True})
    else:
        form = ProductEditForm(instance=product)
    return render(request, "inventory/product_edit.html", {"form": form, "is_edit": True, "product": product})

@login_required
@permission_required("inventory.delete_product", raise_exception=True)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    
    # Check for existing transactions
    from .models import SaleItem, PurchaseItem
    has_transactions = SaleItem.objects.filter(product=product).exists() or PurchaseItem.objects.filter(product=product).exists()
    
    if has_transactions:
        messages.error(request, f"Cannot delete product '{product.name}' because there are existing sales or purchases linked to it.")
        return redirect("product_list")
        
    if request.method == "POST":
        name = product.name
        product.delete()
        messages.success(request, f"Product {name} deleted.")
        return redirect("product_list")
        
    return render(request, "inventory/product_confirm_delete.html", {"product_to_delete": product})

# =========================
# PURCHASES
# =========================
@login_required
@permission_required("inventory.add_purchase", raise_exception=True)
def purchase_list(request):
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")

    purchases = Purchase.objects.all().order_by("-purchase_date")

    try:
        if date_from_str:
            from_dt = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            purchases = purchases.filter(purchase_date__date__gte=from_dt)
    except (ValueError, TypeError):
        date_from_str = None

    try:
        if date_to_str:
            to_dt = datetime.strptime(date_to_str, "%Y-%m-%d").date()
            purchases = purchases.filter(purchase_date__date__lte=to_dt)
    except (ValueError, TypeError):
        date_to_str = None

    context = {
        "purchases": purchases,
        "date_from": date_from_str,
        "date_to": date_to_str,
    }
    return render(request, "inventory/purchase_list.html", context)

@login_required
@permission_required("inventory.add_purchase", raise_exception=True)
def purchase_create(request):
    vendors = Vendor.objects.all()
    products = Product.objects.all()

    if request.method == "POST":
        try:
            with transaction.atomic():
                vendor_id = request.POST.get("vendor")
                if not vendor_id:
                    raise ValidationError("Please select a vendor.")
                
                vendor = Vendor.objects.filter(id=vendor_id).first()
                if not vendor:
                    raise ValidationError("Selected vendor does not exist.")

                product_ids = request.POST.getlist("product")
                quantities = request.POST.getlist("quantity")
                cost_prices = request.POST.getlist("cost_price")
                mfg_dates = request.POST.getlist("manufacture_date")
                exp_dates = request.POST.getlist("expiry_date")
                batch_numbers = request.POST.getlist("batch_number")

                line_items = []
                for idx in range(len(product_ids)):
                    pid = product_ids[idx]
                    qty_str = quantities[idx]
                    cost_str = cost_prices[idx]
                    mfg_str = mfg_dates[idx] if idx < len(mfg_dates) else ""
                    exp_str = exp_dates[idx] if idx < len(exp_dates) else ""
                    batch_num = batch_numbers[idx] if idx < len(batch_numbers) else ""

                    if not pid or not qty_str or not cost_str:
                        continue

                    try:
                        qty = int(qty_str)
                        cost = Decimal(cost_str)
                    except (TypeError, ValueError):
                        raise ValidationError("Quantity and Cost Price must be valid numbers.")
                    
                    if qty <= 0 or cost < 0:
                        raise ValidationError("Quantity must be > 0 and Cost Price must be >= 0.")
                    
                    mfg_dt = datetime.strptime(mfg_str, "%Y-%m-%d").date() if mfg_str else None
                    exp_dt = datetime.strptime(exp_str, "%Y-%m-%d").date() if exp_str else None

                    line_items.append({
                        "product_id": pid,
                        "quantity": qty,
                        "cost": cost,
                        "mfg": mfg_dt,
                        "exp": exp_dt,
                        "batch": batch_num
                    })

                if not line_items:
                    raise ValidationError("Please add at least one valid product line.")

                purchase = Purchase.objects.create(vendor=vendor, user=request.user)

                for item in line_items:
                    product = Product.objects.filter(id=item["product_id"]).first()
                    if not product:
                        raise ValidationError("One or more selected products are invalid.")
                    PurchaseItem.objects.create(
                        purchase=purchase,
                        product=product,
                        quantity=item["quantity"],
                        cost_price=item["cost"],
                        manufacture_date=item["mfg"],
                        expiry_date=item["exp"],
                        batch_number=item["batch"]
                    )
                
                messages.success(request, f"Purchase created successfully with {len(line_items)} item(s)!")
            return redirect("purchase_list")

        except ValidationError as e:
            message = list(e.message_dict.values())[0][0] if hasattr(e, "message_dict") else str(e.message) if hasattr(e, "message") else str(e)
            return render(request, "inventory/purchase_form.html", {"vendors": vendors, "products": products, "form_error": message})
        except Exception as e:
            return render(request, "inventory/purchase_form.html", {"vendors": vendors, "products": products, "form_error": str(e)})

    return render(request, "inventory/purchase_form.html", {
        "vendors": vendors,
        "products": products,
    })

# =========================
# STOCK ADJUSTMENTS
# =========================
@login_required
@permission_required("inventory.add_stockadjustment", raise_exception=True)
def stock_adjustment_list(request):
    adjustments = StockAdjustment.objects.all().order_by("-created_at")
    return render(request, "inventory/stock_adjustment_list.html", {"adjustments": adjustments})

@login_required
@permission_required("inventory.add_stockadjustment", raise_exception=True)
def stock_adjustment_create(request):
    if request.method == "POST":
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            try:
                adjustment = form.save(commit=False)
                adjustment.user = request.user
                adjustment.save() # model logic validates/updates stock
                messages.success(request, f"Stock adjustment recorded successfully!")
                return redirect("stock_adjustment_list")
            except ValidationError as e:
                form.add_error(None, e)
    else:
        form = StockAdjustmentForm()
    
    return render(request, "inventory/stock_adjustment_form.html", {"form": form})
@login_required
@permission_required('inventory.change_alertsettings', raise_exception=True)
def alert_settings(request):
    settings_obj = AlertSettings.get_settings()
    if request.method == "POST":
        form = AlertSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            
            # Reschedule the background job
            try:
                from inventory import scheduler
                scheduler.start() # This calls scheduler.start() which has replace_existing=True
                messages.success(request, "Alert settings updated and scheduler restarted.")
            except Exception as e:
                messages.error(request, f"Settings saved but scheduler failed to restart: {e}")
                
            return redirect('alert_settings')
    else:
        form = AlertSettingsForm(instance=settings_obj)
    
    return render(request, 'inventory/alert_settings.html', {
        'form': form,
        'settings': settings_obj
    })

@login_required
@permission_required('inventory.change_alertsettings', raise_exception=True)
def test_email_alert(request):
    from inventory.cron import check_stock_and_expiry
    
    # Send email in background so the user doesn't wait for 2-3 mins 
    thread = threading.Thread(target=check_stock_and_expiry, daemon=True)
    thread.start()
    
    messages.success(request, "Test alert triggered in the background! You should receive it shortly without the page waiting.")
    return redirect('alert_settings')


# =========================
# USER MANAGEMENT (ADMIN ONLY)
# =========================

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_list(request):
    users = User.objects.all().order_by('-is_superuser', 'username')
    return render(request, "inventory/user_list.html", {"users": users})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_create(request):
    # Ensure groups exist
    setup_user_groups()
    
    if request.method == "POST":
        form = AppUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data.get("role")
            
            # Assign to group
            group = Group.objects.get(name=role)
            user.groups.add(group)
            
            # Also set is_staff for both Staff and Manager
            user.is_staff = True
            user.save()
            
            messages.success(request, f"User {user.username} created successfully as {role}.")
            return redirect("user_list")
    else:
        form = AppUserCreationForm()
        
    return render(request, "inventory/user_form.html", {"form": form})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = AppUserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data.get("role")
            new_password = form.cleaned_data.get("new_password")
            
            # Update role group
            user.groups.clear()
            group = Group.objects.get(name=role)
            user.groups.add(group)

            # Handle password change
            if new_password:
                user.set_password(new_password)
                user.save()
                # If editing yourself, keep the session valid
                if user == request.user:
                    update_session_auth_hash(request, user)
            
            messages.success(request, f"User {user.username} updated successfully.")
            return redirect("user_list")
    else:
        form = AppUserUpdateForm(instance=user)
    
    return render(request, "inventory/user_form.html", {
        "form": form,
        "is_edit": True,
        "edit_user": user
    })

@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    
    # Prevent self-deletion
    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect("user_list")
        
    if request.method == "POST":
        username = user.username
        user.delete()
        messages.success(request, f"User {username} deleted successfully.")
        return redirect("user_list")
        
    return render(request, "inventory/user_confirm_delete.html", {"user_to_delete": user})


# =========================
# FORECASTING VIEWS
# =========================

@login_required
@permission_required("inventory.view_product", raise_exception=True)
def forecast_dashboard(request):
    """
    Overview of all products that have an active forecast.
    """
    forecasts = DemandForecast.objects.select_related("product").values(
        "product__id", "product__name"
    ).distinct()
    
    return render(request, "inventory/forecast_dashboard.html", {
        "forecast_products": forecasts
    })

@login_required
@permission_required("inventory.view_product", raise_exception=True)
def product_forecast_detail(request, pk):
    """
    Detailed forecast view for a single product with Plotly chart data.
    """
    product = get_object_or_404(Product, pk=pk)
    forecast_qs = DemandForecast.objects.filter(product=product).order_by("date")

    if request.method == "POST":
        def _generate_forecast():
            from .forecasting import run_forecast_for_product, ingest_excel_history
            excel_path = Path(settings.BASE_DIR) / "Online Retail.xlsx"
            excel_df = ingest_excel_history(excel_path) if excel_path.exists() else None
            run_forecast_for_product(product.id, excel_df)

        generation_thread = threading.Thread(target=_generate_forecast, daemon=True)
        generation_thread.start()
        messages.success(request, f"Forecast generation started for {product.name}. Refresh in a moment to see the result.")
        return redirect("product_forecast_detail", pk=product.pk)

    # Historical data for the chart (last 30 days)
    history_cutoff = now() - timedelta(days=60)
    history_qs = SaleItem.objects.filter(
        product=product, 
        sale__sale_date__gte=history_cutoff
    ).values("sale__sale_date").annotate(qty=Sum("quantity")).order_by("sale__sale_date")

    # Map to JSON for Plotly
    hist_x = [h["sale__sale_date"].strftime("%Y-%m-%d") for h in history_qs]
    hist_y = [h["qty"] for h in history_qs]

    forecast_ready = forecast_qs.exists()
    forecast_rows = list(forecast_qs) if forecast_ready else []

    display_dates = [f.date for f in forecast_rows]
    if display_dates:
        latest_forecast_date = max(display_dates)
        today_date = now().date()
        if (today_date - latest_forecast_date).days > 30:
            shift_days = (today_date - latest_forecast_date).days
            display_dates = [d + timedelta(days=shift_days) for d in display_dates]

    fore_x = [d.strftime("%Y-%m-%d") for d in display_dates]
    fore_y = [float(f.predicted_quantity) for f in forecast_rows]
    fore_y_upper = [float(f.upper_bound) for f in forecast_rows]
    fore_y_lower = [float(f.lower_bound) for f in forecast_rows]

    weekly_breakdown = []
    for week_no in range(1, 5):
        start_idx = (week_no - 1) * 7
        end_idx = start_idx + 7
        week_rows = forecast_rows[start_idx:end_idx]

        if week_rows:
            week_total = sum(float(row.predicted_quantity) for row in week_rows)
            start_date = display_dates[start_idx].strftime("%b %d")
            end_date = display_dates[min(end_idx, len(display_dates)) - 1].strftime("%b %d")
        else:
            week_total = 0.0
            start_date = "-"
            end_date = "-"

        weekly_breakdown.append(
            {
                "label": f"Week {week_no}",
                "total": week_total,
                "range": f"{start_date} - {end_date}",
            }
        )

    month_rows = forecast_rows[:30]
    month_total = sum(float(row.predicted_quantity) for row in month_rows) if month_rows else 0.0
    month_range = (
        f"{display_dates[0].strftime('%b %d')} - {display_dates[min(len(display_dates), 30) - 1].strftime('%b %d')}"
        if month_rows
        else "-"
    )

    # Smart Reorder Suggestion
    reorder_quantity = int(month_total - product.stock_quantity)
    if reorder_quantity <= 0:
        reorder_status = "good"
        reorder_message = "You're well-stocked! No reorder needed."
    else:
        reorder_status = "action_needed"
        reorder_message = f"Suggested reorder: {reorder_quantity} units"

    context = {
        "product": product,
        "hist_x": json.dumps(hist_x),
        "hist_y": json.dumps(hist_y),
        "fore_x": json.dumps(fore_x),
        "fore_y": json.dumps(fore_y),
        "fore_y_upper": json.dumps(fore_y_upper),
        "fore_y_lower": json.dumps(fore_y_lower),
        "forecast_ready": forecast_ready,
        "forecast_count": len(forecast_rows),
        "weekly_breakdown": weekly_breakdown,
        "month_total": month_total,
        "month_range": month_range,
        "reorder_quantity": reorder_quantity,
        "reorder_status": reorder_status,
        "reorder_message": reorder_message,
    }
    
    return render(request, "inventory/forecast_detail.html", context)


@login_required
@permission_required("inventory.view_product", raise_exception=True)
def forecast_accuracy_report(request):
    messages.info(request, "Model accuracy report is hidden for this demo build.")
    return redirect("forecast_dashboard")

    report_path = Path(settings.BASE_DIR) / "presentation_artifacts" / "accuracy_report.csv"

    if request.method == "POST":
        script_path = Path(settings.BASE_DIR) / "prophet_presentation_accuracy.py"
        if not script_path.exists():
            messages.error(request, "Accuracy generator script was not found.")
        else:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(settings.BASE_DIR),
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                messages.success(request, "Forecast accuracy report generated successfully.")
            else:
                messages.error(request, completed.stderr.strip() or "Failed to generate the accuracy report.")

        return redirect("forecast_accuracy_report")

    rows = []

    if report_path.exists():
        with report_path.open(newline="", encoding="utf-8") as report_file:
            reader = csv.DictReader(report_file)
            for row in reader:
                try:
                    mape_value = row.get("mape_percent", "")
                    rows.append(
                        {
                            "sku": (row.get("sku") or "").strip(),
                            "product_name": (row.get("product_name") or "").strip(),
                            "points_compared": int(float(row.get("points_compared") or 0)),
                            "mae": float(row.get("mae") or 0),
                            "rmse": float(row.get("rmse") or 0),
                            "mape_percent": float(mape_value) if mape_value not in ("", None) else None,
                        }
                    )
                except (TypeError, ValueError):
                    continue

    for row in rows:
        row["mape_has_value"] = row["mape_percent"] is not None
        row["mape_display"] = f"{row['mape_percent']:.2f}%" if row["mape_has_value"] else "N/A"

    rows.sort(key=lambda item: (item["mape_percent"] is None, item["mape_percent"] or 0))

    total_models = len(rows)
    average_mae = round(sum(row["mae"] for row in rows) / total_models, 2) if rows else None
    average_rmse = round(sum(row["rmse"] for row in rows) / total_models, 2) if rows else None
    valid_mape_rows = [row for row in rows if row["mape_percent"] is not None]
    average_mape = round(sum(row["mape_percent"] for row in valid_mape_rows) / len(valid_mape_rows), 2) if valid_mape_rows else None

    average_mae_display = f"{average_mae:.2f}" if average_mae is not None else "N/A"
    average_rmse_display = f"{average_rmse:.2f}" if average_rmse is not None else "N/A"
    average_mape_display = f"{average_mape:.2f}%" if average_mape is not None else "N/A"

    context = {
        "report_available": report_path.exists(),
        "report_path": str(report_path),
        "rows": rows,
        "total_models": total_models,
        "average_mae": average_mae,
        "average_rmse": average_rmse,
        "average_mape": average_mape,
        "average_mae_display": average_mae_display,
        "average_rmse_display": average_rmse_display,
        "average_mape_display": average_mape_display,
        "best_row": rows[0] if rows else None,
        "worst_row": rows[-1] if rows else None,
        "chart_labels": json.dumps([f"{row['sku']} - {row['product_name']}" for row in rows]),
        "chart_mape": json.dumps([row["mape_percent"] or 0 for row in rows]),
    }

    return render(request, "inventory/forecast_accuracy_report.html", context)
