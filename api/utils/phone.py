import re

def normalize_phone(phone):
    """
    Normalizes a phone number by removing all non-digit characters.
    If the number starts with '00', replaces it with nothing (or handles as needed).
    For comparison purposes, stripping everything except digits is usually safest.
    """
    if not phone:
        return ""
    # Remove all non-digit characters
    normalized = re.sub(r'\D', '', str(phone))
    
    # Optional: if it starts with 00, it might be a country code prefix equivalent to +
    # But let's keep it simple for now and just return all digits.
    return normalized
