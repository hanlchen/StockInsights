from abc import ABC, abstractmethod
from typing import Any, Optional


class Cache(ABC):
    """
    Cache interface. MVP ships MemoryCache; swap in RedisCache later
    without touching any calling code — this is one of the two
    interfaces worth over-investing in per the architecture doc.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int) -> None:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...
