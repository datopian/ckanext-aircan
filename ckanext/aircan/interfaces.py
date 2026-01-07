import ckan.plugins as plugins


class IAircan(plugins.Interface):
    """Interface for plugins to extend Aircan payload."""

    def update_payload(self, context, payload):
        """Update the payload before submitting to Airflow.

        Args:
            context: The CKAN context dict
            payload: The payload dict to be updated (modified in place)
        """
        pass
