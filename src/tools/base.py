from abc import ABC, abstractmethod

class BaseTool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def run(self, **kwargs) -> str:
        pass

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description
        }