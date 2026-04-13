#!/usr/bin/env python
"""Convert product prices from GBP to NPR (1 GBP = 150 NPR)"""
import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

from inventory.models import Product

GBP_TO_NPR = Decimal('150')  # Exchange rate

# Get all products with prices < 100 (likely the UK-sourced ones)
products = Product.objects.filter(selling_price__lt=100)

updated = 0
for product in products:
    old_cost = product.cost_price
    old_price = product.selling_price
    
    # Convert to NPR
    new_cost = old_cost * GBP_TO_NPR
    new_price = old_price * GBP_TO_NPR
    
    # Update
    product.cost_price = new_cost
    product.selling_price = new_price
    product.save(skip_stock_validation=True)
    
    print(f"✅ {product.name}")
    print(f"   Cost: £{old_cost} → Rs {new_cost}")
    print(f"   Price: £{old_price} → Rs {new_price}")
    updated += 1

print(f"\n{'='*80}")
print(f"✨ Updated {updated} products to NPR currency!")
print(f"Exchange rate used: 1 GBP = 150 NPR")
