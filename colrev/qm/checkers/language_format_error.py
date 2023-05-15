#! /usr/bin/env python
"""Checker for language-format-error."""
from __future__ import annotations

import colrev.exceptions as colrev_exceptions
import colrev.qm.quality_model
import colrev.record

# pylint: disable=too-few-public-methods


class LanguageFormatChecker:
    """The LanguageFormatChecker"""

    def __init__(self, quality_model: colrev.qm.quality_model.QualityModel) -> None:
        self.quality_model = quality_model
        self.language_service = colrev.env.language_service.LanguageService()

    def run(self, *, record: colrev.record.Record) -> None:
        """Run the language-format-error checks"""

        if "language" not in record.data:
            return

        try:
            self.language_service.validate_iso_639_3_language_codes(
                lang_code_list=[record.data["language"]]
            )
        except colrev_exceptions.InvalidLanguageCodeException:
            record.add_masterdata_provenance_note(
                key="language", note="language-format-error"
            )
        else:
            record.remove_masterdata_provenance_note(
                key="language", note="language-format-error"
            )


def register(quality_model: colrev.qm.quality_model.QualityModel) -> None:
    """Register the checker"""
    quality_model.register_checker(LanguageFormatChecker(quality_model))
