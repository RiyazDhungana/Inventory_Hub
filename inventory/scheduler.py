import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler = BackgroundScheduler(timezone="Asia/Kathmandu")

def start():
    from inventory.cron import check_stock_and_expiry
    from inventory.models import AlertSettings

    if _scheduler.running:
        _scheduler.shutdown(wait=False)

    alert_settings = AlertSettings.get_settings()
    
    # Clear existing jobs to avoid duplicates
    _scheduler.remove_all_jobs()

    # Run every day at the time configured in database
    _scheduler.add_job(
        check_stock_and_expiry,
        trigger=CronTrigger(hour=alert_settings.alert_hour, minute=alert_settings.alert_minute),
        id="daily_stock_expiry_alert",
        name="Daily Stock & Expiry Email Alert",
        replace_existing=True,
    )

    if not _scheduler.running:
        _scheduler.start()
        
    print(f"APScheduler sync complete: Daily Alert scheduled at {alert_settings.alert_hour:02d}:{alert_settings.alert_minute:02d} NPT.")
