from typing import Protocol


class LLMInterface(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError
