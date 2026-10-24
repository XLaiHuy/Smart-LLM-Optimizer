from app.config import Settings
from app.providers.catalog import Catalog
from app.providers.openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, key: str, catalog: Catalog, settings: Settings | None = None):
        super().__init__(default_key=key, catalog=catalog, settings=settings)
