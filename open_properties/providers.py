"""Provider registry: one source of truth for CLI, MCP and documentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple, Type

from .portals.base import PortalAdapter
from .portals.crea import CREAAdapter
from .portals.daft import DaftAdapter
from .portals.domain import DomainAdapter
from .portals.espc import ESPCAdapter
from .portals.idealista import IdealistaAdapter
from .portals.immoscout24 import ImmoScout24Adapter
from .portals.rentcast import RentCastAdapter
from .portals.rightmove import RightmoveAdapter
from .portals.zoopla import ZooplaAdapter


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    countries: Tuple[str, ...]
    transactions: Tuple[str, ...]
    auth: str
    access: str
    notes: str
    adapter: Type[PortalAdapter]

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("adapter", None)
        data["countries"] = list(self.countries)
        data["transactions"] = list(self.transactions)
        return data


PROVIDERS: Dict[str, ProviderInfo] = {
    "rightmove": ProviderInfo("rightmove", "Rightmove", ("GB",), ("sale", "rent"), "none", "live", "Embedded storefront JSON; no key", RightmoveAdapter),
    "espc": ProviderInfo("espc", "ESPC", ("GB",), ("sale",), "none", "live", "Edinburgh and Lothians specialist", ESPCAdapter),
    "zoopla": ProviderInfo("zoopla", "Zoopla", ("GB",), ("sale", "rent"), "Firecrawl", "optional", "Cloudflare requires the optional Firecrawl CLI", ZooplaAdapter),
    "daft": ProviderInfo("daft", "Daft.ie", ("IE",), ("sale", "rent"), "none", "live", "Anonymous web JSON API", DaftAdapter),
    "domain": ProviderInfo("domain", "Domain", ("AU",), ("sale", "rent"), "client credentials", "official", "Official developer API; DOMAIN_CLIENT_ID and DOMAIN_CLIENT_SECRET", DomainAdapter),
    "idealista": ProviderInfo("idealista", "Idealista", ("ES", "IT", "PT"), ("sale", "rent"), "client credentials", "official", "Official API; IDEALISTA_API_KEY and IDEALISTA_API_SECRET", IdealistaAdapter),
    "rentcast": ProviderInfo("rentcast", "RentCast", ("US",), ("sale", "rent"), "API key", "official", "Nationwide listings API; self-serve RENTCAST_API_KEY", RentCastAdapter),
    "crea-ddf": ProviderInfo("crea-ddf", "REALTOR.ca DDF", ("CA",), ("sale", "rent"), "data-feed credentials", "official", "Official CREA DDF API; requires an active DDF feed", CREAAdapter),
    "immoscout24": ProviderInfo("immoscout24", "ImmoScout24", ("DE",), ("sale", "rent"), "none", "live", "Anonymous mobile search API; no key", ImmoScout24Adapter),
}

ADAPTERS = {provider_id: info.adapter for provider_id, info in PROVIDERS.items()}


def list_providers(country: str = "") -> List[dict]:
    country = country.upper()
    return [info.to_dict() for info in PROVIDERS.values() if not country or country in info.countries]


def provider_ids_for(country: str, transaction: str = "sale") -> List[str]:
    country = country.upper()
    transaction = transaction.lower()
    return [provider_id for provider_id, info in PROVIDERS.items() if country in info.countries and transaction in info.transactions]


def validate_provider(provider_id: str, country: str, transaction: str) -> None:
    if provider_id not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_id}")
    info = PROVIDERS[provider_id]
    if country.upper() not in info.countries:
        raise ValueError(f"{info.name} does not support country {country.upper()}")
    if transaction.lower() not in info.transactions:
        raise ValueError(f"{info.name} does not support {transaction.lower()} listings")
