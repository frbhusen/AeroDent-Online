"""Saving phone numbers in international (E.164-style) format, based on the clinic's country.

Examples for a clinic in Syria (+963):
    0944 123 456     -> +963944123456   (national format: the leading 0 is dropped)
    944123456        -> +963944123456
    00963944123456   -> +963944123456
    +963 (0) 944 123 456 / +9630944123456 -> +963944123456  (stray trunk 0 after the code is dropped)
    963944123456     -> +963944123456   (already carries the country code)

A clinic without a country keeps numbers as typed (only an international "00" prefix becomes "+").
"""

import re

from backend.services.countries import get_country

MIN_DIGITS = 7
MAX_DIGITS = 15  # E.164 maximum
# National numbers (without the leading 0) are at most this long; used to tell "963944123456"
# (already international) from a national number that merely starts with the same digits.
MAX_NATIONAL_DIGITS = 11
PHONE_ERROR = "Phone number is not valid for the clinic's country."

_SEPARATORS = re.compile(r"[\s\-().]")


def normalize_phone(raw, country_code):
    """Returns (phone, error). Blank input returns (None, None)."""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None

    country = get_country(country_code)
    compact = _SEPARATORS.sub("", text)

    if country is None:
        # No country configured: leave the number as typed, except the "00" international prefix.
        return ("+" + compact[2:] if compact.startswith("00") and compact[2:].isdigit() else text), None

    dial = country["dial"]
    plus = compact.startswith("+")
    digits = compact[1:] if plus else compact
    if not digits.isdigit():
        return None, PHONE_ERROR

    if plus:
        pass  # already international
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = dial + digits.lstrip("0")
    elif digits.startswith(dial) and MIN_DIGITS <= len(digits) - len(dial) <= MAX_NATIONAL_DIGITS:
        pass  # typed with the country code but without "+"
    else:
        digits = dial + digits

    # "+963 0944..." / "+963 (0) 944...": the national trunk 0 must not follow the country code.
    if digits.startswith(dial) and digits[len(dial):].startswith("0"):
        digits = dial + digits[len(dial):].lstrip("0")

    if not digits or not MIN_DIGITS <= len(digits) <= MAX_DIGITS:
        return None, PHONE_ERROR
    return "+" + digits, None
