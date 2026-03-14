import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SPREADSHEET_ID = "1So-TALP3EmCIEOYeyrgVlekw9jibe-iORhUN0ZX6V0Y"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file(
    "service_account.json",
    scopes=SCOPES
)

client = gspread.authorize(creds)

sheet = client.open_by_key(SPREADSHEET_ID)

ws = sheet.worksheet("expenses")

ws.append_row([
    "test-id-001",
    datetime.now().isoformat(),
    "123456789",
    "2026-02-16",
    "2.5",
    "RUB",
    "transport",
    "taxi",
    "до дома",
    "такси 2,5 рублей до дома"
])

print("✅ Успешно! Строка добавлена в expenses.")
