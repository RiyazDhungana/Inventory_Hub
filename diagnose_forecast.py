#!/usr/bin/env python
"""Diagnostic: Check forecasting data and quality"""
import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

from inventory.models import Product, DemandForecast, SaleItem
from inventory.forecasting import run_forecast_for_product, ingest_excel_history
from django.conf import settings

excel_path = os.path.join(settings.BASE_DIR, 'Online Retail.xlsx')
excel_df = ingest_excel_history(excel_path) if os.path.exists(excel_path) else None

print("="*80)
print("FORECASTING DIAGNOSTIC")
print("="*80)

# Check products with forecasts
products_with_forecasts = DemandForecast.objects.values('product_id').distinct()
print(f"\n✅ Products with existing forecasts: {products_with_forecasts.count()}")

# Check a trained product
trained_products = Product.objects.filter(shelf_life_days__in=[0, 180, 365])[:3]

for product in trained_products:
    print(f"\n{'='*80}")
    print(f"Product: {product.name} (ID: {product.id})")
    print(f"SKU: {product.sku}")
    print(f"Stock: {product.stock_quantity}")
    
    # Check historical sales from this system
    sales = SaleItem.objects.filter(product=product)
    print(f"Sales in this system: {sales.count()} items")
    
    # Check Excel historical data
    if excel_df is not None and product.sku:
        excel_sales = excel_df[excel_df['product_id'] == str(product.sku)]
        print(f"Sales in Excel dataset: {len(excel_sales)} records ({int(excel_sales['quantity'].sum())} units)")
    
    # Check if forecast exists
    forecasts = DemandForecast.objects.filter(product=product)
    print(f"Forecasts in DB: {forecasts.count()}")
    
    if forecasts.count() > 0:
        latest = forecasts.latest('date')
        earliest = forecasts.earliest('date')
        print(f"  Forecast range: {earliest.date} to {latest.date}")
        print(f"  Sample prediction: {forecasts.first().predicted_quantity} units on {forecasts.first().date}")
    else:
        print(f"  ❌ NO FORECASTS - Generating now...")
        result = run_forecast_for_product(product.id, excel_df)
        if result:
            forecasts = DemandForecast.objects.filter(product=product)
            print(f"  ✅ Generated {forecasts.count()} forecasts")
            print(f"  Sample: {forecasts.first().predicted_quantity} units on {forecasts.first().date}")
        else:
            print(f"  ❌ FORECAST GENERATION FAILED - insufficient data?")

print(f"\n{'='*80}")
print("Diagnosis complete!")
