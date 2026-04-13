#!/usr/bin/env python
"""Check Excel SKU data and create matching sample sales to bootstrap forecasting"""
import os
import django
from decimal import Decimal
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

import pandas as pd
from django.conf import settings
from inventory.models import Product, Sale, SaleItem

excel_path = os.path.join(settings.BASE_DIR, 'Online Retail.xlsx')
df = pd.read_excel(excel_path)

print("="*80)
print("EXCEL SKU ANALYSIS")
print("="*80)

# Get unique SKUs from Excel
excel_skus = df['StockCode'].unique()
print(f"\nTotal unique SKUs in Excel: {len(excel_skus)}")

# Get products we just added
products = Product.objects.filter(shelf_life_days__in=[0, 180, 365])
print(f"Products in DB: {products.count()}")

print("\nMatching Analysis:")
matched = 0
for product in products[:5]:
    sku_in_excel = str(product.sku) in df['StockCode'].values
    sales_qty = df[df['StockCode'] == str(product.sku)]['Quantity'].sum() if sku_in_excel else 0
    
    status = "✅" if sku_in_excel else "❌"
    print(f"{status} {product.name}: SKU {product.sku}")
    if sku_in_excel:
        print(f"   → Found in Excel: {int(sales_qty)} units sold historically")
        matched += 1
    else:
        print(f"   → NOT in Excel dataset")

print(f"\n{matched}/{min(5, products.count())} products found in Excel")

# Create test sales data to bootstrap forecasting
print("\n" + "="*80)
print("CREATING TEST SALES DATA (to bootstrap Prophet)")
print("="*80)

# Get a product that's in the Excel data
test_product = None
for product in products:
    if str(product.sku) in df['StockCode'].values:
        test_product = product
        break

if test_product:
    print(f"\nUsing product: {test_product.name} (SKU: {test_product.sku})")
    excel_data = df[df['StockCode'] == str(test_product.sku)]
    print(f"Historical sales: {int(excel_data['Quantity'].sum())} units")
    
    # Create a user for test sales
    from django.contrib.auth.models import User
    user, _ = User.objects.get_or_create(username='forecast_test', defaults={'is_staff': True})
    
    # Create 30 days of test sales based on typical daily volumes
    daily_sales = int(excel_data['Quantity'].sum() / 365)  # Rough daily average
    
    start_date = datetime.now() - timedelta(days=30)
    created_sales = 0
    
    for day in range(30):
        sale_date = start_date + timedelta(days=day)
        # Create 1-3 sales per day
        for _ in range(min(2, max(1, daily_sales // 50))):
            sale = Sale.objects.create(user=user)
            SaleItem.objects.create(
                sale=sale,
                product=test_product,
                quantity=max(1, daily_sales // 5)
            )
            created_sales += 1
    
    print(f"✅ Created {created_sales} test sales records over 30 days")
    print(f"   Now try forecasting for: {test_product.name}")
else:
    print("⚠️  No products found matching Excel data")
    print("   The issue is SKU mismatch - products need matching SKU from Excel")
