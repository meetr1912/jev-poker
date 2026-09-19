"""Jev (TypeSafe System One) as the decision maker for heads-up poker.

Jev returns a typed choice with a probability distribution over the legal actions.
That distribution is the "thinking" the demo renders on the side panel.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .engine import Action, HoldemTable

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CLIENT = httpx.Client(http2=True, timeout=30)

POKER_RULES = (
    "You are a top heads-up No-Limit Texas Hold'em player. Choose exactly one offered action. "
    "Weigh hand strength, board texture, position, stack depth, pot odds, and the opponent's line. "
    "Value-bet strong hands, keep bluffs and calls balanced, and avoid folding to trivial bets."
)


class JevError(RuntimeError):
    """The TypeSafe call failed or returned an unusable answer."""


@dataclass
class Decision:
    choice: str
    operation: str
    probabilities: dict[str, float]
    confidence: float
    latency_ms: int
    model: str
    fallback: bool = False
    summary: str = ""
    view: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "choice": self.choice,
            "operation": self.operation,
            "probabilities": self.probabilities,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "model": self.model,
            "fallback": self.fallback,
            "summary": self.summary,
            "view": self.view,
        }


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def ensure_api_key() -> str:
    if not os.environ.get("TYPESAFE_API_KEY"):
        load_env_file(Path(__file__).resolve().parent.parent / ".env")
    if not os.environ.get("TYPESAFE_API_KEY"):
        load_env_file(Path.home() / "jev-ultrafast" / ".env")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise JevError("TYPESAFE_API_KEY is not set (add it to jev-poker/.env or jev-ultrafast/.env)")
    return key


def build_view(table: HoldemTable, player: int, history: list[dict]) -> dict:
    opponent = 1 - player
    stacks = table.stacks()
    state = table.state
    position = (
        "BB (out of position, acts last preflop)"
        if player == 0
        else "BTN/SB (in position, acts first preflop)"
    )
    return {
        "game": "Heads-up No-Limit Texas Hold'em",
        "your_hand": table.hole(player),
        "your_position": position,
        "street": table.street,
        "community_cards": table.board(),
        "pot": table.pot(),
        "chips_to_call": int(state.checking_or_calling_amount or 0),
        "your_stack": stacks[player],
        "opponent_stack": stacks[opponent],
        "your_bet_this_round": int(state.bets[player]),
        "opponent_bet_this_round": int(state.bets[opponent]),
        "min_raise_to": int(state.min_completion_betting_or_raising_to_amount or 0),
        "max_raise_to": int(state.max_completion_betting_or_raising_to_amount or 0),
        "actions_so_far": history[-12:],
    }


def _summary(choice: str, probabilities: dict[str, float], confidence: float) -> str:
    ranked = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
    top = ranked[0] if ranked else (choice, 0.0)
    if len(ranked) > 1:
        runner = ranked[1]
        return (
            f"Jev chose {top[0]} at p={top[1]:.0%} (runner-up {runner[0]} {runner[1]:.0%}, "
            f"reported confidence {confidence:.0%})."
        )
    return f"Jev chose {top[0]} at p={top[1]:.0%} (reported confidence {confidence:.0%})."


def _validate(answer: dict, actions: list[Action]) -> None:
    names = {action.name for action in actions}
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != names:
        raise JevError("Jev did not score every offered action")
    numbers = [*probabilities.values(), answer.get("confidence")]
    if not all(type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1 for n in numbers):
        raise JevError("Jev returned a non-finite probability")
    if abs(sum(probabilities.values()) - 1) >= 0.02:
        raise JevError("Jev probabilities do not sum to 1")
    if answer.get("choice") not in names:
        raise JevError("Jev chose an action that was not offered")


def decide(table: HoldemTable, player: int, history: list[dict], attempts: int = 3) -> Decision:
    actions = table.legal_actions(player)
    if not actions:
        raise JevError("No legal actions available")
    criteria = {action.name: f"{action.label}: {action.describe()}" for action in actions}
    view = build_view(table, player, history)
    body = {
        "model": os.environ.get("TYPESAFE_MODEL", "jev-latest"),
        "state": view,
        "questions": {
            "action": {
                "type": "choice",
                "criteria": criteria,
                "instructions": {
                    "goal": "Win the most chips in this heads-up poker hand.",
                    "rules": POKER_RULES,
                },
            }
        },
    }
    key = ensure_api_key()
    last_error: Exception | None = None
    started = time.perf_counter()
    for attempt in range(attempts):
        try:
            response = CLIENT.post(ENDPOINT, json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as error:
            last_error = error
            time.sleep(0.4 * 2**attempt)
            continue
        if response.status_code in {429, 529, 503} and attempt < attempts - 1:
            time.sleep(0.5 * 2**attempt)
            continue
        if response.is_error:
            raise JevError(f"TypeSafe returned HTTP {response.status_code}")
        try:
            answer = response.json()["answers"]["action"]
            _validate(answer, actions)
        except (KeyError, TypeError, ValueError, JevError) as error:
            last_error = error
            time.sleep(0.3 * 2**attempt)
            continue
        latency = round((time.perf_counter() - started) * 1000)
        probabilities = {name: round(value, 4) for name, value in answer["probabilities"].items()}
        return Decision(
            choice=answer["choice"],
            operation="choice",
            probabilities=probabilities,
            confidence=round(answer["confidence"], 4),
            latency_ms=latency,
            model=response.json().get("model", os.environ.get("TYPESAFE_MODEL", "jev-latest")),
            summary=_summary(answer["choice"], probabilities, answer["confidence"]),
            view=view,
        )
    raise JevError(f"no usable Jev answer after {attempts} attempts: {last_error}")


def fallback_action(actions: list[Action]) -> Action:
    """Safest legal action if Jev is unavailable: check/call, else fold."""
    for name in ("CHECK", "CALL"):
        for action in actions:
            if action.name == name:
                return action
    return actions[0]
