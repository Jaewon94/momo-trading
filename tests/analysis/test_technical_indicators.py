import pandas as pd

from analysis.technical.indicators import TechnicalIndicators


def test_bollinger_bands_are_mapped_by_column_name() -> None:
    df = pd.DataFrame(
        {
            "open": [100 + i for i in range(30)],
            "high": [103 + i for i in range(30)],
            "low": [97 + i for i in range(30)],
            "close": [100 + i for i in range(30)],
            "volume": [10_000 + i * 100 for i in range(30)],
        }
    )

    indicators = TechnicalIndicators.calculate_all(df)

    assert indicators["bb_upper"] > indicators["bb_middle"] > indicators["bb_lower"]
    assert indicators["bb_squeeze_ratio"] > 0
