"""DataSource contract: symbol listing, range slicing, error paths, snapshot hashing."""

import pytest

from engine.datasource import CSVDataSource, DataSourceError, data_snapshot_hash


def test_symbols_lists_fixtures(data_dir):
    syms = CSVDataSource(data_dir).symbols()
    assert "SPY" in syms and "BTC-USD" in syms


def test_unknown_symbol_raises(data_dir):
    with pytest.raises(DataSourceError):
        CSVDataSource(data_dir).load("NOPE")


def test_empty_range_raises(data_dir):
    with pytest.raises(DataSourceError):
        CSVDataSource(data_dir).load("SPY", start="2100-01-01")


def test_load_slices_inclusive_and_canonical(data_dir):
    df = CSVDataSource(data_dir).load("SPY", start="2019-01-01", end="2019-12-31")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert str(df.index.min().date()) >= "2019-01-01"
    assert str(df.index.max().date()) <= "2019-12-31"
    assert df.index.is_monotonic_increasing


def test_snapshot_hash_deterministic_and_sensitive(data_dir):
    src = CSVDataSource(data_dir)
    a = src.load("SPY", end="2019-06-01")
    b = src.load("SPY", end="2019-06-01")
    assert data_snapshot_hash(a) == data_snapshot_hash(b)
    # A different window must produce a different fingerprint.
    c = src.load("SPY", end="2019-07-01")
    assert data_snapshot_hash(a) != data_snapshot_hash(c)
