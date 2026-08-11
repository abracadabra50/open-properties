from .base import PortalAdapter, SearchConfig
from .daft import DaftAdapter
from .crea import CREAAdapter
from .domain import DomainAdapter
from .espc import ESPCAdapter
from .idealista import IdealistaAdapter
from .immoscout24 import ImmoScout24Adapter
from .rentcast import RentCastAdapter
from .rightmove import RightmoveAdapter
from .zoopla import ZooplaAdapter

__all__ = [
    "PortalAdapter", "SearchConfig", "CREAAdapter", "DaftAdapter", "DomainAdapter", "ESPCAdapter",
    "IdealistaAdapter", "ImmoScout24Adapter", "RentCastAdapter", "RightmoveAdapter", "ZooplaAdapter",
]
