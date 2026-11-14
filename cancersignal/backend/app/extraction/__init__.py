"""Independent clinical extraction; no database or pipeline integration."""

from app.extraction.service import ClinicalExtractor

__all__ = ["ClinicalExtractor"]
