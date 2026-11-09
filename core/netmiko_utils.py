"""Shared Netmiko device helpers."""


VENDOR_NAMES = {
    "huawei": "华为",
    "h3c": "新华三",
    "cisco": "思科",
}


def vendor_from_device_type(device_type: str):
    """Return the supported vendor key for a Netmiko device type."""
    normalized = str(device_type).strip().lower()
    if normalized.startswith(("h3c", "hp_comware")):
        return "h3c"
    if normalized.startswith("cisco"):
        return "cisco"
    if normalized.startswith("huawei"):
        return "huawei"
    return None


def disable_terminal_paging(connection, device_config: dict):
    """Disable pagination using the command for the connected vendor."""
    device_type = str(device_config.get("device_type", ""))
    if device_type.startswith("cisco"):
        connection.send_command("terminal length 0")
    elif device_type.startswith(("h3c", "hp_comware")):
        connection.send_command("screen-length disable")
    else:
        connection.send_command("screen-length 0 temporary")
