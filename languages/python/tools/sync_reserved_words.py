"""Copy the normative dialect words into the self-contained Python distribution."""

from pathlib import Path

PY_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PY_ROOT.parents[1] / "core/schemas/dialect-reserved-words.json"
TARGET = PY_ROOT / "packages/parallax-core/src/parallax/core/dialect/dialect-reserved-words.json"

if __name__ == "__main__":
    TARGET.write_bytes(SOURCE.read_bytes())
