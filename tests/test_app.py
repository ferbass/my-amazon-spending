"""Unit tests for the pure-logic helpers in app.py."""
import csv
import os

import pandas as pd
import pytest

import app


# --------------------------------------------------------------------------- #
# _normalize_amount
# --------------------------------------------------------------------------- #

def test_normalize_amount_strips_commas():
    s = pd.Series(["2,524", "5,980", "836"])
    out = app._normalize_amount(s)
    assert out.tolist() == [2524.0, 5980.0, 836.0]


def test_normalize_amount_strips_currency_symbols():
    s = pd.Series(["¥2,524", "$1,000", "  3,000  "])
    out = app._normalize_amount(s)
    assert out.tolist() == [2524.0, 1000.0, 3000.0]


def test_normalize_amount_coerces_non_numeric_to_zero():
    s = pd.Series(["", "Not Available", "abc", "1,234"])
    out = app._normalize_amount(s)
    assert out.tolist() == [0.0, 0.0, 0.0, 1234.0]


def test_normalize_amount_works_on_arrow_string_dtype():
    """Regression: pandas 3.0 defaults to Arrow-backed strings, dtype != object.

    Previously _normalize_amount short-circuited unless dtype was 'object',
    which produced ¥154,687 instead of ¥4,705,839 in the dashboard.
    """
    s = pd.Series(["2,524", "5,980"], dtype="string")
    out = app._normalize_amount(s)
    assert out.tolist() == [2524.0, 5980.0]


# --------------------------------------------------------------------------- #
# _categorize_series
# --------------------------------------------------------------------------- #

@pytest.fixture
def sample_rules():
    return {
        "Subscriptions": ["prime", "audible"],
        "Books": ["book", "kindle"],
        "Electronics": ["usb", "battery", "ケーブル"],
    }


def test_categorize_first_match_wins(sample_rules):
    # "Kindle book" hits both Books (kindle/book) — Books listed before Electronics
    names = pd.Series(["Prime renewal", "USB-C cable", "ケーブル 1m", "Random item"])
    out = app._categorize_series(names, sample_rules)
    assert out.tolist() == ["Subscriptions", "Electronics", "Electronics", "Other"]


def test_categorize_priority_order(sample_rules):
    # "Audible Prime" would match Subscriptions on either keyword.
    # If we swap order, the first matching category wins.
    swapped = {"Books": ["audible"], **sample_rules}  # Books first, with audible
    names = pd.Series(["Audible book"])
    assert app._categorize_series(names, swapped).tolist() == ["Books"]


def test_categorize_case_insensitive(sample_rules):
    names = pd.Series(["KINDLE Paperwhite", "kindle paperwhite", "Kindle"])
    out = app._categorize_series(names, sample_rules)
    assert out.tolist() == ["Books", "Books", "Books"]


def test_categorize_escapes_regex_specials():
    # A naive (?:a|b|c) join would explode on keywords like "C++" or "(set)".
    rules = {"Special": ["C++", "(set)", "1.5L"]}
    names = pd.Series(["C++ programming book", "Cookware (set)", "Water 1x5L", "Water 1.5L"])
    out = app._categorize_series(names, rules)
    assert out.tolist() == ["Special", "Special", "Other", "Special"]


def test_categorize_handles_japanese(sample_rules):
    names = pd.Series(["USB-Cケーブル 2m", "サンペレグリノ 炭酸水"])
    out = app._categorize_series(names, sample_rules)
    # Both have ケーブル... wait the second doesn't. Only first should hit Electronics.
    assert out.tolist() == ["Electronics", "Other"]


def test_categorize_empty_or_missing_name(sample_rules):
    names = pd.Series(["", None, pd.NA])
    out = app._categorize_series(names, sample_rules)
    assert out.tolist() == ["Other", "Other", "Other"]


def test_categorize_with_empty_rules():
    names = pd.Series(["anything"])
    assert app._categorize_series(names, {}).tolist() == ["Other"]


# --------------------------------------------------------------------------- #
# Loaders — Order History, Digital, Cancelled, Refunds
# --------------------------------------------------------------------------- #

PHYSICAL_HEADER = [
    "ASIN", "Order Date", "Order ID", "Order Status", "Product Name",
    "Total Amount",
]


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_load_physical_returns_none_when_file_missing(tmp_path):
    assert app._load_physical(str(tmp_path / "missing.csv")) is None


def test_load_physical_drops_cancelled(tmp_path):
    path = tmp_path / "orders.csv"
    _write_csv(path, PHYSICAL_HEADER, [
        ["B001", "2024-01-01T00:00:00Z", "OID-1", "Closed", "Item A", "1,000"],
        ["B002", "2024-02-01T00:00:00Z", "OID-2", "Cancelled", "Item B", "2,000"],
        ["B003", "2024-03-01T00:00:00Z", "OID-3", "Closed", "Item C", "3,000"],
    ])
    df = app._load_physical(str(path))
    assert len(df) == 2
    assert df["Source"].unique().tolist() == ["Physical"]
    assert df["Total Amount"].tolist() == [1000.0, 3000.0]


def test_load_physical_parses_millisecond_iso8601(tmp_path):
    """Cancelled-row dates sometimes have milliseconds — must still parse."""
    path = tmp_path / "orders.csv"
    _write_csv(path, PHYSICAL_HEADER, [
        ["B001", "2025-09-18T15:54:25.230Z", "OID-1", "Closed", "Item A", "100"],
    ])
    df = app._load_physical(str(path))
    assert df["Order Date"].iloc[0].year == 2025


DIGITAL_HEADER = [
    "ASIN", "Order Date", "Order ID", "Order Status", "Product Name",
    "Transaction Amount",
]


def test_load_digital_keeps_only_success(tmp_path):
    path = tmp_path / "digital.csv"
    _write_csv(path, DIGITAL_HEADER, [
        ["B100", "2024-01-01T00:00:00Z", "D-1", "SUCCESS", "Prime", "600"],
        ["B101", "2024-02-01T00:00:00Z", "D-2", "FAILURE", "Failed buy", "1000"],
        ["B102", "2024-03-01T00:00:00Z", "D-3", "SUCCESS", "Kindle book", "1200"],
    ])
    df = app._load_digital(str(path))
    assert len(df) == 2
    assert df["Source"].unique().tolist() == ["Digital"]
    assert df["Total Amount"].tolist() == [600.0, 1200.0]


def test_load_cancelled_returns_only_cancelled_rows(tmp_path):
    path = tmp_path / "orders.csv"
    _write_csv(path, PHYSICAL_HEADER, [
        ["B001", "2024-01-01T00:00:00Z", "OID-1", "Closed", "Item A", "1,000"],
        ["B002", "2024-02-01T00:00:00Z", "OID-2", "Cancelled", "Cancelled Item", "2,000"],
        ["B003", "2024-03-01T00:00:00Z", "OID-3", "Cancelled", "Another", "3,000"],
    ])
    df = app._load_cancelled(str(path))
    assert len(df) == 2
    assert df["Product Name"].tolist() == ["Cancelled Item", "Another"]
    assert df["Year"].tolist() == [2024, 2024]


def test_load_cancelled_returns_empty_when_file_missing(tmp_path):
    df = app._load_cancelled(str(tmp_path / "no-such-file.csv"))
    assert df.empty


REFUND_HEADER = ["Order ID", "Refund Date", "Refund Amount"]


def test_load_refunds_drops_zero_refunds_and_joins_product_name(tmp_path):
    orders_path = tmp_path / "orders.csv"
    _write_csv(orders_path, PHYSICAL_HEADER, [
        ["B001", "2024-01-01T00:00:00Z", "OID-1", "Closed", "Refunded Speaker", "10,000"],
        ["B002", "2024-02-01T00:00:00Z", "OID-2", "Closed", "Other Item", "5,000"],
    ])
    refunds_path = tmp_path / "refunds.csv"
    _write_csv(refunds_path, REFUND_HEADER, [
        ["OID-1", "2024-02-02T10:00:00.498Z", "10,000"],
        ["OID-999", "2024-03-01T00:00:00Z", "1,500"],  # not in orders → fallback
        ["OID-1", "2024-02-02T10:00:00Z", "0"],         # zero refund → dropped
    ])
    df = app._load_refunds(str(refunds_path), str(orders_path))
    assert len(df) == 2
    products = df.set_index("Order ID")["Product Name"].to_dict()
    assert products["OID-1"] == "Refunded Speaker"
    assert products["OID-999"] == "—"
    assert df["Refund Amount"].sum() == 11500.0


def test_load_refunds_returns_empty_when_file_missing(tmp_path):
    assert app._load_refunds(str(tmp_path / "missing.csv"), "irrelevant").empty
