# main.py — Расходы (Google Sheets)
# Файлы рядом: .env, service_account.json, parse_expense.py
#
# expenses (строка 1 — заголовки):
# id | created_at | owner | date | amount | currency | category | subcategory | comment | raw_text

import os
import re
from pathlib import Path
from datetime import datetime, date, timedelta

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from aiogram import Bot, Dispatcher
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import CommandStart

from parse_expense import parse_expense, CATEGORY_LABELS, SUBCATEGORY_LABELS

print("🔥 RUNNING MAIN.PY (EXPENSES ONLY) VERSION 2026-03-14")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
TZ = os.getenv("TZ") or "Europe/Moscow"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не загрузился. Проверь .env")
if not SPREADSHEET_ID:
    raise RuntimeError("SPREADSHEET_ID не загрузился. Проверь .env")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_BOOK = None


def get_sheets():
    global _BOOK
    if _BOOK is not None:
        return _BOOK
    creds = Credentials.from_service_account_file(
        str(BASE_DIR / "service_account.json"),
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    _BOOK = client.open_by_key(SPREADSHEET_ID)
    return _BOOK


# =========================
#        KEYBOARDS
# =========================

def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня"),      KeyboardButton(text="📆 Неделя")],
            [KeyboardButton(text="📊 Месяц"),         KeyboardButton(text="◀️ Другой месяц")],
            [KeyboardButton(text="↩️ Отменить")],
        ],
        resize_keyboard=True,
    )


MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def month_ru(month: int, year: int) -> str:
    return f"{MONTHS_RU[month]} {year}"


def kb_month_picker() -> InlineKeyboardMarkup:
    """Последние 6 месяцев как инлайн-кнопки."""
    today = datetime.now().date()
    buttons = []
    for i in range(6):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        buttons.append([InlineKeyboardButton(
            text=month_ru(month, year),
            callback_data=f"month:{year}:{month:02d}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =========================
#         HELPERS
# =========================

def norm_text(message: Message) -> str:
    return (message.text or "").strip()


def fmt_amount(amount: float) -> str:
    if amount == int(amount):
        return f"{int(amount):,}".replace(",", " ")
    return f"{amount:,.2f}".replace(",", " ")


def currency_sign(currency: str) -> str:
    return {"RUB": "₽", "EUR": "€", "USD": "$"}.get(currency, currency)


def _date_range(mode: str):
    today = datetime.now().date()
    if mode == "today":
        return today, today + timedelta(days=1)
    elif mode == "week":
        return today - timedelta(days=6), today + timedelta(days=1)
    elif mode == "month":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1)
        else:
            end = start.replace(month=start.month + 1, day=1)
        return start, end


def _month_date_range(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _get_expenses(uid: str, start: date, end: date) -> list:
    book = get_sheets()
    ws = book.worksheet("expenses")
    rows = ws.get_all_records()
    result = []
    for r in rows:
        if str(r.get("owner", "")) != uid:
            continue
        ds = str(r.get("date", "")).strip()
        if not ds:
            continue
        try:
            d = datetime.fromisoformat(ds).date()
        except Exception:
            continue
        if start <= d < end:
            result.append(r)
    return result


def _build_report(rows: list, title: str) -> str:
    if not rows:
        return f"{title}\n\nПока пусто 🙂"

    by_cat: dict[str, float] = {}
    by_cur: dict[str, float] = {}
    main_cur = "RUB"

    for r in rows:
        try:
            amt = float(str(r.get("amount", "0")).replace(",", "."))
        except Exception:
            amt = 0.0
        cat = (r.get("category") or "other").strip() or "other"
        cur = (r.get("currency") or "RUB").strip()
        by_cat[cat] = by_cat.get(cat, 0.0) + amt
        by_cur[cur] = by_cur.get(cur, 0.0) + amt
        main_cur = cur

    sign = currency_sign(main_cur)
    total = sum(by_cur.values())

    lines = [title, ""]

    sorted_cats = sorted(by_cat.items(), key=lambda x: -x[1])
    max_amt = sorted_cats[0][1] if sorted_cats else 1

    for cat, amt in sorted_cats:
        label = CATEGORY_LABELS.get(cat, f"❓ {cat}")
        bar_len = int((amt / max_amt) * 8)
        bar = "█" * bar_len + "░" * (8 - bar_len)
        lines.append(f"{label}")
        lines.append(f"  {bar}  {fmt_amount(amt)} {sign}")

    lines.append("")
    lines.append(f"──────────────────")
    lines.append(f"💰 Итого: {fmt_amount(total)} {sign}")

    return "\n".join(lines)


def _get_last_expense_row(uid: str):
    book = get_sheets()
    ws = book.worksheet("expenses")
    all_vals = ws.get_all_values()
    if not all_vals or len(all_vals) < 2:
        return None, ws

    header = [h.strip() for h in all_vals[0]]
    try:
        owner_col = header.index("owner")
    except ValueError:
        return None, ws

    for i in range(len(all_vals) - 1, 0, -1):
        row = all_vals[i]
        if len(row) > owner_col and row[owner_col] == uid:
            return i + 1, ws  # gspread: 1-based

    return None, ws


# =========================
#           BOT
# =========================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================
#        HANDLERS
# =========================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"Привет, {name}! 👋\n\n"
        f"Просто напиши расход — я сам запишу:\n"
        f"<code>зал 500</code>\n"
        f"<code>такси 250 до дома</code>\n"
        f"<code>хофа 180</code>\n\n"
        f"Или нажми кнопку снизу 👇",
        parse_mode="HTML",
        reply_markup=kb_main(),
    )


async def send_report(message: Message, mode: str):
    titles = {
        "today": "📅 Расходы сегодня",
        "week":  "📆 Расходы за неделю",
        "month": "📊 Расходы за месяц",
    }
    start, end = _date_range(mode)
    uid = str(message.from_user.id)
    rows = _get_expenses(uid, start, end)
    text = _build_report(rows, titles[mode])
    await message.answer(text, reply_markup=kb_main())


async def undo_last(message: Message):
    uid = str(message.from_user.id)
    row_idx, ws = _get_last_expense_row(uid)
    if row_idx is None:
        await message.answer("Нечего отменять 🤷", reply_markup=kb_main())
        return

    all_vals = ws.get_all_values()
    row = all_vals[row_idx - 1]
    header = [h.strip() for h in all_vals[0]]

    def get_col(col_name):
        try:
            return row[header.index(col_name)]
        except (ValueError, IndexError):
            return ""

    amount  = get_col("amount")
    cat     = get_col("category")
    raw     = get_col("raw_text")
    comment = get_col("comment")

    ws.delete_rows(row_idx)

    label = CATEGORY_LABELS.get(cat, cat)
    await message.answer(
        f"↩️ Отменил последний расход:\n"
        f"{label} — {amount} ₽\n"
        f"<i>{raw or comment}</i>",
        parse_mode="HTML",
        reply_markup=kb_main(),
    )


async def handle_expense_text(message: Message):
    raw = norm_text(message)
    uid = message.from_user.id

    parsed = parse_expense(raw)
    if parsed is None:
        await message.answer(
            "Не понял сумму 😅\n"
            "Напиши так: <code>такси 250</code> или <code>зал 1500</code>",
            parse_mode="HTML",
            reply_markup=kb_main(),
        )
        return

    now = datetime.now()
    book = get_sheets()
    ws = book.worksheet("expenses")

    ws.append_row([
        f"exp-{int(now.timestamp())}",
        now.isoformat(),
        str(uid),
        now.date().isoformat(),
        str(parsed.amount),
        parsed.currency,
        parsed.category,
        parsed.subcategory,
        parsed.comment,
        raw,
    ])

    sign  = currency_sign(parsed.currency)
    label = CATEGORY_LABELS.get(parsed.category, parsed.category)
    sub   = SUBCATEGORY_LABELS.get(parsed.subcategory, parsed.subcategory)

    await message.answer(
        f"✅ <b>{fmt_amount(parsed.amount)} {sign}</b> — {label}\n"
        f"<i>{sub}{(' · ' + parsed.comment) if parsed.comment else ''}</i>",
        parse_mode="HTML",
        reply_markup=kb_main(),
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("month:"))
async def cb_month(call: CallbackQuery):
    _, year_s, month_s = call.data.split(":")
    year, month = int(year_s), int(month_s)
    start, end = _month_date_range(year, month)
    uid = str(call.from_user.id)
    rows = _get_expenses(uid, start, end)
    title = f"📊 {month_ru(month, year)}"
    text = _build_report(rows, title)
    await call.message.edit_text(text)
    await call.answer()


@dp.message()
async def router(message: Message):
    text = norm_text(message)
    t = text.lower()

    if text.startswith("◀️") or "другой месяц" in t:
        await message.answer("Выбери месяц:", reply_markup=kb_month_picker())
        return

    if text.startswith("📅") or t == "сегодня":
        await send_report(message, "today")
        return

    if text.startswith("📆") or t == "неделя":
        await send_report(message, "week")
        return

    if text.startswith("📊") or t == "месяц":
        await send_report(message, "month")
        return

    if text.startswith("↩️") or t in ("отменить", "отмена"):
        await undo_last(message)
        return

    # любой текст с цифрой — парсим как расход
    if re.search(r"\d", text):
        await handle_expense_text(message)
        return

    await message.answer(
        "Напиши расход, например:\n"
        "<code>зал 500</code>\n"
        "<code>такси 250 до дома</code>",
        parse_mode="HTML",
        reply_markup=kb_main(),
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())