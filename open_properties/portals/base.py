"""Provider adapter interface shared by every country."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SearchConfig:
    country: str = "GB"
    transaction: str = "sale"
    min_beds: int = 1
    max_beds: Optional[int] = None
    min_baths: Optional[int] = None
    max_baths: Optional[int] = None
    min_price: str = ""
    max_price: str = ""
    property_types: str = ""
    location: str = "edinburgh"
    location_id: str = ""
    max_pages: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.country = (self.country or "GB").upper()
        self.transaction = (self.transaction or "sale").lower()
        if self.transaction not in {"sale", "rent"}:
            raise ValueError("transaction must be sale or rent")


class PortalAdapter:
    name = "base"
    parser_version = "0"

    def search(self, config: SearchConfig) -> Dict[str, Any]:
        raise NotImplementedError
