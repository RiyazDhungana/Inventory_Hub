from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

def setup_user_groups():
    # Define Roles and their associated permissions (model names in inventory app)
    roles = {
        "Staff": [
            "view_product", "add_product",
            "view_sale", "add_sale",
            "view_vendor", "add_vendor",
            "view_purchase", "add_purchase",
            "view_stockadjustment", "add_stockadjustment",
            "view_low_stock_alerts",
        ],
        "Manager": [
            "view_product", "add_product", "change_product",
            "view_sale", "add_sale", "change_sale",
            "view_vendor", "add_vendor", "change_vendor",
            "view_purchase", "add_purchase", "change_purchase",
            "view_stockadjustment", "add_stockadjustment", "change_stockadjustment",
            "view_profit_dashboard", "view_low_stock_alerts",
        ]
    }

    for role_name, perms in roles.items():
        group, created = Group.objects.get_or_create(name=role_name)
        
        # Get permissions
        permission_objs = []
        for perm_codename in perms:
            try:
                # Most permissions are standard app.codename
                if "view_profit_dashboard" in perm_codename or "view_low_stock_alerts" in perm_codename:
                     p = Permission.objects.get(codename=perm_codename, content_type__app_label='inventory')
                else:
                    # Standard Django permissions: add_model, change_model, delete_model, view_model
                    p = Permission.objects.get(codename=perm_codename, content_type__app_label='inventory')
                permission_objs.append(p)
            except Permission.DoesNotExist:
                # Log or handle missing permissions if necessary
                pass
        
        group.permissions.set(permission_objs)
    
    return True
