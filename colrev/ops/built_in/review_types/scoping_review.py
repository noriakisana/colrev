#! /usr/bin/env python
"""Scoping review"""
from dataclasses import dataclass

import zope.interface
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.ops.search
import colrev.record

# pylint: disable=unused-argument
# pylint: disable=duplicate-code
# pylint: disable=too-few-public-methods


@zope.interface.implementer(
    colrev.env.package_manager.ReviewTypePackageEndpointInterface
)
@dataclass
class ScopingReview(JsonSchemaMixin):
    """Scoping review"""

    settings_class = colrev.env.package_manager.DefaultSettings

    def __init__(
        self, *, operation: colrev.operation.CheckOperation, settings: dict
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)

    def __str__(self) -> str:
        return "scoping review"

    def initialize(
        self, settings: colrev.settings.Settings
    ) -> colrev.settings.Settings:
        """Initialize a scoping review"""

        settings.data.data_package_endpoints = [
            {"endpoint": "colrev_built_in.prisma", "version": "1.0"},
            {
                "endpoint": "colrev_built_in.obsidian",
                "version": "0.1",
                "config": {},
            },
            {
                "endpoint": "colrev_built_in.paper_md",
                "version": "1.0",
                "word_template": "APA-7.docx",
            },
        ]
        return settings


if __name__ == "__main__":
    pass
