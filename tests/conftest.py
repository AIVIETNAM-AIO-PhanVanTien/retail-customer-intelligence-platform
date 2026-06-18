"""Shared test fixtures for the retail Medallion pipeline."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest


@pytest.fixture
def bronze_like_df() -> pd.DataFrame:
    """Small DataFrame mimicking Bronze output for one month (3 rows).

    Dates are already shifted to ~2026 (date synthesis is now in Bronze).
    """
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
                datetime(2024, 6, 7, 7, 45),
                datetime(2024, 6, 7, 7, 45),
                datetime(2024, 6, 7, 10, 33),
            ],
            "original_invoice_date": [
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 10, 33),
            ],
            "price": [6.95, 6.75, 2.95],
            "customer_id": ["13085", "13085", "16321"],
            "country": ["United Kingdom", "United Kingdom", "Australia"],
            "is_cancellation": [False, False, True],
            "ingested_at": [
                datetime(2026, 6, 10),
                datetime(2026, 6, 10),
                datetime(2026, 6, 10),
            ],
        }
    )


@pytest.fixture
def silver_like_df() -> pd.DataFrame:
    """Small DataFrame mimicking Silver output after cleaning (5 rows).

    Dates are already shifted (from Bronze), with derived calendar columns.
    """
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
                datetime(2024, 6, 7, 7, 45),
                datetime(2024, 6, 7, 7, 45),
                datetime(2024, 6, 7, 10, 33),
                datetime(2024, 6, 7, 12, 0),
                datetime(2024, 6, 7, 12, 0),
            ],
            "original_invoice_date": [
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 7, 45),
                datetime(2009, 12, 1, 10, 33),
                datetime(2009, 12, 1, 12, 0),
                datetime(2009, 12, 1, 12, 0),
            ],
            "invoice_year": [2024, 2024, 2024, 2024, 2024],
            "invoice_month": [6, 6, 6, 6, 6],
            "invoice_day": [7, 7, 7, 7, 7],
            "invoice_quarter": [2, 2, 2, 2, 2],
            "invoice_day_of_week": [4, 4, 4, 4, 4],
            "invoice_week": [23, 23, 23, 23, 23],
            "year_month": ["2024-06", "2024-06", "2024-06", "2024-06", "2024-06"],
        }
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests that require built data/ artifacts (bronze, silver, gold, duckdb)",
    )
