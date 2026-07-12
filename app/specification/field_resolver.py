import re

from app.constants import FIELD_KEYWORD_ALIASES


def _build_alias_patterns() -> tuple[tuple[re.Pattern, str, tuple[str, ...]], ...]:
    alias_fields: dict[str, list[str]] = {}
    for field, aliases in FIELD_KEYWORD_ALIASES.items():
        for alias in aliases:
            alias_fields.setdefault(alias.casefold(), []).append(field)

    return tuple(
        (
            re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)"),
            alias,
            tuple(fields),
        )
        for alias, fields in sorted(
            alias_fields.items(), key=lambda item: len(item[0]), reverse=True
        )
    )


_ALIAS_PATTERNS = _build_alias_patterns()


def resolve_explicit_spec_detail(message: str) -> str | None:
    """Return the specification detail explicitly named in a user message.

    A unique alias resolves to its canonical data field. If an alias intentionally
    belongs to multiple fields, keep the user's alias so downstream code can
    return every relevant value.
    """
    normalized_message = message.casefold()
    for pattern, alias, fields in _ALIAS_PATTERNS:
        if pattern.search(normalized_message):
            return fields[0] if len(fields) == 1 else alias

    return None
