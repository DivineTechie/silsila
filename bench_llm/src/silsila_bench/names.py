"""Emirati first names used for the FICTIONAL people in Silsila-Bench families.

Common first names only (no family names), so no item describes a real person.
Each entry is (Latin spelling used as the person id and in English/Arabizi text,
Arabic script used in the MSA and Gulf Arabic stories).
"""

from __future__ import annotations

import re
import unicodedata

MALE: tuple[tuple[str, str], ...] = (
    ("Ahmed", "أحمد"), ("Rashid", "راشد"), ("Saeed", "سعيد"), ("Khalid", "خالد"), ("Obaid", "عبيد"),
    ("Hamad", "حمد"), ("Sultan", "سلطان"), ("Saif", "سيف"), ("Majid", "ماجد"), ("Juma", "جمعة"),
    ("Ali", "علي"), ("Mansour", "منصور"), ("Abdullah", "عبدالله"), ("Salem", "سالم"), ("Humaid", "حميد"),
    ("Mubarak", "مبارك"), ("Faisal", "فيصل"), ("Nasser", "ناصر"), ("Hareb", "حارب"), ("Butti", "بطي"),
    ("Suhail", "سهيل"), ("Mattar", "مطر"), ("Ateeq", "عتيق"), ("Ghanim", "غانم"), ("Yousef", "يوسف"),
    ("Ibrahim", "إبراهيم"), ("Omar", "عمر"), ("Jassim", "جاسم"), ("Marwan", "مروان"), ("Hilal", "هلال"),
    ("Eissa", "عيسى"), ("Musabbeh", "مصبح"), ("Khamis", "خميس"), ("Rashed", "راشد"), ("Thani", "ثاني"),
    ("Hamdan", "حمدان"), ("Mohammed", "محمد"), ("Ghaith", "غيث"), ("Badr", "بدر"), ("Waleed", "وليد"),
    ("Adel", "عادل"), ("Hassan", "حسن"), ("Hussain", "حسين"), ("Fahad", "فهد"), ("Nahyan", "نهيان"),
)
FEMALE: tuple[tuple[str, str], ...] = (
    ("Fatima", "فاطمة"), ("Mariam", "مريم"), ("Aisha", "عائشة"), ("Moza", "موزة"), ("Hessa", "حصة"),
    ("Shamma", "شما"), ("Mahra", "مهرة"), ("Alyazia", "اليازية"), ("Latifa", "لطيفة"), ("Noura", "نورة"),
    ("Salama", "سلامة"), ("Maitha", "ميثاء"), ("Sheikha", "شيخة"), ("Amna", "آمنة"), ("Hind", "هند"),
    ("Reem", "ريم"), ("Meera", "ميرة"), ("Asma", "أسماء"), ("Khawla", "خولة"), ("Afra", "عفراء"),
    ("Ghaya", "غاية"), ("Hamda", "حمدة"), ("Sara", "سارة"), ("Wadeema", "وديمة"), ("Roudha", "روضة"),
    ("Lubna", "لبنى"), ("Fakhra", "فخرة"), ("Badriya", "بدرية"), ("Jawaher", "جواهر"), ("Nouf", "نوف"),
    ("Hala", "هالة"), ("Shamsa", "شمسة"), ("Alanood", "العنود"), ("Dana", "دانة"), ("Muna", "منى"),
    ("Khadija", "خديجة"), ("Zainab", "زينب"), ("Ohoud", "عهود"), ("Bakhita", "بخيتة"), ("Sultana", "سلطانة"),
    ("Mouza", "موزا"), ("Hamama", "حمامة"), ("Rawda", "روضة"), ("Nadia", "نادية"), ("Huda", "هدى"),
)

# "Rashed"/"Rashid", "Mouza"/"Moza" and "Rawda"/"Roudha" share Arabic spellings; never use both of a
# pair in one family (names must be unique in each script).
_DUP_AR = {"Rashed", "Mouza", "Rawda"}
MALE = tuple(n for n in MALE if n[0] not in _DUP_AR)
FEMALE = tuple(n for n in FEMALE if n[0] not in _DUP_AR)

_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def normalise(name: str) -> str:
    """Normalise a name for matching across scripts and spelling variants."""
    s = unicodedata.normalize("NFKC", str(name)).strip()
    s = _AR_DIACRITICS.sub("", s)
    s = re.sub("[أإآٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"[\s_\-'’]+", "", s)
    return s.casefold()
