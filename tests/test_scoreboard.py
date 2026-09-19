"""Scoreboard accounting: money and points reconcile with the chip ledger."""

from jev_poker.scoreboard import Scoreboard


def test_money_and_points_reconcile():
    board = Scoreboard(name_a="Jev", name_b="HouseBot", starting_money=200)
    board.record(hand=1, winner="Jev", pot=12, money_a=6, money_b=-6)
    board.record(hand=2, winner="HouseBot", pot=20, money_a=-10, money_b=10)
    board.record(hand=3, winner="split", pot=4, money_a=0, money_b=0)

    assert board.money_a == 196
    assert board.money_b == 204
    assert board.points_a == 1
    assert board.points_b == 1
    assert board.splits == 1
    # Zero-sum: total money is conserved.
    assert board.money_a + board.money_b == 400


def test_outputs_are_written(tmp_path):
    board = Scoreboard(name_a="Jev", name_b="HouseBot", starting_money=200)
    board.record(hand=1, winner="Jev", pot=8, money_a=4, money_b=-4)
    json_path, md_path = board.write(tmp_path)

    assert json_path.exists() and md_path.exists()
    text = md_path.read_text()
    assert "| Jev | $204 | +4 | 1 |" in text
    assert "leader: **Jev**" in text
