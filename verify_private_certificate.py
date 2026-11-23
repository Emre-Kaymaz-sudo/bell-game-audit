"""Compatibility entry point for bell_game_audit.certificates.verify."""

if __name__ == "__main__":
    # Keep the published standalone command usable with python -I -S.
    from pathlib import Path
    from runpy import run_path

    script = Path(__file__).resolve().parent / "bell_game_audit/certificates/verify.py"
    run_path(str(script), run_name="__main__")
else:
    from bell_game_audit.certificates.verify import (
        verify,
        main,
    )
