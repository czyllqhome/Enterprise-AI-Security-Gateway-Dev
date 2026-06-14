from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], model: str) -> str:
        raise NotImplementedError
