class RemoteSyncRouter:
    """
    Routes RemoteSyncLog model to the 'remote_sync' database.
    All other models use the 'default' database.
    """

    def db_for_read(self, model, **hints):
        if model.__name__ == 'RemoteSyncLog':
            return 'remote_sync'
        return 'default'

    def db_for_write(self, model, **hints):
        if model.__name__ == 'RemoteSyncLog':
            return 'remote_sync'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name == 'remotesynelog':
            return db == 'remote_sync'
        if db == 'remote_sync':
            return False
        return db == 'default'
