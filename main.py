"""Traveloka hotel room rates scraper using request capture and API replay."""

import json
import time
import uuid
import urllib.parse
from copy import deepcopy

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


# Config

HOTEL_ID = "9000001153383"
HOTEL_NAME = "Radisson Resort & Spa Hua Hin"
CHECK_IN = "25-04-2026"
CHECK_OUT = "26-04-2026"
NUM_ROOMS = 1
NUM_ADULTS = 2
CURRENCY = "EUR"
LOCALE = "en-en"

CHROMEDRIVER_PATH = ""
HEADLESS = False
CAPTURE_TIMEOUT = 60

API_PATH = "/api/v2/hotel/search/rooms"
OUTPUT_FILE = "result.json"



def build_deeplink() -> str:
    encoded_name = urllib.parse.quote(HOTEL_NAME, safe="")
    spec = (
        f"{CHECK_IN}.{CHECK_OUT}.1.{NUM_ROOMS}"
        f".HOTEL.{HOTEL_ID}.{encoded_name}.{NUM_ADULTS}"
    )
    return (
        f"https://www.traveloka.com/{LOCALE}/hotel/detail"
        f"?spec={spec}&cur={CURRENCY}&multiRoomAlternativeOption=false"
    )



def _create_driver() -> webdriver.Chrome:
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1200")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    svc = Service(CHROMEDRIVER_PATH) if CHROMEDRIVER_PATH else Service()
    return webdriver.Chrome(service=svc, options=opts)


def _extract_cookies(driver: webdriver.Chrome) -> dict[str, str]:
    return {c["name"]: c["value"] for c in driver.get_cookies() if c.get("name")}


def _find_rooms_request(driver: webdriver.Chrome) -> dict | None:
    for entry in driver.get_log("performance"):
        try:
            msg = json.loads(entry["message"])["message"]
        except (json.JSONDecodeError, KeyError):
            continue

        if msg.get("method") != "Network.requestWillBeSent":
            continue

        req = msg.get("params", {}).get("request", {})
        if API_PATH not in req.get("url", ""):
            continue
        if req.get("method", "").upper() != "POST":
            continue
        if not req.get("postData"):
            continue

        return {
            "url": req["url"],
            "headers": req["headers"],
            "payload": json.loads(req["postData"]),
        }
    return None


def capture_session(deeplink: str) -> dict:
    """
    Open the hotel page in Chrome, wait for the rooms API request,
    and return captured cookies, headers, URL, and payload.
    """
    driver = _create_driver()
    try:
        print(f"Opening: {deeplink}")
        driver.get(deeplink)

        print(f"Waiting for {API_PATH}...")
        deadline = time.time() + CAPTURE_TIMEOUT
        captured = None

        while time.time() < deadline:
            captured = _find_rooms_request(driver)
            if captured:
                break
            time.sleep(0.5)

        if not captured:
            raise TimeoutError(f"Timed out waiting for {API_PATH}")

        print(f"Captured: {captured['url']}")
        return {
            "url": captured["url"],
            "headers": captured["headers"],
            "payload": captured["payload"],
            "cookies": _extract_cookies(driver),
        }
    finally:
        driver.quit()
        print("Browser closed.")



BLOCKED_HEADERS = frozenset({
    "host", "content-length", "cookie", "connection",
    "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
    "priority", "te", "accept-encoding",
    ":authority", ":method", ":path", ":scheme",
})


def _clean_headers(raw: dict, deeplink: str) -> dict[str, str]:
    headers = {k: str(v) for k, v in raw.items() if k.lower() not in BLOCKED_HEADERS}
    headers.update({
        "Referer": deeplink,
        "Origin": "https://www.traveloka.com",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate",
    })
    return headers


def _refresh_payload(payload: dict, deeplink: str) -> dict:
    updated = deepcopy(payload)

    data = updated.get("data", {})
    data["tid"] = str(uuid.uuid4())

    ctx = data.get("contexts", {})
    ctx["hotelDetailURL"] = deeplink

    mkt = ctx.get("marketingContextCapsule", {})
    if mkt:
        mkt["referrer_url"] = deeplink
        mkt["page_full_url"] = deeplink

    return updated


def replay_request(session_data: dict, deeplink: str) -> dict:
    session = requests.Session()
    for name, value in session_data["cookies"].items():
        session.cookies.set(name, value)

    response = session.post(
        url=session_data["url"],
        headers=_clean_headers(session_data["headers"], deeplink),
        json=_refresh_payload(session_data["payload"], deeplink),
        timeout=30,
    )
    print(f"Replay status: {response.status_code}")
    response.raise_for_status()
    return response.json()



def _get_decimals(rate: dict) -> int:
    try:
        val = (rate.get("rateDisplay") or {}).get("numOfDecimalPoint")
        return max(int(val), 0) if val not in ("", None) else 0
    except (ValueError, TypeError):
        return 0


def _fmt_price(raw, decimals: int):
    if raw in ("", None):
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n / (10 ** decimals) if decimals > 0 else n



def _dig(data: dict, *keys, default=None):
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key)
        if data is None:
            return default
    return data


def _get_breakfast(rate: dict) -> str:
    val = rate.get("displayNumBreakfastIncluded", rate.get("numBreakfastIncluded"))
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return "Breakfast Included" if int(val) > 0 else "Breakfast not Included"


def _parse_rate(room_name: str, rate: dict) -> dict:
    d = _get_decimals(rate)

    def p(v):
        return _fmt_price(v, d)

    rate_name = rate.get("inventoryName") or room_name

    per_night = _dig(rate, "finalPrice", "perRoomPerNightDisplay") or {}

    return {
        "room_name": room_name,
        "rate_name": rate_name,
        "shown_currency": _dig(rate, "rateDisplay", "totalFare", "currency", default=""),
        "shown_price": {"rate name": rate_name},
        "net_price": p(_dig(rate, "rateDisplay", "baseFare", "amount")),
        "cancellation policy": _dig(
            rate, "roomCancellationPolicy", "providerCancellationPolicyString"
        ),
        "breakfast": _get_breakfast(rate),
        "number_of_guests": str(rate.get("maxOccupancy", "")),
        "taxes_amount": p(_dig(rate, "rateDisplay", "taxes", "amount")),
        "total_price": p(_dig(rate, "rateDisplay", "totalFare", "amount")),
        "original_price": p(_dig(rate, "originalRateDisplay", "totalFare", "amount")),
        "shown_price_per_stay": p(_dig(per_night, "inclusiveFinalPrice", "amount")),
        "net_price_per_stay": p(_dig(per_night, "exclusiveFinalPrice", "amount")),
        "total_price_per_stay": p(_dig(per_night, "totalFare", "amount")),
    }


def parse_rates(response_data: dict) -> list[dict]:
    rates = []
    for entry in (_dig(response_data, "data", "recommendedEntries") or []):
        room_name = entry.get("name", "")
        for inv in entry.get("hotelRoomInventoryList", []):
            rates.append(_parse_rate(room_name, inv))
    return rates




def main():
    deeplink = build_deeplink()
    print(f"Deep link: {deeplink}\n")

    session_data = capture_session(deeplink)

    print("\nReplaying API request...")
    response_data = replay_request(session_data, deeplink)

    rates = parse_rates(response_data)

    if not rates:
        print("\nWarning: no rates extracted")
        raise SystemExit(1)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"rates": rates}, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(rates)} rates to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
