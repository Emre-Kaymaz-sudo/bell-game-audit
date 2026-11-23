"""Compatibility entry point for bell_game_audit.audit.private_history."""

from bell_game_audit.audit.private_history import (
    MAX_ROUNDS,
    MAX_ORDERS,
    MAX_SMALLER_SIDE,
    MAX_UPDATES_PER_ROUND,
    private_position_bounds,
    demo,
    main,
)


if __name__ == "__main__":
    raise SystemExit(main())
