import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.mojmojster.net/povprasevanja/montaza_pohistva"
STATE_FILE = Path("seen-listings.json")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15"
    ),
    "Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_listings(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    listings = {}

    for link in soup.select('a[href*="/povprasevanja/montaza_pohistva/"]'):
        title = clean_text(link.get_text(" ", strip=True))
        href = urljoin(SOURCE_URL, link.get("href", ""))
        if not title or not href or href.rstrip("/") == SOURCE_URL.rstrip("/"):
            continue
        container = link
        for _ in range(4):
            if container.parent:
                container = container.parent

        details = clean_text(container.get_text(" ", strip=True))
        date_match = re.search(r"\b\d{1,2}\.\d{1,2}\.\d{2}\b", details)
        date = date_match.group(0) if date_match else ""
        location = details.split(title, 1)[0].strip(" -") if title in details else ""
        location = location[-100:] if location else "Lokacija ni navedena"

        listings[href] = {
            "title": title,
            "url": href,
            "date": date,
            "location": location,
        }

    return list(listings.values())


def load_seen() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(urls: set[str]) -> None:
    STATE_FILE.write_text(
        json.dumps(sorted(urls), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def send_to_discord(listings: list[dict[str, str]]) -> None:
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL GitHub Secret is missing")

    embeds = []
    for listing in listings[:10]:
        embeds.append(
            {
                "title": listing["title"][:256],
                "url": listing["url"],
                "description": (
                    f"**Lokacija:** {listing['location']}\n"
                    f"**Objavljeno:** {listing['date'] or 'ni navedeno'}"
                ),
                "color": 0x6BC90E,
            }
        )

    if len(listings) > 10:
        embeds[-1]["footer"] = {"text": f"In še {len(listings) - 10} novih oglasov."}

    response = requests.post(
        WEBHOOK_URL,
        json={
            "username": "Montaže - MojMojster",
            "content": f"Novi relevantni oglasi za montažo pohištva: **{len(listings)}**",
            "embeds": embeds,
        },
        timeout=20,
    )
    response.raise_for_status()


def main() -> None:
    response = requests.get(SOURCE_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()

    listings = parse_listings(response.text)
    seen = load_seen()
    new_listings = [listing for listing in listings if listing["url"] not in seen]

    if not seen:
        # First run creates a baseline instead of flooding Discord with old listings.
        save_seen({listing["url"] for listing in listings})
        print(f"Baseline created with {len(listings)} listings.")
        return

    if new_listings:
        send_to_discord(new_listings)
        print(f"Sent {len(new_listings)} new listings to Discord.")
    else:
        print("No new listings found.")

    save_seen(seen | {listing["url"] for listing in listings})


if __name__ == "__main__":
    main()
