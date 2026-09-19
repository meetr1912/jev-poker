"""Heads-up No-Limit Hold'em table built on PokerKit (github.com/uoftcprg/pokerkit)."""

from dataclasses import dataclass

from pokerkit import Automation, NoLimitTexasHoldem

AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)

STREETS = {0: "Preflop", 1: "Flop", 2: "Turn", 3: "River"}
# PokerKit heads-up: position 0 posts the big blind, position 1 the small blind / button.
POSITIONS = {0: "BB", 1: "BTN/SB"}


@dataclass(frozen=True)
class Action:
    """One legal action offered to a player."""

    name: str
    label: str
    kind: str  # fold | check | call | raise
    amount: int | None = None

    def describe(self) -> str:
        if self.kind == "fold":
            return "Fold and forfeit the pot."
        if self.kind == "check":
            return "Check: put no chips in and pass the action."
        if self.kind == "call":
            return f"Call {self.amount} chips to stay in the hand."
        return f"Bet/raise to {self.amount} chips total."


def _code(card) -> str:
    return f"{card.rank}{card.suit}"


def _flat(cards) -> list[str]:
    return [_code(card) for group in cards for card in group]


class HoldemTable:
    """A two-player hand. Position 0 is the button/small blind, position 1 the big blind."""

    def __init__(self, stacks: tuple[int, int], blinds: tuple[int, int] = (1, 2), min_bet: int = 2):
        self.blinds = blinds
        self.min_bet = min_bet
        self.state = NoLimitTexasHoldem.create_state(
            AUTOMATIONS,
            True,  # uniform antes
            0,  # no antes
            blinds,
            min_bet,
            stacks,
            len(stacks),
        )

    @property
    def actor(self) -> int | None:
        return self.state.actor_index

    @property
    def street(self) -> str:
        return STREETS.get(self.state.street_index, f"Street {self.state.street_index}")

    @property
    def street_index(self) -> int:
        return self.state.street_index or 0

    def board(self) -> list[str]:
        return _flat(self.state.board_cards)

    def hole(self, player: int) -> list[str]:
        return [_code(card) for card in self.state.hole_cards[player]]

    def stacks(self) -> tuple[int, int]:
        return (self.state.stacks[0], self.state.stacks[1])

    def pot(self) -> int:
        return int(self.state.total_pot_amount + sum(self.state.bets))

    def to_call(self, player: int) -> int:
        del player
        return int(self.state.checking_or_calling_amount or 0)

    def legal_actions(self, player: int) -> list[Action]:
        state = self.state
        actions: list[Action] = []
        if state.can_fold():
            actions.append(Action("FOLD", "Fold", "fold"))
        if state.can_check_or_call():
            amount = int(state.checking_or_calling_amount)
            if amount:
                actions.append(Action("CALL", f"Call {amount}", "call", amount))
            else:
                actions.append(Action("CHECK", "Check", "check"))
        if state.can_complete_bet_or_raise_to():
            low = int(state.min_completion_betting_or_raising_to_amount)
            high = int(state.max_completion_betting_or_raising_to_amount)
            pot, to_call = self.pot(), int(state.checking_or_calling_amount or 0)
            candidates = {
                "RAISE_MIN": low,
                "RAISE_HALF": round(to_call + 0.5 * pot),
                "RAISE_POT": round(to_call + pot),
                "RAISE_ALLIN": high,
            }
            seen: set[int] = set()
            for name, amount in candidates.items():
                amount = max(low, min(high, amount))
                if amount in seen:
                    continue
                seen.add(amount)
                # Postflop with no bet yet it is a bet; otherwise (including the preflop BB) a raise.
                verb = "Bet" if (self.street_index > 0 and to_call == 0) else "Raise to"
                actions.append(Action(name, f"{verb} {amount}", "raise", amount))
        return actions

    def apply(self, action: Action) -> None:
        state = self.state
        if action.kind == "fold":
            state.fold()
        elif action.kind in ("check", "call"):
            state.check_or_call()
        elif action.kind == "raise":
            state.complete_bet_or_raise_to(action.amount)
        else:  # pragma: no cover - guarded by Action construction
            raise ValueError(f"Unknown action kind: {action.kind}")

    @property
    def done(self) -> bool:
        return not self.state.status

    def payoffs(self) -> tuple[int, int]:
        return (int(self.state.payoffs[0]), int(self.state.payoffs[1]))
