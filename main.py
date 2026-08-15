#!/usr/bin/env python3
"""
RingSentry - Main Entry Point
=============================
启动入口，运行: python main.py
"""

import sys


def main() -> int:
    """Start the desktop GUI application."""
    try:
        from gui.app import App

        app = App()
    except (ImportError, ModuleNotFoundError) as exc:
        print(
            "ERROR: RingSentry requires Python with Tk support and its installed dependencies.",
            file=sys.stderr,
        )
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if exc.__class__.__name__ != "TclError":
            raise
        print(
            "ERROR: RingSentry could not open the graphical interface.",
            file=sys.stderr,
        )
        print(f"Tk initialization failed: {exc}", file=sys.stderr)
        print(
            "Run RingSentry in a graphical desktop session with a working display.",
            file=sys.stderr,
        )
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
