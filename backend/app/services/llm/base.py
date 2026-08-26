from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], model: str) -> str:
        raise NotImplementedError

    def stream_chat(self, messages: list[dict], model: str):
        yield self.chat(messages, model)
