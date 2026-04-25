# Traveloka Hotel Room Rates Scraper

Extracts hotel room rates from Traveloka using request interception and API replay.

## How It Works

1. Selenium opens the hotel page to pass AWS WAF bot protection and capture session cookies
2. The rooms API request (`/api/v2/hotel/search/rooms`) is intercepted from Chrome performance logs
3. The captured request is replayed using `requests` to fetch room data
4. The API response is parsed into a structured JSON output

> Selenium is used **only** for session initialization — Traveloka requires JavaScript execution to obtain valid AWS WAF cookies. All data extraction is performed via `requests` against the JSON API. No HTML parsing or BeautifulSoup is used.

## Requirements

- Python 3.10+
- Chrome/Chromium browser installed
- Internet connection

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Configuration

Edit the variables at the top of `main.py`:

| Variable | Description |
|----------|-------------|
| `HOTEL_ID` | Traveloka hotel ID |
| `HOTEL_NAME` | Hotel name for URL encoding |
| `CHECK_IN` / `CHECK_OUT` | Dates in DD-MM-YYYY format |
| `NUM_ROOMS` / `NUM_ADULTS` | Room and guest count |
| `CURRENCY` | Display currency (e.g. EUR, USD) |
| `HEADLESS` | Run browser in headless mode |

## Output

Results are saved to `result.json`:

```json
{
  "rates": [
    {
      "room_name": "Superior Ocean View",
      "rate_name": "Superior Ocean View",
      "shown_currency": "EUR",
      "shown_price": {
        "rate name": "Superior Ocean View"
      },
      "net_price": 68.09,
      "cancellation policy": "Non refundable",
      "breakfast": "Breakfast not Included",
      "number_of_guests": "2",
      "taxes_amount": 12.06,
      "total_price": 80.15,
      "original_price": 88.8,
      "shown_price_per_stay": 80.15,
      "net_price_per_stay": 68.09,
      "total_price_per_stay": 80.15
    }
  ]
}
```

## Deep Link Generation

The script automatically generates a Traveloka deep link from the configuration parameters. You can also set `DEEPLINK_URL` directly in the code if needed.
