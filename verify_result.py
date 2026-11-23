"""Compatibility entry point for bell_game_audit.design.verify."""

if __name__ == "__main__":
    # Keep the published standalone command usable with python -I -S.
    from pathlib import Path
    from runpy import run_path

    script = Path(__file__).resolve().parent / "bell_game_audit/design/verify.py"
    run_path(str(script), run_name="__main__")
else:
    from bell_game_audit.design.verify import (
        unique_keys,
        reject_constant,
        object_value,
        triple,
        number,
        vector,
        integer_matrix,
        classical_probability,
        physical_probability,
        compare,
        verify_result,
        main,
    )
