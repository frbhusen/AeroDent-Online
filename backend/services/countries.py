"""Countries a clinic can be located in: dialling code and a suggested currency.

The clinic's country decides how phone numbers are saved (see services/phone.py). The currency is
only a suggestion; clinics can pick any currency or type their own.
"""

# code, English name, Arabic name, international dialling code, suggested currency
_COUNTRY_ROWS = (
    ("SY", "Syria", "سوريا", "963", "SYR"),
    ("LB", "Lebanon", "لبنان", "961", "LBP"),
    ("JO", "Jordan", "الأردن", "962", "JOD"),
    ("IQ", "Iraq", "العراق", "964", "IQD"),
    ("PS", "Palestine", "فلسطين", "970", "ILS"),
    ("EG", "Egypt", "مصر", "20", "EGP"),
    ("SA", "Saudi Arabia", "السعودية", "966", "SAR"),
    ("AE", "United Arab Emirates", "الإمارات", "971", "AED"),
    ("KW", "Kuwait", "الكويت", "965", "KWD"),
    ("QA", "Qatar", "قطر", "974", "QAR"),
    ("BH", "Bahrain", "البحرين", "973", "BHD"),
    ("OM", "Oman", "عُمان", "968", "OMR"),
    ("YE", "Yemen", "اليمن", "967", "YER"),
    ("LY", "Libya", "ليبيا", "218", "LYD"),
    ("TN", "Tunisia", "تونس", "216", "TND"),
    ("DZ", "Algeria", "الجزائر", "213", "DZD"),
    ("MA", "Morocco", "المغرب", "212", "MAD"),
    ("SD", "Sudan", "السودان", "249", "SDG"),
    ("TR", "Turkey", "تركيا", "90", "TRY"),
    ("IR", "Iran", "إيران", "98", "IRR"),
    ("US", "United States", "الولايات المتحدة", "1", "USD"),
    ("CA", "Canada", "كندا", "1", "CAD"),
    ("GB", "United Kingdom", "المملكة المتحدة", "44", "GBP"),
    ("DE", "Germany", "ألمانيا", "49", "EUR"),
    ("FR", "France", "فرنسا", "33", "EUR"),
    ("SE", "Sweden", "السويد", "46", "SEK"),
    ("NL", "Netherlands", "هولندا", "31", "EUR"),
    ("IN", "India", "الهند", "91", "INR"),
    ("PK", "Pakistan", "باكستان", "92", "PKR"),
)

COUNTRIES = {
    code: {"code": code, "name_en": name_en, "name_ar": name_ar, "dial": dial, "currency": currency}
    for code, name_en, name_ar, dial, currency in _COUNTRY_ROWS
}


def get_country(code):
    return COUNTRIES.get(code) if isinstance(code, str) else None


def list_countries():
    return list(COUNTRIES.values())
