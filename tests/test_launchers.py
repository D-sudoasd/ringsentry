"""Regression tests for the Windows launchers and GUI entry point."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ("START_RingSentry.cmd", "START_RingSentry.bat")


def test_windows_launchers_stay_identical():
    assert (ROOT / LAUNCHERS[0]).read_bytes() == (ROOT / LAUNCHERS[1]).read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="Windows batch launcher")
@pytest.mark.parametrize("launcher_name", LAUNCHERS)
def test_launcher_skips_broken_first_python_on_path(tmp_path, launcher_name):
    """A WindowsApps-like failed shim must not hide the next interpreter."""
    launch_dir = tmp_path / "launch"
    bad_dir = tmp_path / "bad-python"
    good_dir = tmp_path / "good-python"
    tools_dir = tmp_path / "tools"
    for directory in (launch_dir, bad_dir, good_dir, tools_dir):
        directory.mkdir()

    shutil.copy2(ROOT / launcher_name, launch_dir / launcher_name)
    shutil.copy2(Path(os.environ["SystemRoot"]) / "System32" / "where.exe", tools_dir)
    (bad_dir / "py.cmd").write_text("@exit /b 1\n", encoding="ascii")
    (bad_dir / "python.cmd").write_text("@exit /b 1\n", encoding="ascii")
    (good_dir / "python.cmd").write_text(
        "@echo runtime-import-ok\r\n@exit /b 0\r\n",
        encoding="ascii",
    )

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join((str(bad_dir), str(good_dir), str(tools_dir)))
    env["PYTHONPATH"] = str(ROOT)
    env["LocalAppData"] = str(tmp_path / "local-app-data-without-python")
    result = subprocess.run(
        [os.environ["ComSpec"], "/d", "/c", str(launch_dir / launcher_name), "--check"],
        cwd=launch_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "runtime-import-ok" in result.stdout
    assert str(good_dir / "python.cmd") in result.stdout
    assert "does not open the GUI" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows batch launcher")
@pytest.mark.parametrize("launcher_name", LAUNCHERS)
def test_launcher_skips_version_ok_interpreter_with_missing_dependencies(
    tmp_path, launcher_name
):
    launch_dir = tmp_path / "launch"
    bad_dir = tmp_path / "version-only-python"
    good_dir = tmp_path / "good-python"
    tools_dir = tmp_path / "tools"
    for directory in (launch_dir, bad_dir, good_dir, tools_dir):
        directory.mkdir()

    shutil.copy2(ROOT / launcher_name, launch_dir / launcher_name)
    shutil.copy2(Path(os.environ["SystemRoot"]) / "System32" / "where.exe", tools_dir)
    (bad_dir / "python.cmd").write_text(
        "@if defined RINGSENTRY_LAUNCHER_PROBE_SEEN exit /b 1\r\n"
        "@set RINGSENTRY_LAUNCHER_PROBE_SEEN=1\r\n"
        "@exit /b 0\r\n",
        encoding="ascii",
    )
    (good_dir / "python.cmd").write_text(
        "@echo runtime-import-ok\r\n@exit /b 0\r\n",
        encoding="ascii",
    )

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join((str(bad_dir), str(good_dir), str(tools_dir)))
    env["PYTHONPATH"] = str(ROOT)
    env["LocalAppData"] = str(tmp_path / "local-app-data-without-python")
    env.pop("RINGSENTRY_LAUNCHER_PROBE_SEEN", None)
    result = subprocess.run(
        [os.environ["ComSpec"], "/d", "/c", str(launch_dir / launcher_name), "--check"],
        cwd=launch_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert str(good_dir / "python.cmd") in result.stdout
    assert "runtime-import-ok" in result.stdout


def test_main_reports_tk_initialization_failure_without_traceback(monkeypatch, capsys):
    tk = pytest.importorskip("tkinter")

    import main

    def fail_to_create_app():
        raise tk.TclError("no display name and no $DISPLAY environment variable")

    import gui.app
    monkeypatch.setattr(gui.app, "App", fail_to_create_app)

    assert main.main() == 1
    captured = capsys.readouterr()
    assert "could not open the graphical interface" in captured.err
    assert "no display name" in captured.err
    assert "Traceback" not in captured.err


def test_main_runs_event_loop_and_returns_success(monkeypatch):
    pytest.importorskip("tkinter")

    import main

    state = {"mainloop_called": False}

    class DummyApp:
        def mainloop(self):
            state["mainloop_called"] = True

    import gui.app
    monkeypatch.setattr(gui.app, "App", DummyApp)

    assert main.main() == 0
    assert state["mainloop_called"] is True


def test_main_reports_missing_tk_without_traceback(monkeypatch, capsys):
    import builtins
    import sys

    import main

    real_import = builtins.__import__

    def reject_tk(name, *args, **kwargs):
        if name == "tkinter":
            raise ModuleNotFoundError("No module named 'tkinter'")
        return real_import(name, *args, **kwargs)

    # Other launcher tests import ``gui.app`` first.  Remove that cached module
    # so this test exercises the real import-failure path regardless of order.
    monkeypatch.delitem(sys.modules, "gui.app", raising=False)
    monkeypatch.setattr(builtins, "__import__", reject_tk)
    assert main.main() == 1
    captured = capsys.readouterr()
    assert "requires Python with Tk support" in captured.err
    assert "Traceback" not in captured.err
