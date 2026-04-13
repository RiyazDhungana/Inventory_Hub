from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Vendor, Purchase, PurchaseItem, StockAdjustment, Product, AlertSettings

class AlertSettingsForm(forms.ModelForm):
    class Meta:
        model = AlertSettings
        fields = ["recipient_emails", "alert_hour", "alert_minute", "low_stock_enabled", "expiry_enabled"]
        widgets = {
            "recipient_emails": forms.Textarea(attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500",
                "rows": 3,
                "placeholder": "email1@example.com, email2@example.com"
            }),
            "alert_hour": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500",
                "min": "0", "max": "23"
            }),
            "alert_minute": forms.NumberInput(attrs={
                "class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500",
                "min": "0", "max": "59"
            }),
            "low_stock_enabled": forms.CheckboxInput(attrs={"class": "w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"}),
            "expiry_enabled": forms.CheckboxInput(attrs={"class": "w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"}),
        }

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "sku", "description", "cost_price", "selling_price", "stock_quantity", "minimum_stock", "shelf_life_days"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "sku": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "placeholder": "StockCode (e.g. 85123A)"}),
            "description": forms.Textarea(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "rows": 3}),
            "cost_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "step": "0.01"}),
            "selling_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "step": "0.01"}),
            "stock_quantity": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "minimum_stock": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "shelf_life_days": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
        }

class ProductEditForm(forms.ModelForm):
    """Form for editing products with stock fields read-only."""
    class Meta:
        model = Product
        fields = ["name", "sku", "description", "cost_price", "selling_price", "shelf_life_days"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
            "sku": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "placeholder": "StockCode (e.g. 85123A)"}),
            "description": forms.Textarea(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "rows": 3}),
            "cost_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "step": "0.01", "min": "0.01"}),
            "selling_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500", "step": "0.01", "min": "0.01"}),
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
        fields = ["product", "quantity", "cost_price", "manufacture_date", "expiry_date", "batch_number"]
        widgets = {
            "product": forms.Select(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg bg-white"}),
            "quantity": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg", "min": "1"}),
            "cost_price": forms.NumberInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg", "step": "0.01", "min": "0"}),
            "manufacture_date": forms.DateInput(attrs={"type": "date", "class": "w-full px-3 py-2 border border-slate-300 rounded-lg"}),
            "expiry_date": forms.DateInput(attrs={"type": "date", "class": "w-full px-3 py-2 border border-slate-300 rounded-lg"}),
            "batch_number": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg", "placeholder": "Batch ID"}),
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

class AppUserCreationForm(UserCreationForm):
    ROLE_CHOICES = [
        ("Staff", "Staff (Operational Access)"),
        ("Manager", "Manager (Full Access + Reports)"),
    ]
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-white"})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"})
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ("email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Tailwind classes to existing fields
        for field in self.fields.values():
            if field != self.fields["role"] and field != self.fields["email"]:
                field.widget.attrs.update({"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"})

class AppUserUpdateForm(forms.ModelForm):
    ROLE_CHOICES = [
        ("Staff", "Staff (Operational Access)"),
        ("Manager", "Manager (Full Access + Reports)"),
    ]
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-white"})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"})
    )
    new_password = forms.CharField(
        required=False,
        label="New Password",
        help_text="Leave blank to keep existing password.",
        widget=forms.PasswordInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"})
    )

    class Meta:
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(attrs={"class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Set initial role based on group
            if self.instance.groups.filter(name="Manager").exists():
                self.fields["role"].initial = "Manager"
            elif self.instance.groups.filter(name="Staff").exists():
                self.fields["role"].initial = "Staff"
