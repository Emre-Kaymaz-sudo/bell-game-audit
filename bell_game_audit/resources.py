"""File I/O for calibration models and generated JSON reports."""

import json
from pathlib import Path

default_model = Path(__file__).with_name("data") / "model.json"


def read_model(path=default_model):
    """Load a calibration from a UTF-8 JSON file."""
    with Path(path).open(encoding="utf-8-sig") as source:
        return json.load(source)


def write_report(report, output: Path | None = None) -> None:
    """Write the same indented, finite JSON to a file or standard output."""
    text = json.dumps(report, indent=2, allow_nan=False)
    if output is None:
        print(text)
    else:
        output.write_text(text + "\n", encoding="utf-8")
