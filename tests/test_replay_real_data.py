from pathlib import Path

from custom_components.signalk_ha.parser import parse_delta_text


def test_replay_signalk_messages_do_not_break() -> None:
    data_path = Path(__file__).parent / "testdata.json"
    count = 0

    with data_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            count += 1
            result = parse_delta_text(text, ["vessels.self"])
            assert isinstance(result, dict), f"Line {line_number} should return dict"

    assert count > 0, "testdata.json should contain at least one message"
