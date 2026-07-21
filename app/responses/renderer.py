import yaml
from pathlib import Path

from .codes import ResponseCode

class MessageCatalog:
    def __init__(self, locales_dir: Path | str):
        self._locales_dir = Path(locales_dir)
        self._cache: dict[str, dict[str, str]] = {}

    def get(self, code: ResponseCode, locale: str = "vi") -> str:
        if locale not in self._cache:
            self._load_locale(locale)
            
        messages = self._cache.get(locale, {})
        
        if code.value not in messages:
            return f"[{code.value}]"
            
        return messages[code.value]

    def _load_locale(self, locale: str) -> None:
        file_path = self._locales_dir / f"{locale}.yaml"
        if not file_path.exists():
            self._cache[locale] = {}
            return
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            self._cache[locale] = data or {}


class ResponseRenderer:
    def __init__(self, message_catalog: MessageCatalog) -> None:
        self._message_catalog = message_catalog

    def render(
        self,
        code: ResponseCode,
        *,
        locale: str = "vi",
        facts: dict[str, object] | None = None,
    ) -> str:
        template = self._message_catalog.get(code=code, locale=locale)
        
        if not facts:
            return template.strip()
            
        try:
            return template.format(**facts).strip()
        except KeyError:
            # Fallback if the facts don't contain the expected keys
            return template.strip()

# Create a default instance for easy access across the app
import os
_locales_path = Path(os.path.dirname(__file__)) / "locales"
default_catalog = MessageCatalog(_locales_path)
response_renderer = ResponseRenderer(default_catalog)
