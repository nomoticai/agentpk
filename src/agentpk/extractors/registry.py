"""Extractor registry for language-specific signal extractors."""

from __future__ import annotations

from typing import Optional

from .base import ExtractorBase


class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: dict[str, ExtractorBase] = {}

    def register(self, extractor: ExtractorBase) -> None:
        self._extractors[extractor.language] = extractor

    def get(self, language: str) -> Optional[ExtractorBase]:
        return self._extractors.get(language.lower())

    def supported_languages(self) -> list[str]:
        return list(self._extractors.keys())


# Global registry -- populated at module import time
_registry = ExtractorRegistry()


def get_extractor(language: str) -> Optional[ExtractorBase]:
    return _registry.get(language)


def register_extractor(extractor: ExtractorBase) -> None:
    _registry.register(extractor)


def supported_languages() -> list[str]:
    return _registry.supported_languages()
