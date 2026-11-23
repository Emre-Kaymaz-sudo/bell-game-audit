"""Compatibility entry point for bell_game_audit.audit.quota."""

from bell_game_audit.audit.quota import (
    position_bounds,
    ratio,
    audit,
    main,
)


if __name__ == "__main__":
    raise SystemExit(main())
