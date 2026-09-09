from django.apps import AppConfig

# Module-level reference keeps the socket alive for the entire process lifetime.
# If it were a local variable inside ready(), Python's GC would release it as
# soon as ready() returned, freeing port 47123 and letting the second Waitress
# worker bind it too — causing every poller to run twice.
_MUTEX_SOCK = None


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        global _MUTEX_SOCK
        import socket, threading
        _MUTEX_SOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            _MUTEX_SOCK.bind(('127.0.0.1', 47123))
            _MUTEX_SOCK.listen(1)
        except OSError:
            _MUTEX_SOCK.close()
            _MUTEX_SOCK = None
            return  # another process already holds the lock
        from api.management.commands.poll_plc import start_poller
        from api.management.commands.refresh_dashboard import start_refresher
        threading.Thread(target=start_poller,    daemon=True).start()
        threading.Thread(target=start_refresher, daemon=True).start()
