"""Engine invariants: chips are conserved, stacks stay valid, and moves are legal."""

import random

from jev_poker.engine import HoldemTable


def test_blind_positions_and_call_amount():
    table = HoldemTable((200, 200), (1, 2), 2)
    assert table.state.bets == [2, 1]  # position 0 posts BB, position 1 posts SB
    assert table.actor == 1  # SB acts first preflop
    call = next(a for a in table.legal_actions(1) if a.name == "CALL")
    assert call.amount == 1


def test_chip_conservation_random_play():
    random.seed(1234)
    for _ in range(200):
        table = HoldemTable((200, 200), (1, 2), 2)
        while not table.done:
            table.apply(random.choice(table.legal_actions(table.actor)))
        payoffs = table.payoffs()
        stacks = table.stacks()
        assert stacks[0] + stacks[1] == 400, stacks
        assert payoffs[0] + payoffs[1] == 0
        assert stacks[0] == 200 + payoffs[0]
        assert stacks[1] == 200 + payoffs[1]


def test_offered_actions_are_always_legal():
    random.seed(99)
    for _ in range(100):
        table = HoldemTable((100, 100), (1, 2), 2)
        while not table.done:
            actions = table.legal_actions(table.actor)
            assert actions, "actor with no legal actions"
            table.apply(random.choice(actions))  # PokerKit raises if the move is illegal


def test_passive_hand_completes_at_showdown():
    table = HoldemTable((200, 200), (1, 2), 2)
    while not table.done:
        actions = table.legal_actions(table.actor)
        check = next((a for a in actions if a.name in ("CHECK", "CALL")), None)
        table.apply(check or actions[0])
    payoffs = table.payoffs()
    assert payoffs[0] + payoffs[1] == 0
    assert table.stacks()[0] + table.stacks()[1] == 400
