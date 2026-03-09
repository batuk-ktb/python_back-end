from .models import Container


def save_container(data):
    if not data or not data.get("id"):
        return None

    return Container.objects.create(
        container_id=data.get("id"),
        date=data.get("date"),
        control_digit=data.get("control_digit"),
        readconfidence=data.get("readconfidence"),
        plateImage=data.get("plateImage")
    )