"""Backward-compatible uk-property command."""
from open_properties.cli import *  # noqa: F401,F403
from open_properties.cli import main as _main

def main(argv=None):
    return _main(argv, prog="uk-property")

if __name__ == "__main__":
    main()
