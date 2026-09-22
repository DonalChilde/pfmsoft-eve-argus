"""Define the primary EVE Online market hubs."""

from dataclasses import dataclass


@dataclass
class MarketHub:
    region_id: int
    region_name: str
    system_id: int
    system_name: str
    station_id: int
    station_name: str


MARKET_HUBS: list[MarketHub] = [
    MarketHub(
        region_id=10000002,
        region_name="The Forge",
        system_id=30000142,
        system_name="Jita",
        station_id=60003760,
        station_name="Jita IV - Moon 4 - Caldari Navy Assembly Plant",
    ),
    MarketHub(
        region_id=10000043,
        region_name="Domain",
        system_id=30002187,
        system_name="Amarr",
        station_id=60008494,
        station_name="Amarr VIII (Oris) - Emperor Family Academy",
    ),
    MarketHub(
        region_id=10000032,
        region_name="Sinq Laison",
        system_id=30002659,
        system_name="Dodixie",
        station_id=60011866,
        station_name="Dodixie IX - Moon 20 - Federation Navy Assembly Plant",
    ),
    MarketHub(
        region_id=10000042,
        region_name="Metropolis",
        system_id=30002053,
        system_name="Hek",
        station_id=60005686,
        station_name="Hek VIII - Moon 12 - Boundless Creation Factory",
    ),
    MarketHub(
        region_id=10000030,
        region_name="Heimatar",
        system_id=30002510,
        system_name="Rens",
        station_id=60004588,
        station_name="Rens VI - Moon 8 - Brutor Tribe Treasury",
    ),
]
