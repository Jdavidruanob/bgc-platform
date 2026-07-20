def format_miles_colombian_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def parse_miles_colombian(text: str) -> int:
    clean = "".join(ch for ch in text if ch.isdigit())
    return int(clean) if clean else 0


def format_full_name_for_excel(nombres: str, apellidos: str, max_length: int = 24) -> str:
    original_full_name = f"{nombres} {apellidos}"
    if len(original_full_name) <= max_length:
        return original_full_name

    parts_nombres = nombres.split()
    parts_apellidos = apellidos.split()

    if len(parts_apellidos) > 1:
        temp_apellidos = f"{parts_apellidos[0]} {parts_apellidos[1][0]}."
        temp_full_name = f"{nombres} {temp_apellidos}"
        if len(temp_full_name) <= max_length:
            return temp_full_name

    if len(parts_nombres) > 1:
        temp_nombres = f"{parts_nombres[0]} {parts_nombres[1][0]}."
        temp_full_name = f"{temp_nombres} {apellidos}"
        if len(temp_full_name) <= max_length:
            return temp_full_name

    if len(parts_nombres) > 1 and len(parts_apellidos) > 1:
        reduced_nombres = f"{parts_nombres[0]} {parts_nombres[1][0]}."
        reduced_apellidos = f"{parts_apellidos[0]} {parts_apellidos[1][0]}."
        final_name = f"{reduced_nombres} {reduced_apellidos}"
        if len(final_name) <= max_length:
            return final_name

    final_parts: list[str] = [parts_nombres[0]] if parts_nombres else []

    if len(parts_nombres) > 1:
        initial = f"{parts_nombres[1][0]}."
        candidate = " ".join(final_parts + [initial, parts_apellidos[0] if parts_apellidos else ""])
        if len(candidate) <= max_length:
            final_parts.append(initial)

    if parts_apellidos:
        final_parts.append(parts_apellidos[0])

    if len(parts_apellidos) > 1:
        initial = f"{parts_apellidos[1][0]}."
        if len(" ".join(final_parts + [initial])) <= max_length:
            final_parts.append(initial)

    return " ".join(final_parts)
