"""Watch Jev play heads-up No-Limit Hold'em, with its probabilities rendered live."""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .bots import HouseBot
from .engine import POSITIONS, HoldemTable
from .jev import Decision, JevError, fallback_action
from .jev import decide as jev_decide
from .scoreboard import Scoreboard

ROOT = Path(__file__).parent
DEFAULT_STACK = 200
DEFAULT_BLINDS = (1, 2)
MAX_ACTIONS_PER_HAND = 40


class Match:
    """Runs hands in a background thread and exposes the latest state to the inspector."""

    def __init__(self, hands: int = 8, stacks: int = DEFAULT_STACK, blinds: tuple[int, int] = DEFAULT_BLINDS,
                 delay: float = 0.6, seed: int | None = 7, offline: bool = False,
                 results_dir: str | Path | None = None):
        self.total_hands = hands
        self.stack_sizes = [stacks, stacks]
        self.blinds = blinds
        self.delay = delay
        self.bot = HouseBot(seed, name="HouseBot-B" if offline else "HouseBot")
        self.offline = offline
        self.player_a = HouseBot((seed or 1) + 7919, name="HouseBot-A") if offline else None
        self.name_a = self.player_a.name if self.player_a else "Jev"
        self.results_dir = Path(results_dir) if results_dir else None
        self.scoreboard = Scoreboard(name_a=self.name_a, name_b=self.bot.name, starting_money=stacks)
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.stop_requested = threading.Event()
        self.reset_state()

    def reset_state(self) -> None:
        with self.lock:
            self.state = {
                "running": False,
                "finished": False,
                "hand_no": 0,
                "total_hands": self.total_hands,
                "stacks": list(self.stack_sizes),
                "pot": 0,
                "street": "-",
                "board": [],
                "actor": None,
                "jev_cards": [],
                "bot_cards": [],
                "showdown": False,
                "decision": None,
                "log": [],
                "score": {self.name_a: 0, self.bot.name: 0},
                "offline": self.offline,
                "player_a": self.name_a,
            }

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def _set(self, **changes) -> None:
        with self.lock:
            self.state.update(changes)

    def _log(self, hand: int, text: str, kind: str = "info", actor: int | None = None) -> None:
        with self.lock:
            self.state["log"].append({"hand": hand, "text": text, "kind": kind, "actor": actor})
            self.state["log"] = self.state["log"][-200:]

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_requested.clear()
        self.reset_state()
        self._set(running=True)
        self.thread = threading.Thread(target=self._run, daemon=True, name="jev-poker-match")
        self.thread.start()

    def stop(self) -> None:
        self.stop_requested.set()

    def _run(self) -> None:
        try:
            for hand_no in range(1, self.total_hands + 1):
                if self.stop_requested.is_set():
                    break
                self._play_hand(hand_no)
                time.sleep(self.delay)
            self._set(finished=True)
        finally:
            self._set(running=False)
            self._write_results()

    def _write_results(self) -> None:
        if self.results_dir is None:
            return
        json_path, md_path = self.scoreboard.write(self.results_dir)
        self._log(
            0,
            f"Scoreboard captured to {json_path.name} and {md_path.name}.",
            "hand",
        )

    def _play_hand(self, hand_no: int) -> None:
        if min(self.stack_sizes) <= 0:
            self._set(finished=True)
            return
        table = HoldemTable((self.stack_sizes[0], self.stack_sizes[1]), self.blinds, self.blinds[1])
        self._set(
            hand_no=hand_no,
            pot=table.pot(),
            street=table.street,
            board=table.board(),
            actor=None,
            jev_cards=table.hole(0),
            bot_cards=["??", "??"],
            showdown=False,
            decision=None,
        )
        self._log(hand_no, f"Hand {hand_no} dealt. {self.name_a} holds {''.join(table.hole(0))}.", "hand")
        history: list[dict] = []
        actions_taken = 0
        peak_pot = table.pot()

        while not table.done and actions_taken < MAX_ACTIONS_PER_HAND and not self.stop_requested.is_set():
            player = table.actor
            if player is None:
                break
            actions = table.legal_actions(player)
            if not actions:
                break
            self._set(actor=player, street=table.street, board=table.board(), pot=table.pot())
            peak_pot = max(peak_pot, table.pot())
            if player == 0 and self.player_a is not None:
                chosen = self.player_a.choose(table, player, history)
                self._set(
                    decision={
                        "choice": chosen.name,
                        "operation": "bot",
                        "probabilities": {},
                        "confidence": None,
                        "latency_ms": 0,
                        "model": self.player_a.name,
                        "fallback": False,
                        "summary": f"{self.player_a.name} plays {chosen.label}.",
                        "view": {},
                    }
                )
                who = self.player_a.name
            elif player == 0:
                try:
                    decision = jev_decide(table, player, history)
                    chosen = next(a for a in actions if a.name == decision.choice)
                    self._set(decision=decision.to_dict())
                except JevError as error:
                    chosen = fallback_action(actions)
                    self._set(
                        decision=Decision(
                            choice=chosen.name,
                            operation="fallback",
                            probabilities={chosen.name: 1.0},
                            confidence=0.0,
                            latency_ms=0,
                            model="fallback",
                            fallback=True,
                            summary=f"Jev unavailable ({error}); used safest action {chosen.label}.",
                            view={},
                        ).to_dict()
                    )
                who = "Jev"
            else:
                chosen = self.bot.choose(table, player, history)
                self._set(
                    decision={
                        "choice": chosen.name,
                        "operation": "bot",
                        "probabilities": {},
                        "confidence": None,
                        "latency_ms": 0,
                        "model": self.bot.name,
                        "fallback": False,
                        "summary": f"{self.bot.name} plays {chosen.label}.",
                        "view": {},
                    }
                )
                who = self.bot.name

            history.append({"actor": who, "action": chosen.label, "street": table.street})
            table.apply(chosen)
            actions_taken += 1
            self._log(hand_no, f"{who} ({POSITIONS[player]}): {chosen.label}", "action", player)
            self._set(pot=table.pot(), street=table.street, board=table.board())
            time.sleep(self.delay / 2)

        payoffs = table.payoffs()
        self.stack_sizes[0] += payoffs[0]
        self.stack_sizes[1] += payoffs[1]
        winner = self.name_a if payoffs[0] > 0 else (self.bot.name if payoffs[1] > 0 else "split")
        showdown = not table.state.folded_status
        self.scoreboard.record(hand_no, winner, peak_pot, payoffs[0], payoffs[1])
        score = self.snapshot()["score"]
        if payoffs[0] > 0:
            score[self.name_a] += 1
        elif payoffs[1] > 0:
            score[self.bot.name] += 1
        with self.lock:
            self.state["stacks"] = list(self.stack_sizes)
            self.state["score"] = score
            self.state["board"] = table.board()
            self.state["pot"] = table.pot()
            self.state["showdown"] = showdown
            self.state["actor"] = None
            if showdown:
                self.state["bot_cards"] = table.hole(1)
        self._log(
            hand_no,
            f"Hand {hand_no} won by {winner} ({payoffs[0]:+d} / {payoffs[1]:+d}).",
            "result",
        )


class Handler(BaseHTTPRequestHandler):
    match: Match

    def _send(self, status: int, content: bytes | str, mime: str = "application/json") -> None:
        body = content if isinstance(content, bytes) else content.encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.headers.get("Host", "").split(":")[0] not in {"127.0.0.1", "localhost"}:
            return self._send(403, "Forbidden", "text/plain")
        path = urlparse(self.path).path
        if path == "/api/state":
            return self._send(200, json.dumps(self.match.snapshot()))
        files = {
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        if path not in files:
            return self._send(404, "Not found", "text/plain")
        name, mime = files[path]
        return self._send(200, (ROOT / "static" / name).read_text(), mime + "; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if self.headers.get("Host", "").split(":")[0] not in {"127.0.0.1", "localhost"}:
            return self._send(403, json.dumps({"error": "Local only"}))
        path = urlparse(self.path).path
        if path == "/api/start":
            self.match.start()
        elif path == "/api/stop":
            self.match.stop()
        else:
            return self._send(404, json.dumps({"error": "Not found"}))
        return self._send(200, json.dumps(self.match.snapshot()))

    def log_message(self, *_args) -> None:
        pass


def run_headless(args: argparse.Namespace) -> int:
    match = Match(hands=args.hands, stacks=args.stack, blinds=(args.blinds, args.blinds * 2),
                  delay=args.delay, seed=args.seed, offline=args.offline,
                  results_dir=args.results_dir)
    match.start()
    while match.snapshot()["running"] or not match.snapshot()["finished"]:
        time.sleep(0.5)
    state = match.snapshot()
    print("=" * 72)
    for entry in state["log"]:
        prefix = {0: match.name_a[:3].upper(), 1: match.bot.name[:3].upper(), None: "   "}.get(
            entry.get("actor"), "   "
        )
        if entry["kind"] == "action":
            print(f"  {prefix} | {entry['text']}")
        else:
            print(f"      | {entry['text']}")
    print("=" * 72)
    board = match.scoreboard
    print(f"Money:  {match.name_a} ${board.money_a} | {match.bot.name} ${board.money_b}")
    print(f"Points: {match.name_a} {board.points_a} | {match.bot.name} {board.points_b}"
          + (f" | splits {board.splits}" if board.splits else ""))
    if args.results_dir:
        print(f"Scoreboard written to {args.results_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Jev plays heads-up No-Limit Hold'em.")
    parser.add_argument("--hands", type=int, default=6, help="number of hands to play")
    parser.add_argument("--stack", type=int, default=DEFAULT_STACK, help="starting stack (dollars)")
    parser.add_argument("--blinds", type=int, default=2, help="big blind (small blind is half)")
    parser.add_argument("--delay", type=float, default=0.6, help="seconds between bot actions")
    parser.add_argument("--seed", type=int, default=7, help="HouseBot RNG seed")
    parser.add_argument("--port", type=int, default=8777, help="inspector port")
    parser.add_argument("--headless", action="store_true", help="print a transcript instead of serving the UI")
    parser.add_argument("--offline", action="store_true",
                        help="replace Jev with a local CallBot (no API key, safe for CI)")
    parser.add_argument("--results-dir", default=None, help="write scoreboard.json / SCOREBOARD.md here")
    args = parser.parse_args()

    if args.headless:
        return run_headless(args)

    match = Match(hands=args.hands, stacks=args.stack, blinds=(args.blinds, args.blinds * 2),
                  delay=args.delay, seed=args.seed, offline=args.offline,
                  results_dir=args.results_dir)
    Handler.match = match
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Jev Poker inspector: http://127.0.0.1:{args.port}", flush=True)
    match.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        match.stop()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
