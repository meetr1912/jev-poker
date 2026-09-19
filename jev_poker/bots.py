"""A lightweight heuristic opponent so Jev has someone to play against."""

from __future__ import annotations

import random

from pokerkit import Card, StandardHighHand

from .engine import Action, HoldemTable

RANK_VALUE = {r: i for i, r in enumerate("23456789TJQKA", start=2)}


def _hole_strength(hole: list[str]) -> float:
    """Crude 0..1 preflop strength from the two hole cards."""
    (first, second) = hole
    r1, r2 = RANK_VALUE[first[0]], RANK_VALUE[second[0]]
    high, low = max(r1, r2), min(r1, r2)
    score = (high - 2) / 12 * 0.6 + (low - 2) / 12 * 0.2
    if r1 == r2:
        score = 0.5 + (high - 2) / 12 * 0.5
    elif first[1] == second[1]:
        score += 0.08
    if abs(r1 - r2) == 1:
        score += 0.06
    return max(0.0, min(1.0, score))


def _made_strength(hole: list[str], board: list[str]) -> float:
    if len(board) < 3:
        return _hole_strength(hole)
    hand = StandardHighHand.from_game(list(Card.parse("".join(hole))), list(Card.parse("".join(board))))
    base = hand.entry.index / 7462
    # A made hand on this board plus the hole-card quality it was built from.
    return max(0.0, min(1.0, 0.65 * base + 0.35 * _hole_strength(hole)))


class HouseBot:
    """Tight-aggressive-ish opponent with a little randomness."""

    def __init__(self, seed: int | None = None, name: str = "HouseBot"):
        self.random = random.Random(seed)
        self.name = name

    def choose(self, table: HoldemTable, player: int, history: list[dict]) -> Action:
        del history
        actions = {action.name: action for action in table.legal_actions(player)}
        strength = _made_strength(table.hole(player), table.board())
        pot = table.pot()
        to_call = table.to_call(player)
        noise = self.random.uniform(-0.08, 0.08)
        score = strength + noise

        def pick(*names: str) -> Action:
            for name in names:
                if name in actions:
                    return actions[name]
            return next(iter(actions.values()))

        if to_call == 0:
            if "RAISE_POT" in actions and score > 0.66:
                return actions["RAISE_POT"]
            if "RAISE_HALF" in actions and score > 0.58:
                return actions["RAISE_HALF"]
            return pick("CHECK", "CALL", "FOLD")

        pot_odds = to_call / (pot + to_call) if pot + to_call else 0
        if score > 0.78 and "RAISE_POT" in actions:
            return actions["RAISE_POT"]
        if score > 0.62 and "RAISE_HALF" in actions and self.random.random() < 0.35:
            return actions["RAISE_HALF"]
        if score + 0.12 >= pot_odds:
            return pick("CALL", "CHECK", "FOLD")
        return pick("FOLD", "CHECK", "CALL")


class CallBot:
    """Baseline opponent: always check or call, never folds or raises.

    Used as the API-free stand-in for Jev so CI can capture a full scoreboard
    without spending any TypeSafe tokens.
    """

    name = "CallBot"

    def choose(self, table: HoldemTable, player: int, history: list[dict]) -> Action:
        del history
        actions = {action.name: action for action in table.legal_actions(player)}
        for name in ("CHECK", "CALL"):
            if name in actions:
                return actions[name]
        return next(iter(actions.values()))

