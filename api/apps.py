from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        import threading
        from api.management.commands.poll_plc import start_poller
        t = threading.Thread(target=start_poller, daemon=True)
        t.start()
