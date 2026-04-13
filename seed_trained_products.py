#!/usr/bin/env python
"""Seed top products from Online Retail.xlsx into database with realistic shelf life."""
import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

import pandas as pd
from inventory.models import Product

excel_path = r'c:\Users\PREDATOR\inventory_hub\Online Retail.xlsx'
df = pd.read_excel(excel_path)

top_products = df.groupby('Description')['Quantity'].sum().nlargest(20)

def get_shelf_life(product_name):
    """Assign realistic shelf life based on product type"""
    name_lower = product_name.lower()
    if any(w in name_lower for w in ['tea', 'coffee', 'chocolate', 'biscuit', 'cake', 'cosy']):
        return 180
    if any(w in name_lower for w in ['warmer', 'hottie']):
        return 365
    return 0

added = 0
for i, (product_name, total_qty) in enumerate(top_products.items(), 1):
    if Product.objects.filter(name=product_name).exists():
        print(f"⏭️  {i}. {product_name} - EXISTS")
        continue
    
    sku = str(df[df['Description'] == product_name]['StockCode'].iloc[0])
    if Product.objects.filter(sku=sku).exists():
        print(f"⏭️  {i}. {product_name} - SKU IN USE")
        continue
    
    price = df[df['Description'] == product_name]['UnitPrice'].mean()
    cost = Decimal(str(round(price * 0.5, 2)))
    sell = Decimal(str(round(price, 2)))
    shelf = get_shelf_life(product_name)
    
    Product.objects.create(
        name=product_name, sku=sku, cost_price=cost,
        selling_price=sell, stock_quantity=50, minimum_stock=5,
        shelf_life_days=shelf,
        description=f"Trained product. {int(total_qty)} units sold historically."
    )
    print(f"✅ {i}. {product_name} | SKU: {sku} | Shelf life: {shelf} days")
    added += 1

print(f"\n✨ Added {added} products ready for forecasting!")
