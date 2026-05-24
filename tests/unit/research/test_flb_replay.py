import pytest

from app.research.flb_replay import (
    find_entry,
    is_binary_yes_no,
    iso_to_ts,
    parse_outcome,
    position_pnl,
    summarize,
    yes_token_id,
)


# --- market parsing (gamma encodes list fields as JSON strings) ------------

def test_is_binary_yes_no_handles_json_string() -> None:
    assert is_binary_yes_no({"outcomes": '["Yes", "No"]'})
    assert is_binary_yes_no({"outcomes": ["Yes", "No"]})
    assert not is_binary_yes_no({"outcomes": '["Trump", "Biden", "Other"]'})
    assert not is_binary_yes_no({})


def test_parse_outcome_yes_no_and_ambiguous() -> None:
    assert parse_outcome({"outcomePrices": '["1", "0"]'}) == "YES"
    assert parse_outcome({"outcomePrices": '["0", "1"]'}) == "NO"
    assert parse_outcome({"outcomePrices": '["0.97", "0.03"]'}) == "YES"
    assert parse_outcome({"outcomePrices": '["0.5", "0.5"]'}) is None  # not resolved
    assert parse_outcome({"outcomePrices": '["1"]'}) is None  # malformed


def test_yes_token_id_first_of_pair() -> None:
    assert yes_token_id({"clobTokenIds": '["aaa", "bbb"]'}) == "aaa"
    assert yes_token_id({"clobTokenIds": "[]"}) is None


def test_iso_to_ts_handles_z_suffix() -> None:
    assert iso_to_ts("2024-05-31T00:00:00Z") == 1717113600
    assert iso_to_ts(None) is None
    assert iso_to_ts("garbage") is None


# --- the trigger: ex-ante, no look-ahead -----------------------------------

def test_find_entry_picks_earliest_point_in_band_and_window() -> None:
    end = 100 * 86400
    history = [
        {"t": end - 120 * 86400, "p": 0.10},  # 120d out: too early, runway gate
        {"t": end - 80 * 86400, "p": 0.30},   # 80d: in window but price too high
        {"t": end - 60 * 86400, "p": 0.10},   # 60d: FIRST valid -> expected
        {"t": end - 20 * 86400, "p": 0.08},   # 20d: also valid but later
    ]
    entry = find_entry(history, end, low=0.05, high=0.15, min_days=7, max_days=90)
    assert entry is not None
    assert entry["entry_price"] == pytest.approx(0.10)
    assert entry["days_to_res"] == pytest.approx(60.0)


def test_find_entry_excludes_inside_minimum_runway() -> None:
    end = 100 * 86400
    history = [{"t": end - 3 * 86400, "p": 0.10}]  # only 3d left -> below min_days
    assert find_entry(history, end, low=0.05, high=0.15, min_days=7, max_days=90) is None


def test_find_entry_none_when_never_in_band() -> None:
    end = 100 * 86400
    history = [{"t": end - 30 * 86400, "p": 0.40}, {"t": end - 10 * 86400, "p": 0.60}]
    assert find_entry(history, end, low=0.05, high=0.15, min_days=7, max_days=90) is None


# --- PnL of the NO (fade) position ------------------------------------------

def test_position_pnl_no_win_keeps_premium() -> None:
    assert position_pnl(0.10, "NO") == pytest.approx(0.10)


def test_position_pnl_yes_win_pays_out() -> None:
    assert position_pnl(0.10, "YES") == pytest.approx(-0.90)


def test_position_pnl_spread_eats_both_sides() -> None:
    # selling at the bid lowers the premium received by half the spread
    assert position_pnl(0.10, "NO", spread=0.02) == pytest.approx(0.09)
    assert position_pnl(0.10, "YES", spread=0.02) == pytest.approx(-0.91)


# --- aggregate edge math: mean PnL == p_bar - q at zero spread -------------

def test_summarize_edge_is_pbar_minus_q() -> None:
    # 9 longshots resolve NO (+0.10 each), 1 hits YES (-0.90): fairly priced 0.10
    rows = [{"entry_price": 0.10, "outcome": "NO", "end_ts": i} for i in range(9)]
    rows.append({"entry_price": 0.10, "outcome": "YES", "end_ts": 9})
    s = summarize(rows)
    assert s["n"] == 10
    assert s["mean_entry"] == pytest.approx(0.10)
    assert s["yes_rate"] == pytest.approx(0.10)
    # gross edge = p_bar - q = 0.10 - 0.10 = 0 (fairly priced => no edge)
    assert s["gross_edge"] == pytest.approx(0.0)
    assert s["mean_pnl"] == pytest.approx(s["gross_edge"])  # spread 0 identity


def test_summarize_positive_edge_when_overpriced() -> None:
    # priced 0.10 but only 1 of 20 actually hits => true q=0.05 < p => +FLB
    rows = [{"entry_price": 0.10, "outcome": "NO", "end_ts": i} for i in range(19)]
    rows.append({"entry_price": 0.10, "outcome": "YES", "end_ts": 19})
    s = summarize(rows)
    assert s["yes_rate"] == pytest.approx(0.05)
    assert s["gross_edge"] == pytest.approx(0.05)
    # a 2c spread still leaves it positive here
    assert summarize(rows, spread=0.02)["mean_pnl"] == pytest.approx(0.04)


def test_summarize_drawdown_orders_by_resolution_date() -> None:
    # the single YES blowup resolves first => deepest drawdown up front
    rows = [{"entry_price": 0.10, "outcome": "YES", "end_ts": 0}]
    rows += [{"entry_price": 0.10, "outcome": "NO", "end_ts": i} for i in range(1, 10)]
    s = summarize(rows)
    assert s["max_drawdown"] == pytest.approx(-0.90)
    assert s["worst"] == pytest.approx(-0.90)
