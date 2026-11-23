"""Compatibility entry point for bell_game_audit.figures."""

from bell_game_audit.figures import (
    build_chart,
    main,
)


if __name__ == "__main__":
    from pathlib import Path
    import sys

    main(["--output", str(Path(__file__).with_name("drift-sweep.svg")), *sys.argv[1:]])
