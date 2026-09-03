from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

from src.tools.schemas import ToolResult


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    args_schema: Optional[type[BaseModel]] = None

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        pass

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        """Turns the LLM's raw ARGS string into a dict of field values, ready
        for args_schema validation. Default: no args. Override per tool for
        pipe-delimited or single-value formats."""
        return {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description
        }