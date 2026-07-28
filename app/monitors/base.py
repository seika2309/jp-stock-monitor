from abc import ABC, abstractmethod
from app.models import Product

class BaseMonitor(ABC):
    site: str

    @abstractmethod
    async def collect(self) -> list[Product]:
        ...
