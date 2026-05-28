#!/usr/bin/env python3
"""
RingSentry - Main Entry Point
=============================
启动入口，运行: python main.py
"""

from gui.app import App


def main():
    """Start the desktop GUI application."""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
