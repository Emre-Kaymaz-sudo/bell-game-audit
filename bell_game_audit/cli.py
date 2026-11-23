"""Command-line entry point for the Bell game research tools."""

import argparse
from importlib import import_module
import sys


# Lazy loading keeps the independent verifiers usable without scientific libraries.
COMMANDS = {
    "history": (".audit.private_history", "Solve the four-card delayed-feedback game"),
    "audit": (".audit.quota", "Compute exact classical bounds for a quota block"),
    "search": (".design.search", "Search the finite game grid under a calibration model"),
    "controls": (".design.controls", "Compare the design with classical and quantum controls"),
    "sensitivity": (".design.sensitivity", "Stress-test the design under angle drift"),
    "build-certificate": (".certificates.build", "Construct a private-history certificate"),
    "verify-certificate": (".certificates.verify", "Independently check a private-history certificate"),
    "verify-result": (".design.verify", "Independently check a published design witness"),
    "survey": (".certificates.survey", "Certify the full finite design grid"),
    "replay": (".protocol.referee", "Replay a referee schedule from a binary stream"),
    "plot-drift": (".figures", "Render the measurement-drift figure (requires the figures extra)"),
}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    commands = "\n".join(f"  {name:20} {summary}" for name, (_, summary) in COMMANDS.items())
    parser = argparse.ArgumentParser(
        prog="bell-game-audit",
        description=__doc__,
        epilog=commands,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=COMMANDS, metavar="COMMAND")
    name = parser.parse_args(args[:1]).command
    module_name, _ = COMMANDS[name]
    command = import_module(module_name, package=__package__)
    prog = f"{parser.prog} {name}"
    try:
        return command.main(args[1:], prog=prog)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{prog}: {error}\n")
