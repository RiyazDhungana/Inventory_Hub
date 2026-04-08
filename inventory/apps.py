from django.apps import AppConfig


class InventoryConfig(AppConfig):
    name = 'inventory'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        import os
        # Only start scheduler in the main process (not in reloader subprocess)
        if os.environ.get('RUN_MAIN') == 'true':
            from inventory import scheduler
            scheduler.start()
