import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ExpenseParsed:
    amount: float
    currency: str
    category: str
    subcategory: str
    comment: str


_CURRENCY_MAP = {
    "₽": "RUB", "руб": "RUB", "руб.": "RUB", "рублей": "RUB", "р": "RUB", "р.": "RUB",
    "€": "EUR", "евро": "EUR", "eur": "EUR",
    "$": "USD", "usd": "USD", "доллар": "USD", "долларов": "USD",
}

_RULES: list[Tuple[str, str, str]] = [
    # --- transport ---
    (r"\bтакси\b", "transport", "taxi"),
    (r"\bметро\b|\bавтобус\b|\bтрамвай\b", "transport", "public"),
    (r"\bбензин\b|\bзаправк", "transport", "fuel"),

    # --- health ---
    (r"\bзал\b|\bспорт\b|\bтрен(ировка|ажер)", "health", "gym"),
    (r"\bаптека\b|\bлекарств", "health", "pharmacy"),
    (r"\bзубы\b|\bзуб\b|\bстоматолог\b|\bдантист\b", "health", "dentist"),

    # --- food ---
    (r"\bвода\b|\bводичк", "food", "water"),
    (r"\bеда\b", "food", "food"),
    (r"\bпродукт\b|\bмагазин\b|\bпятерочк\b|\bмагнит\b", "food", "groceries"),

    # --- alcohol (отдельная категория) ---
    (r"\bалко\b|\bпиво\b|\bвино\b|\bвиски\b|\bводк\b|\bджин\b|\bром\b|\bшот\b|\bбар\b|\bкоктейл\b", "alcohol", "drinks"),

    # --- хофа (своё слово — отдельная категория) ---
    (r"\bхофа\b", "hoffa", "hoffa"),

    # --- restaurants / cafes ---
    (r"\b(рестик|шава)\b", "restaurants_cafes", "fastfood"),
    (r"\bкафе\b|\bкофе\b|\bшаурм\b|\bресторан\b", "restaurants_cafes", "cafe"),

    # --- home ---
    (r"\bобщаг\b|\bобщаш\b|\bобщежит", "home", "dorm"),
    (r"\bквартплат\b|\bаренд\b|\bкоммунал", "home", "rent"),

    # --- entertainment (отдельная категория) ---
    (r"\bразлекаловк\b|\bразвлечен\b|\bкино\b|\bконцерт\b|\bклуб\b|\bвечеринк\b|\bбоулинг\b|\bкараоке\b", "entertainment", "fun"),

    # --- gifts ---
    (r"\bподарк", "gifts", "gifts"),

    # --- clothes ---
    (r"\bодежд", "clothes", "clothes"),

    # --- marketplaces ---
    (r"\b(вб|wb|озон|ozon)\b", "marketplaces", "marketplace"),

    # --- church ---
    (r"\bцерковь\b|\bцерк\b|\bхрам\b|\bпожертвован\b|\bсвеч\b", "church", "church"),

    # --- subscriptions ---
    (r"\bподписк\b|\bspotify\b|\bnetflix\b|\byoutube\b", "subscriptions", "digital"),

    # --- phone / telecom ---
    (r"\bтелефон\b|\bсвязь\b|\bмегафон\b|\bмтс\b|\bбилайн\b|\btele2\b|\bсим\b|\bинтернет\b", "phone", "telecom"),
]

_DEFAULT_CATEGORY = ("other", "other")

# Человекочитаемые названия для ответа бота
CATEGORY_LABELS = {
    "transport":         "🚕 Транспорт",
    "health":            "💊 Здоровье",
    "food":              "🛒 Еда",
    "alcohol":           "🍺 Алкоголь",
    "hoffa":             "☕ Хофа",
    "restaurants_cafes": "🍽 Рестораны/кафе",
    "home":              "🏠 Жильё",
    "entertainment":     "🎉 Развлечения",
    "gifts":             "🎁 Подарки",
    "clothes":           "👕 Одежда",
    "marketplaces":      "🛍 Маркетплейсы",
    "subscriptions":     "📱 Подписки",
    "phone":             "📞 Телефон/связь",
    "church":            "⛪ Церковь",
    "other":             "❓ Прочее",
    # subcategory fallbacks (если в таблице записана subcategory вместо category)
    "dentist":           "🦷 Зубы",
    "dorm":              "🏠 Общага",
    "drinks":            "🍺 Алкоголь",
    "gym":               "💪 Зал",
}

SUBCATEGORY_LABELS = {
    "taxi":        "такси",
    "public":      "общественный транспорт",
    "fuel":        "бензин",
    "gym":         "зал/спорт",
    "pharmacy":    "аптека",
    "dentist":     "Зубы",
    "water":       "вода",
    "food":        "еда",
    "groceries":   "продукты",
    "drinks":      "алкоголь",
    "hoffa":       "хофа",
    "fastfood":    "фастфуд",
    "cafe":        "кафе/кофе",
    "dorm":        "Общага",
    "rent":        "аренда/коммуналка",
    "fun":         "развлечения",
    "gifts":       "подарки",
    "clothes":     "одежда",
    "marketplace": "маркетплейс",
    "digital":     "цифровая подписка",
    "telecom":     "телефон/связь",
    "church":      "церковь",
    "other":       "прочее",
}


def _detect_currency(text: str) -> str:
    t = text.lower()
    for k, v in _CURRENCY_MAP.items():
        if k in t:
            return v
    return "RUB"


def _extract_amount(text: str) -> Optional[float]:
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    s = m.group(1).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _classify(text: str) -> Tuple[str, str]:
    t = text.lower()
    for pattern, cat, sub in _RULES:
        if re.search(pattern, t):
            return cat, sub
    return _DEFAULT_CATEGORY


def _cleanup_comment(text: str) -> str:
    t = text
    t = re.sub(r"(-?\d+(?:[.,]\d+)?)", "", t)
    for k in _CURRENCY_MAP.keys():
        t = t.replace(k, "")
    t = re.sub(r"\s{2,}", " ", t).strip(" ,.-\n\t")
    return t.strip()


def parse_expense(text: str) -> Optional[ExpenseParsed]:
    amount = _extract_amount(text)
    if amount is None:
        return None
    currency = _detect_currency(text)
    category, subcategory = _classify(text)
    comment = _cleanup_comment(text)
    return ExpenseParsed(
        amount=amount,
        currency=currency,
        category=category,
        subcategory=subcategory,
        comment=comment if comment else "",
    )