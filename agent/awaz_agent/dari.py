"""Small text helpers for Dari: spelling normalization, digits and phone numbers."""

import re

# Arabic letters that look like Persian ones but are different code points.
# Speech recognition and keyboards mix them, so "كباب" must match "کباب".
_LETTER_MAP = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "أ": "ا",
        "إ": "ا",
        "ٱ": "ا",
    }
)
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# Short vowel marks, tanween, superscript alef and tatweel carry no meaning for matching.
_MARKS = re.compile(r"[ً-ٰٟـ]")
_SPACES = re.compile(r"[\s‌‏‎]+")


def to_ascii_digits(text: str) -> str:
    """Turn Dari (Persian) and Arabic-Indic digits into 0-9."""
    return text.translate(_DIGIT_MAP)


def normalize(text: str) -> str:
    """A matching key for Dari or English text: same letters, no marks, single spaces."""
    text = to_ascii_digits(text).translate(_LETTER_MAP)
    text = _MARKS.sub("", text)
    text = _SPACES.sub(" ", text)
    return text.strip().lower()


def normalize_phone(raw: str) -> str | None:
    """Clean a spoken or typed phone number; None when it is too short to be real.

    Keeps a leading + for international numbers, drops spaces and dashes, and
    accepts Dari digits: "۰۷۹۹ ۱۲۳ ۴۵۶" becomes "0799123456".
    """
    text = to_ascii_digits(raw).strip()
    plus = text.startswith("+") or text.startswith("00")
    digits = re.sub(r"\D", "", text)
    if text.startswith("00"):
        digits = digits[2:]
    if len(digits) < 9 or len(digits) > 15:
        return None
    return f"+{digits}" if plus else digits
