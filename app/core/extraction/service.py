import ollama
from pydantic import ValidationError

from app.core.extraction.extractor import _run_extraction_pass
from app.core.extraction.models import ExtractionResult


class EntityExtractor:
    async def extract_entities(
        self,
        *,
        message: str,
        handler_name: str,
    ) -> ExtractionResult:
        """Extract entities without making or revising a routing decision."""
        try:
            parsed = await _run_extraction_pass(message, handler_name)
            parsed.intent = handler_name
            return ExtractionResult(value=parsed, source="llm")
        except TimeoutError:
            return ExtractionResult(error="timeout", source="llm")
        except ValidationError:
            return ExtractionResult(error="validation_error", source="llm")
        except (ollama.RequestError, ollama.ResponseError):
            return ExtractionResult(error="parsing_error", source="llm")
