from __future__ import annotations

import tiktoken

from ds1000_harness.models import RetrievedItem

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def pack_context(
    items: tuple[RetrievedItem, ...],
    *,
    token_budget: int,
) -> tuple[str, int]:
    if token_budget < 1:
        raise ValueError("token_budget must be positive")

    packed: list[int] = []
    for item in items:
        header = f"### {item.path}\n" if item.path else "### Retrieved context\n"
        block = _TOKENIZER.encode(header + item.content.strip() + "\n\n")
        remaining = token_budget - len(packed)
        if remaining <= 0:
            break
        packed.extend(block[:remaining])
        if len(block) > remaining:
            break
    return _TOKENIZER.decode(packed).strip(), len(packed)


def identifier_hit(context: str, identifiers: tuple[str, ...]) -> bool:
    normalized = context.casefold()
    return any(identifier.casefold() in normalized for identifier in identifiers)
