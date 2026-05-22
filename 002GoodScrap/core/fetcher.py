"""PriceFetcher - fetch gold prices from JD Finance API."""
import json
import requests
from dataclasses import dataclass, field

AU_URL = "https://ms.jr.jd.com/gw2/generic/CreatorSer/pc/m/pcQueryGoldProduct"
XAU_URL = "https://ms.jr.jd.com/gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache"
TIMEOUT = 5
HEADERS = {"Origin": "https://jdjr.jd.com", "Referer": "https://jdjr.jd.com/"}


@dataclass
class PriceData:
    symbol: str
    name: str
    price: float
    change_pct: float


class PriceFetcher:
    """Fetch AU (沪金) and XAUUSD (国际金) from JD Finance."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._prev_au: float = 0.0
        self._prev_xau: float = 0.0

    def fetch_all(self) -> dict[str, PriceData | None]:
        results: dict[str, PriceData | None] = {}
        results["AU"] = self._fetch_au()
        results["XAU"] = self._fetch_xau()
        return results

    def _fetch_au(self) -> PriceData | None:
        try:
            resp = self._session.get(
                AU_URL,
                params={"reqData": '{"goldType":"2"}'},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            price = float(resp.json()["resultData"]["data"]["priceValue"])
            return self._build_data("AU", "沪金9999", price, self._prev_au)
        except Exception:
            return None

    def _fetch_xau(self) -> PriceData | None:
        try:
            resp = self._session.post(
                XAU_URL,
                json={"ticket": "jd-jr-pc", "uniqueCode": "WG-XAUUSD"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            inner = json.loads(resp.json()["resultData"]["data"])
            price = float(inner["lastPrice"])
            return self._build_data("XAU", "国际金", price, self._prev_xau)
        except Exception:
            return None

    def _build_data(self, symbol: str, name: str, price: float, prev: float) -> PriceData:
        if prev > 0:
            change_pct = round((price - prev) / prev * 100, 2)
        else:
            change_pct = 0.0

        if symbol == "AU":
            self._prev_au = price
        else:
            self._prev_xau = price

        return PriceData(symbol=symbol, name=name, price=price, change_pct=change_pct)
