import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.policy import *
from agent.tracer import Tracer


def test_routes():
    assert route("ALLOW_TRANSACTION") == "auto"
    assert route("CREATE_CASE") == "auto"
    assert route("DECLINE_TRANSACTION") == "L1"
    assert route("BLOCK_CARD", 268.43) == "L1"
    assert route("BLOCK_CARD", 2500) == "L1"
    assert route("BLOCK_CARD", 2500.01) == "L2"
    assert route("BLOCK_ALL_CARDS") == "L2"
    assert route("FILE_REPORT") == "L2"


def test_unknown_action():
    try:
        route("FREEZE_EVERYTHING")
        assert False
    except ValueError:
        pass


def test_report_rules():
    assert should_file_report(0.86, 268.43, True, False) is True    # shared device
    assert should_file_report(0.86, 268.43, False, False) is False  # case only
    assert should_file_report(0.86, 1000.03, False, False) is True  # > $1,000
    assert should_file_report(0.86, 1000.00, False, False) is False # not strictly over
    assert should_file_report(0.40, 5000, True, True) is False      # not strongly suspected


def test_case_and_block_rules():
    assert should_open_case(0.30, False, False)
    assert not should_open_case(0.29, False, False)
    assert should_open_case(0.05, True, False)
    assert not may_block_on_single_signal(0.45, True)
    assert may_block_on_single_signal(0.75, True)
    assert not can_block_all(1, False)
    assert can_block_all(2, False)


def test_stop():
    assert can_stop(0.90, 2, False, False)[0]
    assert not can_stop(0.90, 1, False, False)[0]
    assert can_stop(0.05, 2, False, False)[0]
    assert not can_stop(0.50, 3, False, False)[0]


def test_tracer(tmp_path):
    t = Tracer("HHG-TEST", log_dir=tmp_path)
    t.tool("card_window", card="C1")
    t.llm("assess", 1200)
    assert t.stats()["tool_calls"] == 1 and t.stats()["tokens"] == 1200
    assert t.save().exists()