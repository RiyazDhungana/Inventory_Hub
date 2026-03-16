from django.core.mail import send_mail
from django.conf import settings

def send_low_stock_email(product_name, quantity, recipients):
    subject = f"Low Stock Alert: {product_name}"
    message = f"The stock for {product_name} is low. Current quantity: {quantity}."
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients)

def send_expiry_alert_email(product_name, quantity, expiry_date, recipients):
    subject = f"Expiry Alert: {product_name}"
    message = f"{quantity} units of {product_name} are expiring on {expiry_date}."
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients)