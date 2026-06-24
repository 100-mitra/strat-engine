"""Bridge from Django settings to the framework-free engine DataSource."""

from __future__ import annotations

from django.conf import settings

from engine.datasource import CSVDataSource


def get_data_source() -> CSVDataSource:
    return CSVDataSource(settings.DATA_DIR)


def available_symbols() -> list[str]:
    return get_data_source().symbols()
