"""Task 5.2 — amount_paise -> Indian-numbering words. Pure function, no I/O."""

_UNITS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
          "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
          "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    return (_TENS[n // 10] + (" " + _UNITS[n % 10] if n % 10 else "")).strip()


def _words(n: int) -> str:
    """Indian grouping: crore (10^7), lakh (10^5), thousand (10^3), hundred, rest."""
    if n == 0:
        return ""
    parts = []
    if n >= 10_000_000:
        parts.append(_words(n // 10_000_000) + " Crore")
        n %= 10_000_000
    if n >= 100_000:
        parts.append(_two(n // 100_000) + " Lakh")
        n %= 100_000
    if n >= 1_000:
        parts.append(_two(n // 1_000) + " Thousand")
        n %= 1_000
    if n >= 100:
        parts.append(_UNITS[n // 100] + " Hundred")
        n %= 100
    if n:
        parts.append(_two(n))
    return " ".join(parts)


def amount_to_words(amount_paise: int) -> str:
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise ValueError("amount_paise must be a positive integer")
    rupees, paise = divmod(amount_paise, 100)
    rupee_word = "Rupee" if rupees == 1 else "Rupees"
    if rupees and paise:
        return f"{_words(rupees)} {rupee_word} and {_words(paise)} Paise Only"
    if rupees:
        return f"{_words(rupees)} {rupee_word} Only"
    return f"{_words(paise)} Paise Only"
