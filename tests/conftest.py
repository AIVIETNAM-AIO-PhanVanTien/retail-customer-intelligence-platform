"""Shared test fixtures for the retail Medallion pipeline."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest


@pytest.fixture
def bronze_like_df() -> pd.DataFrame:
    """Small DataFrame mimicking Bronze output for one month (3 rows)."""
    return pd.DataFrame(
        {
            "invoice": ["489434", "489434", "C489449"],
            "stock_code": ["85048", "79323P", "22087"],
            "description": [
                "15CM CHRISTMAS GLASS BALL 20 LIGHTS",
                "PINK CHERRY LIGHTS",
                "PAPER BUNTING WHITE LACE",
            ],
            "quantity": [12.0, 12.0, -12.0],
            "invoice_date": [
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 10, 33),
            ],
            "price": [6.95, 6.75, 2.95],
            "customer_id": ["13085", "13085", "16321"],
            "country": ["United Kingdom", "United Kingdom", "Australia"],
            "is_cancellation": [False, False, True],
            "ingested_at": [
                datetime(2026, 6, 8),
                datetime(2026, 6, 8),
                datetime(2026, 6, 8),
            ],
        }
    )


@pytest.fixture
def silver_like_df() -> pd.DataFrame:
    """Small DataFrame mimicking Silver output after cleaning + date-shift (5 rows).

    DATE_SHIFT_DAYS = 5295  (2026-06-08 − 2011-12-09).
    All rows share the same original date (2009-12-01), so all shift to 2024-05-31.
    """
    shifted = datetime(2024, 5, 31, 7, 45)   # 2009-12-01 07:45 + 5295 days
    return pd.DataFrame(
        {
            "invoice": ["489434", "489434", "C489449", "489465", "489465"],
            "stock_code": ["85048", "79323P", "22087", "21733", "85023A"],
            "description": [
                "15CM CHRISTMAS GLASS BALL 20 LIGHTS",
                "PINK CHERRY LIGHTS",
                "PAPER BUNTING WHITE LACE",
                "RED FELT EASTER EGG",
                "BLUE FELT EASTER EGG",
            ],
            "quantity": [12.0, 12.0, -12.0, 24.0, 12.0],
            "price": [6.95, 6.75, 2.95, 1.65, 1.65],
            "customer_id": ["13085", "13085", "16321", "13085", "13085"],
            "country": [
                "United Kingdom",
                "United Kingdom",
                "Australia",
                "United Kingdom",
                "United Kingdom",
            ],
            "is_cancellation": [False, False, True, False, False],
            "line_amount": [83.40, 81.00, -35.40, 39.60, 19.80],
            "invoice_date": [
                shifted,
                shifted,
                datetime(2024, 5, 31, 10, 33),
                datetime(2024, 5, 31, 12, 0),
                datetime(2024, 5, 31, 12, 0),
            ],
            "original_invoice_date": [
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 10, 33),
                datetime(2009, 12, 1, 12, 0),
                datetime(2009, 12, 1, 12, 0),
            ],
            "invoice_year": [2024, 2024, 2024, 2024, 2024],
            "invoice_month": [5, 5, 5, 5, 5],
            "invoice_day": [31, 31, 31, 31, 31],
            "invoice_quarter": [2, 2, 2, 2, 2],
            "invoice_day_of_week": [4, 4, 4, 4, 4],
            "invoice_week": [22, 22, 22, 22, 22],
            "year_month": ["2024-05", "2024-05", "2024-05", "2024-05", "2024-05"],
        }
    )
