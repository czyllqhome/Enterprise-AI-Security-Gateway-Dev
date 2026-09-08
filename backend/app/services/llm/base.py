from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    def validate_attachments(self, messages: list[dict], model: str) -> None:
        if any(message.get("attachments") for message in messages):
            raise ValueError("Original-file input is not supported by this provider adapter.")

    @abstractmethod
    def chat(self, messages: list[dict], model: str) -> str:
        raise NotImplementedError

    def stream_chat(self, messages: list[dict], model: str):
        yield self.chat(messages, model)
