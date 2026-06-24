from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
RULES_PATH = PROJECT_ROOT / "assets" / "fm_abhaya_rules.json"
SINHALA_START = "\u0d80"
SINHALA_END = "\u0dff"


@dataclass(frozen=True)
class FontConversionResult:
    text: str
    warnings: list[str]


def load_rules() -> list[tuple[str, str]]:
    with RULES_PATH.open(encoding="utf-8") as file:
        raw_rules = json.load(file)
    return [(rule["pattern"], rule["replacement"]) for rule in raw_rules]


RULES = load_rules()
ASCII_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")


def contains_sinhala(text: str) -> bool:
    """True if the text has any Sinhala Unicode characters."""
    return any(SINHALA_START <= char <= SINHALA_END for char in text)


def unicode_to_fm(text: str) -> FontConversionResult:
    protected_text, protected_values = protect_ascii_words(text)
    converted = protected_text
    for pattern, replacement in RULES:
        converted = converted.replace(pattern, replacement)
    converted = restore_ascii_words(converted, protected_values)
    converted = converted.replace("\u200d", "").replace("\u200b", "")

    warnings = []
    leftovers = sorted({char for char in converted if SINHALA_START <= char <= SINHALA_END})
    if leftovers:
        warnings.append(
            "Some Sinhala characters may not have converted cleanly: "
            + " ".join(leftovers[:12])
        )

    return FontConversionResult(text=converted, warnings=warnings)


def protect_ascii_words(text: str) -> tuple[str, list[str]]:
    values: list[str] = []

    def replace(match: re.Match[str]) -> str:
        values.append(match.group(0))
        return f"\ue000{len(values) - 1}\ue001"

    return ASCII_WORD_PATTERN.sub(replace, text), values


def restore_ascii_words(text: str, values: list[str]) -> str:
    for index, value in enumerate(values):
        text = text.replace(f"\ue000{index}\ue001", value)
    return text
