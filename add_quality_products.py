#!/usr/bin/env python
"""Find high-quality products for forecasting from Excel"""
import os
import django
import pandas as pd
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

from django.conf import settings
from inventory.models import Product

excel_path = os.path.join(settings.BASE_DIR, 'Online Retail.xlsx')
df = pd.read_excel(excel_path)

# Find products with LOTS of sales (good for Prophet)
product_sales = df.groupby('StockCode').agg({
    'Quantity': 'sum',
    'Description': 'first',
    'UnitPrice': 'mean'
}).reset_index()

product_sales = product_sales[product_sales['Quantity'] > 1000].sort_values('Quantity', ascending=False)

print("="*80)
print("TOP 20 PRODUCTS WITH BEST HISTORICAL DATA (>1000 units)")
print("="*80)
print(f"\nTotal products with 1000+ units: {len(product_sales)}")

# Skip top 15 that already exist, go for next best ones
high_quality = product_sales.iloc[15:35]

added = 0
for idx, row in high_quality.iterrows():
    sku = str(row['StockCode'])
    name = row['Description']
    qty = int(row['Quantity'])
    price_gbp = Decimal(str(row['UnitPrice']))
    
    # Check if already exists
    if Product.objects.filter(sku=sku).exists():
        print(f"⏭️  SKU {sku} - EXISTS")
        continue
    
    # Convert to NPR (1 GBP = 150 NPR)
    sell_npr = price_gbp * Decimal('150')
    cost_npr = sell_npr * Decimal('0.5')  # Cost is 50% of selling price
    
    # Ensure prices don't exceed max_digits=10
    if sell_npr > Decimal('9999999.99') or cost_npr > Decimal('9999999.99'):
        print(f"⏭️  {name} - PRICE TOO HIGH (cap at 9999999.99)")
        continue
    
    product = Product.objects.create(
        name=name,
        sku=sku,
        cost_price=cost_npr,
        selling_price=sell_npr,
        stock_quantity=100,
        minimum_stock=10,
        shelf_life_days=0,
        description=f"High-volume: {qty} units sold. Perfect for forecasting!"
    )
    
    print(f"✅ {name}")
    print(f"   SKU: {sku} | Sales: {qty} units | Price: Rs {sell_npr}")
    added += 1

print(f"\n{'='*80}")
print(f"✨ Added {added} high-quality forecast products!")
print(f"These have 1000+ historical sales - Prophet forecasting will work!")
