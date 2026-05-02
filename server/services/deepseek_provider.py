from __future__ import annotations

from server.services.openai_provider import OpenAIProvider
from server.services.provider import ProviderConfig, ProviderType


class DeepSeekProvider(OpenAIProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.name = ProviderType.DEEPSEEK.value
        if not config.base_url:
            self.config.base_url = "https://api.deepseek.com"
        if not config.model:
            self.config.model = "deepseek-v4-flash"

    def supports_thinking(self) -> bool:
        return False

    def get_default_model(self) -> str:
        return "deepseek-v4-flash"
