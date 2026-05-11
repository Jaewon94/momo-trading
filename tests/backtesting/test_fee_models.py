from backtesting.fee_models import KoreaStockFeeModel


def test_korea_stock_fee_model_separates_commission_and_sell_tax() -> None:
    model = KoreaStockFeeModel(commission_rate_pct=0.015, sell_tax_rate_pct=0.15)

    buy = model.calculate(side="BUY", price=10_000, quantity=10)
    sell = model.calculate(side="SELL", price=10_000, quantity=10)

    assert buy.notional == 100_000
    assert buy.commission == 15
    assert buy.tax == 0
    assert buy.cash_delta == -100_015

    assert sell.notional == 100_000
    assert sell.commission == 15
    assert sell.tax == 150
    assert sell.cash_delta == 99_835


def test_korea_stock_fee_model_metadata_is_reportable() -> None:
    model = KoreaStockFeeModel(commission_rate_pct=0.015, sell_tax_rate_pct=0.15)

    assert model.metadata() == {
        "name": "KOREA_STOCK_FEE_MODEL",
        "commission_rate_pct": 0.015,
        "sell_tax_rate_pct": 0.15,
    }
