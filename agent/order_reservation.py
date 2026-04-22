"""Cycle-local cash reservation for concurrent BUY candidates."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from trading.symbols import normalize_krx_symbol


@dataclass(frozen=True)
class OrderReservationDecision:
    approved: bool
    symbol: str
    requested_amount: float
    reserved_amount: float
    available_cash: float
    reservation_id: str | None = None
    reason: str = ""


@dataclass
class _Reservation:
    reservation_id: str
    symbol: str
    amount: float
    quantity: int
    active: bool = True


class OrderReservationLedger:
    """Tracks reserved cash within one trading cycle."""

    def __init__(self, *, starting_cash: float) -> None:
        self.starting_cash = max(float(starting_cash or 0.0), 0.0)
        self._reservations: dict[str, _Reservation] = {}

    @property
    def reserved_cash(self) -> float:
        return sum(item.amount for item in self._reservations.values() if item.active)

    @property
    def available_cash(self) -> float:
        return max(self.starting_cash - self.reserved_cash, 0.0)

    def reserve(self, *, symbol: str, amount: float, quantity: int) -> OrderReservationDecision:
        normalized_symbol = normalize_krx_symbol(symbol)
        requested_amount = max(float(amount or 0.0), 0.0)
        if requested_amount <= 0 or int(quantity or 0) <= 0:
            return OrderReservationDecision(
                approved=False,
                symbol=normalized_symbol,
                requested_amount=requested_amount,
                reserved_amount=0.0,
                available_cash=self.available_cash,
                reason="예약 금액 또는 수량이 유효하지 않음",
            )

        available = self.available_cash
        if requested_amount > available:
            return OrderReservationDecision(
                approved=False,
                symbol=normalized_symbol,
                requested_amount=requested_amount,
                reserved_amount=0.0,
                available_cash=available,
                reason="예약 가능 현금 부족",
            )

        reservation_id = str(uuid4())
        self._reservations[reservation_id] = _Reservation(
            reservation_id=reservation_id,
            symbol=normalized_symbol,
            amount=requested_amount,
            quantity=int(quantity),
        )
        return OrderReservationDecision(
            approved=True,
            symbol=normalized_symbol,
            requested_amount=requested_amount,
            reserved_amount=requested_amount,
            available_cash=self.available_cash,
            reservation_id=reservation_id,
            reason="예약 완료",
        )

    def release(self, reservation_id: str | None, *, reason: str = "") -> bool:
        if not reservation_id:
            return False
        reservation = self._reservations.get(reservation_id)
        if reservation is None or not reservation.active:
            return False
        reservation.active = False
        return True
