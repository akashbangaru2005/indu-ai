"""Read-only live information from fixed public providers; never fabricate a fallback."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from xml.etree import ElementTree

import httpx


class LiveInformation:
    @staticmethod
    def recognizes(command):
        original = command.strip().rstrip(".!?")
        text = original.casefold()
        return bool(re.fullmatch(
            r"(?:(?:what(?: is|'s| are)|tell me|show me|show)\s+)?(?:the\s+)?(?:"
            r"(?:current |latest )?(?:bitcoin|btc|ethereum|eth)(?:'s)?\s+price(?:\s+(?:right now|now|today))?|"
            r"(?:today'?s |current )?weather(?: today)?(?:\s+in\s+.+)?|"
            r"(?:current )?time(?:\s+in\s+.+)?|(?:the )?latest (?:technology|tech) news)", text))

    async def execute(self, command):
        def checked():
            return datetime.now(timezone.utc).isoformat(timespec="seconds")
        text = command.casefold().strip().rstrip(".!?")
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
                if re.search(r"\b(?:bitcoin|btc|ethereum|eth)\b", text):
                    product = "BTC-USD" if re.search(r"\b(?:bitcoin|btc)\b", text) else "ETH-USD"
                    response = await client.get(f"https://api.exchange.coinbase.com/products/{product}/ticker")
                    response.raise_for_status()
                    data = response.json()
                    price = float(data["price"])
                    return f"{product}: ${price:,.2f} USD. Source: Coinbase Exchange (last trade, {data['time']}); retrieved {checked()}."
                if "weather" in text:
                    location = re.search(r"\bin\s+(.+)", text)
                    if not location:
                        return "Which city should I check? For example, ‘What is the weather in Hyderabad?’"
                    response = await client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name":location[1][:100], "count":1, "language":"en", "format":"json"})
                    response.raise_for_status()
                    places = response.json().get("results", [])
                    if not places:
                        return "I could not find that city. Try a city name and check the spelling."
                    place = places[0]
                    response = await client.get("https://api.open-meteo.com/v1/forecast", params={
                        "latitude":place["latitude"], "longitude":place["longitude"], "current":"temperature_2m,relative_humidity_2m,wind_speed_10m", "timezone":"auto"})
                    response.raise_for_status()
                    data = response.json()
                    current = data["current"]
                    return f"{place['name']}, {place.get('country', '')}: {current['temperature_2m']} °C, humidity {current['relative_humidity_2m']}%, wind {current['wind_speed_10m']} km/h. Source: Open-Meteo modelled current conditions, {current['time']} {data['timezone']}; retrieved {checked()}. Location: GeoNames."
                if "news" in text:
                    response = await client.get("https://feeds.bbci.co.uk/news/technology/rss.xml")
                    response.raise_for_status()
                    if len(response.content) > 2_000_000:
                        raise ValueError("Oversized news feed")
                    feed = ElementTree.fromstring(response.content)
                    items = feed.findall("./channel/item")[:5]
                    if not items:
                        raise ValueError("No current headlines")
                    return f"BBC Technology headlines, retrieved {checked()}:\n" + "\n".join(f"• {item.findtext('title')} ({item.findtext('pubDate')}) — {item.findtext('link')}" for item in items)
                location = re.search(r"\bin\s+(.+)", text)
                name = location[1] if location else "utc"
                zones = {"paris":"Europe/Paris", "london":"Europe/London", "new york":"America/New_York", "india":"Asia/Kolkata", "hyderabad":"Asia/Kolkata", "tokyo":"Asia/Tokyo", "utc":"UTC"}
                zone = zones.get(name, name)
                # Retain canonical IANA case supplied by the user.
                if name not in zones and location:
                    zone = command.strip()[location.start(1):].strip().rstrip(".!?")
                value = datetime.now(ZoneInfo(zone))
                return f"The time in {zone} is {value.strftime('%A, %d %B %Y, %I:%M:%S %p %Z')}. Source: this computer's clock and IANA time zone data; checked {checked()}."
        except ZoneInfoNotFoundError:
            return "Choose a known city such as Paris, London or Tokyo, or an IANA timezone such as Europe/Paris."
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ElementTree.ParseError):
            raise RuntimeError("The live information provider is unavailable or returned incomplete data. No current value was invented; try again later.") from None
