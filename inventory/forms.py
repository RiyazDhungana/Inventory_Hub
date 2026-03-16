from django import forms
from .models import Vendor, Purchase, PurchaseItem, StockAdjustment, Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "description", "cost_price", "selling_price", "stock_quantity", "minimum_stock", "shelf_life_days"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "description": forms.Textarea(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "rows": 3}),
            "cost_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "step": "0.01"}),
            "selling_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "step": "0.01"}),
            "stock_quantity": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "minimum_stock": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "shelf_life_days": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
        }

class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "contact_info"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "contact_info": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
        }

class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ["vendor"]
        widgets = {
            "vendor": forms.Select(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-white"}),
        }

class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ["product", "quantity", "cost_price", "manufacture_date", "expiry_date"]
        widgets = {
            "product": forms.Select(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg bg-white"}),
            "quantity": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg", "min": "1"}),
            "cost_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg", "step": "0.01", "min": "0"}),
            "manufacture_date": forms.DateInput(attrs={"type": "date", "class": "w-full px-3 py-2 border border-slate-300 rounded-lg"}),
            "expiry_date": forms.DateInput(attrs={"type": "date", "class": "w-full px-3 py-2 border border-slate-300 rounded-lg"}),
        }

class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ["product", "adjustment_type", "quantity", "reason"]
        widgets = {
            "product": forms.Select(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-white"}),
            "adjustment_type": forms.Select(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-white"}),
            "quantity": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "min": "1"}),
            "reason": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
        }
