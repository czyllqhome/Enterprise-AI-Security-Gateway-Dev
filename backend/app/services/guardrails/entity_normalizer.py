import re

from ...schemas.guardrail import GuardrailEntity
from .masking import mask_value


def _normalize_entity_type(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    normalized = normalized.removesuffix("_RE")
    return normalized or "SENSITIVE_VALUE"


def normalize_entities(entities: list[dict]) -> list[GuardrailEntity]:
    grouped: dict[tuple[int, int, str, str], dict] = {}
    counters: dict[str, int] = {}

    for entity in sorted(entities, key=lambda item: (item["start"], item["end"], item["type"])):
        normalized_type = _normalize_entity_type(entity["type"])
        key = (entity["start"], entity["end"], entity["original"], normalized_type)
        current = grouped.setdefault(
            key,
            {
                "type": normalized_type,
                "original": entity["original"],
                "start": entity["start"],
                "end": entity["end"],
                "source": entity["source"],
                "sources": [],
            },
        )
        for source in [*entity.get("sources", []), entity.get("source")]:
            if source and source not in current["sources"]:
                current["sources"].append(source)

    normalized: list[GuardrailEntity] = []
    for entity in sorted(grouped.values(), key=lambda item: (item["start"], item["end"])):
        entity_type = _normalize_entity_type(entity["type"])
        counters[entity_type] = counters.get(entity_type, 0) + 1
        sources = sorted(
            entity["sources"],
            key=lambda source: (
                0 if source == "privacy_filter" else 1 if source == "llm_guard_secrets" else 2 if source == "llm_guard" else 3,
                source,
            ),
        )
        normalized.append(
            GuardrailEntity(
                type=entity_type,
                original=entity["original"],
                masked=mask_value(entity["original"]),
                replacement=f"[REDACTED_{entity_type}_{counters[entity_type]}]",
                start=entity["start"],
                end=entity["end"],
                source=sources[0],
                sources=sources,
            )
        )

    return normalized
