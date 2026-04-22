from agent.order_reservation import OrderReservationLedger


def test_order_reservation_uses_remaining_cash_for_later_buy_candidates():
    ledger = OrderReservationLedger(starting_cash=100_000)

    first = ledger.reserve(symbol="005930", amount=70_000, quantity=7)
    second = ledger.reserve(symbol="000660", amount=40_000, quantity=4)

    assert first.approved is True
    assert first.reserved_amount == 70_000
    assert ledger.available_cash == 30_000
    assert second.approved is False
    assert second.reason == "예약 가능 현금 부족"
    assert second.available_cash == 30_000


def test_order_reservation_releases_failed_or_skipped_buy_candidate():
    ledger = OrderReservationLedger(starting_cash=100_000)

    reservation = ledger.reserve(symbol="005930", amount=70_000, quantity=7)
    ledger.release(reservation.reservation_id, reason="broker_rejected")

    assert ledger.available_cash == 100_000
    assert ledger.reserved_cash == 0
