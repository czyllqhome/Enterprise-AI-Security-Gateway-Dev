def mask_value(value: str) -> str:
    if "@" in value:
        local_part, domain = value.split("@", 1)
        visible = local_part[:1] or "*"
        return f"{visible}***@{domain}"
    if len(value) <= 4:
        return "*" * len(value)
    if len(value) <= 8:
        return f"{value[:1]}{'*' * (len(value) - 2)}{value[-1:]}"
    return f"{value[:2]}{'*' * max(1, len(value) - 4)}{value[-2:]}"
