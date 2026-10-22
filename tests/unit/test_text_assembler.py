"""TextAssembler: positional, replay-safe, UTF-16-addressed text assembly."""

from __future__ import annotations

from typing import Any

import pytest

from ligaxai import RunEvent, TextAssembler
from tests.conftest import recorded_frames


def ev(type_: str, seq: int | None, **payload: Any) -> RunEvent:
    return RunEvent(type=type_, seq=seq, payload=payload)


def delta(seq: int | None, part: str, offset: int, text: str) -> RunEvent:
    return ev("text.delta", seq, part_id=part, offset=offset, text=text)


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def test_in_order_deltas_yield_new_text_and_build_the_answer() -> None:
    a = TextAssembler()
    assert a.apply(ev("part.start", 1, part_id="p0", kind="text")) == ""
    assert a.apply(delta(2, "p0", 0, "Hello")) == "Hello"
    assert a.apply(delta(3, "p0", 5, ", world")) == ", world"
    assert a.answer() == "Hello, world"
    assert a.text("p0") == "Hello, world"
    assert a.part_ids == ["p0"]


def test_replayed_frames_change_nothing_and_yield_nothing() -> None:
    a = TextAssembler()
    frames = [ev("part.start", 1, part_id="p0"), delta(2, "p0", 0, "abc"), delta(3, "p0", 3, "def")]
    out = [a.apply(f) for f in frames]
    replay = [a.apply(f) for f in frames]
    assert "".join(out) == "abcdef"
    assert replay == ["", "", ""]
    assert a.answer() == "abcdef"


def test_replay_without_seq_is_still_positional() -> None:
    # A delta with no seq (or a resumed stream that re-numbers) is deduplicated by position.
    a = TextAssembler()
    assert a.write("p0", 0, "abc") == "abc"
    assert a.write("p0", 0, "abc") == ""
    assert a.write("p0", 1, "bc") == ""
    assert a.write("p0", 3, "d") == "d"
    assert a.answer() == "abcd"


def test_out_of_order_delta_is_held_until_the_gap_fills() -> None:
    a = TextAssembler()
    assert a.write("p0", 5, "world") == ""  # nothing readable yet: 0..5 unwritten
    assert a.text("p0") == "     world"  # padded, as the platform's reducer pads
    assert a.write("p0", 0, "hello") == "helloworld"
    assert a.answer() == "helloworld"


def test_overlapping_pending_spans_are_absorbed() -> None:
    a = TextAssembler()
    assert a.write("p0", 6, "gh") == ""
    assert a.write("p0", 3, "def") == ""
    assert a.write("p0", 0, "abc") == "abcdefgh"


def test_emoji_offsets_are_utf16_code_units() -> None:
    a = TextAssembler()
    first = "Hi 😀"  # the emoji is one str char and two UTF-16 units
    assert utf16_len(first) == 5
    assert a.write("p0", 0, first) == first
    assert a.write("p0", utf16_len(first), " there 👋🏽!") == " there 👋🏽!"
    assert a.answer() == "Hi 😀 there 👋🏽!"
    # A replay addressed in UTF-16 units lands on the same characters.
    assert a.write("p0", 3, "😀") == ""
    assert a.answer() == "Hi 😀 there 👋🏽!"


def test_a_surrogate_pair_split_across_deltas_is_never_emitted_in_half() -> None:
    a = TextAssembler()
    high, low = "\ud83d", "\ude00"  # 😀 as two lone surrogates, one per delta
    assert a.write("p0", 0, "a" + high) == "a"
    assert a.write("p0", 2, low + "b") == "😀b"
    assert a.answer() == "a😀b"


def test_multiple_parts_answer_in_part_start_order() -> None:
    a = TextAssembler()
    a.apply(ev("part.start", 1, part_id="first", kind="text"))
    a.apply(ev("part.start", 2, part_id="second", kind="text"))
    a.apply(delta(3, "second", 0, " Second."))
    a.apply(delta(4, "first", 0, "First."))
    assert a.answer() == "First. Second."


def test_part_seen_only_through_deltas_sorts_after_started_parts() -> None:
    a = TextAssembler()
    a.apply(delta(1, "late", 0, " (late)"))
    a.apply(ev("part.start", 2, part_id="p0"))
    a.apply(delta(3, "p0", 0, "Answer"))
    assert a.answer() == "Answer (late)"


def test_reasoning_and_unknown_frames_are_ignored() -> None:
    a = TextAssembler()
    a.apply(ev("part.start", 1, part_id="r0", kind="reasoning"))
    assert a.apply(ev("reasoning.delta", 2, part_id="r0", offset=0, text="thinking")) == ""
    a.apply(ev("part.start", 3, part_id="p0", kind="text"))
    assert a.apply(ev("brand.new.event", 4, part_id="p0", offset=0, text="x")) == ""
    assert a.apply(delta(5, "p0", 0, "Answer")) == "Answer"
    # A text.delta into a reasoning part is folded but never surfaced as answer text.
    assert a.apply(delta(6, "r0", 0, "hidden")) == ""
    assert a.answer() == "Answer"
    assert a.text("r0") == "hidden"


def test_control_frames_and_malformed_payloads_are_harmless() -> None:
    a = TextAssembler()
    assert a.apply(ev("stream.heartbeat", None)) == ""
    assert a.apply(ev("text.delta", 1, part_id="p0", offset="0", text="x")) == ""
    assert a.apply(ev("text.delta", 2, part_id="p0", offset=-1, text="x")) == ""
    assert a.apply(ev("text.delta", 3, offset=0, text="x")) == ""
    assert a.apply(ev("text.delta", 4, part_id="p0", offset=0)) == ""
    assert a.answer() == ""
    assert a.text("missing") == ""


def test_replayed_part_start_keeps_its_first_position() -> None:
    a = TextAssembler()
    a.start_part("a")
    a.start_part("b")
    a.start_part("a")  # a resumed stream re-sends part.start
    assert a.part_ids == ["a", "b"]


@pytest.mark.parametrize("prefix", [0, 5, 12, 22])
def test_recorded_run_matches_the_engines_own_message(prefix: int) -> None:
    """A real 1,056-character answer, replayed from every point a resume could start."""
    frames = [RunEvent.model_validate(f) for f in recorded_frames()]
    message_end = next(f for f in frames if f.type == "message.end")
    expected = "".join(p["text"] for p in message_end.payload["message"]["parts"])

    a = TextAssembler()
    streamed = [a.apply(f) for f in frames]
    replayed = [a.apply(f) for f in frames[prefix:]]
    assert "".join(streamed) == expected
    assert a.answer() == expected
    assert utf16_len(expected) == 1056
    assert not any(replayed)
