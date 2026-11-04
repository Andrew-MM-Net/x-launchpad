# x-launchpad.py - menu to run a .py file in this folder or a python -m module
# with the venv, open a terminal with the venv active, or start your editor.
# Stdlib only.

# ================================ SETTINGS ================================
# Script names in these settings ignore case. Use the bare name for a file in
# this folder ("sync.py") and folder/name for a subfolder ("tools/sync.py").

# --- Python / venv ---
VENV_NAMES = [".venv", "venv", "env"]  # folders to check, in order; first match wins
ALLOW_SYSTEM_PYTHON = False            # no venv: run scripts with the system Python
OFFER_CREATE_VENV = True               # no venv: ask to create one, suggesting a folder name

# --- Running scripts ---
RUN_MODE = "same_window"               # "same_window" | "new_window" | "no_window"
SCRIPT_RUN_MODES = {}                  # per-script overrides: {"server.py": "new_window"}
PAUSE_AFTER_RUN = "on_error"           # "always" | "on_error" | "never" (no effect in "no_window")
RETURN_TO_MENU = False                 # True: back to the menu; False: launchpad closes
NO_WINDOW_LOG = "launchpad.log"        # output file for "no_window"; None = discard output
SCRIPT_ARGS = {}                       # always pass these: {"sync.py": ["--dry-run"]}
EXTRA_ENV = {}                         # environment variables: {"PYTHONUTF8": "1"}

# --- Running modules (python -m) ---
# Menu name -> module, then any arguments. Listed above the scripts and run from
# this folder. SCRIPT_RUN_MODES also accepts these menu names.
# {"Dev server": ["uvicorn", "app.main:app", "--port", "8000"]}
MODULES = {}

# --- Which scripts are listed ---
EXCLUDE_LIST = ["x-run_py.py"]         # exact script names to hide
EXCLUDE_PATTERNS = []                  # wildcards to hide, matched on file name or path: ["test_*", "_*"]
PINNED_SCRIPTS = []                    # listed ahead of other scripts, in this order: ["main.py"]
SCRIPT_LABELS = {}                     # friendly names: {"sync.py": "Sync database"}
SCAN_SUBFOLDERS = []                   # also list scripts from these folders: ["tools"]

# --- Menu behaviour ---
CLEAR_SCREEN = False                   # clear the screen before drawing the menu
DEFAULT_KEY = None                     # key that Enter triggers, e.g. "1"; None = ignore Enter
AUTO_RUN_SINGLE = False                # skip the menu at startup if there's only one script or module
SHOW_LAST_RESULT = False               # show the last script's name, exit code and run time

# --- Terminal and editor options ---
TERMINAL = "cmd"                       # "cmd" | "powershell" | "wt"
EDITOR_PATHS = ["Code.exe"]            # names or full paths, first found wins: ["Code.exe", "Cursor.exe"]
SHOW_TERMINAL_OPTION = True            # show the terminal option in the menu
SHOW_EDITOR_OPTION = True              # show the editor option in the menu
CMD_KEY = "c"                          # key for the terminal option (a letter other than q)
CODE_KEY = "v"                         # key for the editor option (a letter other than q)

# --- Appearance ---
TITLE = "x-launchpad"                  # menu header text
MENU_MIN_WIDTH = 50                    # minimum box width
HEADER_STYLE = ("bold",)               # title style
KEY_STYLE = ("bold",)                  # style of the [1] [c] [q] labels
# Styles: bold, dim, red, green, yellow, blue, magenta, cyan, white.

# ============================== END OF SETTINGS ==============================

import datetime
import fnmatch
import os
import re
import shutil
import string
import subprocess
import sys
import time
from collections import namedtuple
from pathlib import Path

try:
    import msvcrt  # Windows-only, part of the standard library
except ImportError:
    msvcrt = None

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).resolve()

SAME_WINDOW, NEW_WINDOW, NO_WINDOW = "same_window", "new_window", "no_window"
RUN_MODES = (SAME_WINDOW, NEW_WINDOW, NO_WINDOW)
PAUSE_CHOICES = ("always", "on_error", "never")
TERMINALS = ("cmd", "powershell", "wt")
INTERRUPTED = 130  # exit code reported when Ctrl+C stops a script

# Internal first arguments: the launchpad re-runs itself with these inside a
# new window, so the pause logic and venv setup stay in one place.
WORKER_RUN = "--x-launchpad-internal-run"
WORKER_TERMINAL = "--x-launchpad-internal-terminal"

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

CMD_KEY = str(CMD_KEY).lower()
CODE_KEY = str(CODE_KEY).lower()
DEFAULT_KEY = str(DEFAULT_KEY).lower() if DEFAULT_KEY is not None else None

# Menu keys: 1-9, then a-z without the reserved letters -> up to 32 entries.
KEYS = [str(n) for n in range(1, 10)] + [
    ch for ch in string.ascii_lowercase if ch not in ("q", CMD_KEY, CODE_KEY)
]
QUIT_KEYS = {"q", "\x1b", "\x03"}  # q, Esc, Ctrl+C
ENTER_KEYS = {"\r", "\n", ""}      # "" is a blank line when input is piped
CMD = object()   # marker returned by choose() for the terminal option
CODE = object()  # marker returned by choose() for the editor option

Result = namedtuple("Result", "name rc seconds mode")
Module = namedtuple("Module", "label name args")  # a menu entry from MODULES


def _lowered(mapping):
    return {str(k).lower(): v for k, v in mapping.items()}


LABELS = _lowered(SCRIPT_LABELS)
ARGS_BY_SCRIPT = _lowered(SCRIPT_ARGS)
MODE_BY_SCRIPT = _lowered(SCRIPT_RUN_MODES)
EXCLUDED_NAMES = {name.lower() for name in EXCLUDE_LIST}
EXCLUDED_GLOBS = [pattern.lower() for pattern in EXCLUDE_PATTERNS]


# ---------------------------------------------------------------- display

def _enable_vt():
    """Turn on ANSI escape codes in the console (no cmd needed)."""
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(k32.SetConsoleMode(handle, mode.value | 0x0004))  # VT processing
    except Exception:
        return False


def _can_print(text):
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


VT_ON = _enable_vt()
COLOUR = VT_ON and not os.environ.get("NO_COLOR")  # colour only on a real console
FANCY = _can_print("╭─╮│├┤╰╯·…")
BOX = dict(tl="╭", tr="╮", bl="╰", br="╯", h="─", v="│", ml="├", mr="┤") if FANCY \
    else dict(tl="+", tr="+", bl="+", br="+", h="-", v="|", ml="+", mr="+")
DOT = "·" if FANCY else "-"
ELLIPSIS = "…" if FANCY else "..."

STYLES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
          "blue": "34", "magenta": "35", "cyan": "36", "white": "37"}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def c(text, *styles):
    if not COLOUR or not styles:
        return text
    return f"\x1b[{';'.join(STYLES[s] for s in styles)}m{text}\x1b[0m"


def vlen(text):
    """Visible length (ignores colour codes)."""
    return len(ANSI_RE.sub("", text))


def shorten(text, width):
    """Cut text to width, keeping the end (useful for paths)."""
    if len(text) <= width:
        return text
    return ELLIPSIS + text[-(width - len(ELLIPSIS)):]


def draw_box(sections, min_width=50):
    """sections: list of lists of (left, right) rows; right may be ''."""
    rows = [r for sec in sections for r in sec]
    need = max(vlen(l) + (vlen(r) + 2 if vlen(r) else 0) for l, r in rows)
    inner = max(min_width, need + 2)
    inner = min(inner, shutil.get_terminal_size().columns - 2)

    def line(left, right):
        gap = inner - 2 - vlen(left) - vlen(right)
        return f"{BOX['v']} {left}{' ' * max(gap, 1 if right else 0)}{right} {BOX['v']}"

    out = [BOX["tl"] + BOX["h"] * inner + BOX["tr"]]
    for i, sec in enumerate(sections):
        if i:
            out.append(BOX["ml"] + BOX["h"] * inner + BOX["mr"])
        out += [line(l, r) for l, r in sec]
    out.append(BOX["bl"] + BOX["h"] * inner + BOX["br"])
    print("\n".join(out))
    return inner


def clear_screen():
    if VT_ON:
        print("\x1b[2J\x1b[H", end="", flush=True)


def format_seconds(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s"


# ---------------------------------------------------------------- settings check

def settings_problems():
    """Catch typos up front so a bad value can't silently change behaviour."""
    problems = []

    def one_of(name, value, allowed):
        if value not in allowed:
            problems.append(f"{name} is {value!r} - use one of: {', '.join(allowed)}")

    one_of("RUN_MODE", RUN_MODE, RUN_MODES)
    one_of("PAUSE_AFTER_RUN", PAUSE_AFTER_RUN, PAUSE_CHOICES)
    one_of("TERMINAL", TERMINAL, TERMINALS)
    for script, mode in SCRIPT_RUN_MODES.items():
        one_of(f"SCRIPT_RUN_MODES[{script!r}]", mode, RUN_MODES)

    for script, args in SCRIPT_ARGS.items():
        if not isinstance(args, (list, tuple)):
            problems.append(f"SCRIPT_ARGS[{script!r}] must be a list, like [\"--dry-run\"]")

    for label, spec in MODULES.items():
        if (not isinstance(spec, (list, tuple)) or not spec
                or not all(isinstance(part, str) for part in spec)):
            problems.append(f"MODULES[{label!r}] must be a list of strings, "
                            "like [\"my_pkg.tool\", \"--port\", \"8000\"]")
        elif not re.fullmatch(r"[^\W\d]\w*(\.[^\W\d]\w*)*", spec[0]):
            problems.append(f"MODULES[{label!r}] starts with {spec[0]!r} - "
                            "the first item must be a module name, like \"my_pkg.tool\"")

    for name, value in (("CMD_KEY", CMD_KEY), ("CODE_KEY", CODE_KEY)):
        if len(value) != 1 or value not in string.ascii_lowercase or value == "q":
            problems.append(f"{name} is {value!r} - use a single letter other than q")
    if CMD_KEY == CODE_KEY:
        problems.append(f"CMD_KEY and CODE_KEY are both {CMD_KEY!r} - use different letters")
    if DEFAULT_KEY is not None and DEFAULT_KEY not in [*KEYS, CMD_KEY, CODE_KEY, "q"]:
        problems.append(f"DEFAULT_KEY is {DEFAULT_KEY!r} - use a menu key, or None")

    for name, value in (("HEADER_STYLE", HEADER_STYLE), ("KEY_STYLE", KEY_STYLE)):
        if not isinstance(value, (tuple, list)):
            problems.append(f"{name} must be a tuple, like (\"bold\",) - note the comma")
        else:
            for style in value:
                if style not in STYLES:
                    problems.append(f"{name} has unknown style {style!r}")

    for folder in SCAN_SUBFOLDERS:
        path = Path(folder)
        if path.is_absolute() or ".." in path.parts:
            problems.append(f"SCAN_SUBFOLDERS entry {folder!r} must be a folder inside this one")

    if not isinstance(MENU_MIN_WIDTH, int) or MENU_MIN_WIDTH < 1:
        problems.append(f"MENU_MIN_WIDTH is {MENU_MIN_WIDTH!r} - use a positive whole number")
    return problems


# ---------------------------------------------------------------- finding things

def find_venv_python():
    for name in VENV_NAMES:
        py = HERE / name / "Scripts" / "python.exe"
        if py.exists():
            return py
    return None


def base_python():
    """The real interpreter, even if the launchpad itself runs from a venv."""
    return Path(getattr(sys, "_base_executable", None) or sys.executable)


def venv_version(py):
    """Python version from the venv's pyvenv.cfg (no need to run anything)."""
    try:
        for line in (py.parent.parent / "pyvenv.cfg").read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() in ("version", "version_info"):
                return ".".join(value.strip().split(".")[:2])
    except OSError:
        pass
    return None


def rel_name(path):
    """How a script is shown: sync.py, or tools/sync.py for a subfolder."""
    return Path(os.path.relpath(path, HERE)).as_posix()


def script_key(path):
    """How a script is matched against the settings."""
    return rel_name(path).lower()


def is_excluded(path):
    if path.resolve() == SELF:
        return True
    key = script_key(path)
    if key in EXCLUDED_NAMES:
        return True
    name = path.name.lower()
    return any(fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(key, pattern)
               for pattern in EXCLUDED_GLOBS)


def find_scripts():
    """Top-level scripts, then each subfolder's, with pinned scripts moved first."""
    found = []
    for folder in [HERE] + [HERE / name for name in SCAN_SUBFOLDERS]:
        in_folder = [p for p in folder.glob("*.py") if p.is_file() and not is_excluded(p)]
        found += sorted(in_folder, key=lambda p: p.name.lower())

    by_key = {}
    for path in found:
        by_key.setdefault(script_key(path), path)
    pinned = []
    for name in PINNED_SCRIPTS:
        path = by_key.pop(name.lower(), None)
        if path is not None:
            pinned.append(path)
    return pinned + list(by_key.values())


def find_modules():
    return [Module(label, spec[0], list(spec[1:])) for label, spec in MODULES.items()]


def entry_label(entry):
    """How a menu entry is shown: a module's name from MODULES, or a script's label."""
    if isinstance(entry, Module):
        return entry.label
    return LABELS.get(script_key(entry), rel_name(entry))


def _find_editor_by_name(exe):
    """Find the editor's .exe itself - its command on PATH is often a .cmd file,
    which may be blocked."""
    stem = Path(exe).stem
    candidates = []
    direct = shutil.which(exe)
    if direct:
        candidates.append(Path(direct))
    on_path = shutil.which(stem)
    if on_path:  # ...\Microsoft VS Code\bin\code.cmd -> ...\Microsoft VS Code\Code.exe
        candidates += [parent / exe for parent in Path(on_path).resolve().parents[:4]]
    folders = [stem] + (["Microsoft VS Code"] if stem.lower() == "code" else [])
    for var in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base:
            for folder in folders:
                candidates.append(Path(base) / "Programs" / folder / exe)
                candidates.append(Path(base) / folder / exe)
    return next((p for p in candidates if p.exists()), None)


def find_editor():
    for entry in EDITOR_PATHS:
        path = Path(entry)
        if path.parent != Path("."):  # a full path, used exactly as given
            if path.exists():
                return path
            continue
        exe = entry if entry.lower().endswith(".exe") else entry + ".exe"
        found = _find_editor_by_name(exe)
        if found:
            return found
    return None


def editor_label(exe):
    return {"code": "VS Code"}.get(exe.stem.lower(), exe.stem)


# ---------------------------------------------------------------- input

def read_key():
    """One keypress, no Enter needed (Windows console). Falls back to input()."""
    if msvcrt and sys.stdin.isatty():
        while True:
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):  # arrow/function keys send two codes; ignore them
                msvcrt.getwch()
                continue
            return ch.lower()
    try:
        return input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "q"


def read_line(prompt):
    """A typed line, or None if input ended or Ctrl+C was pressed."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def wait_for_key(message):
    print(message + "  Press any key to continue...", end="", flush=True)
    read_key()
    print()


def report_problem(message):
    """Show an error and wait, so a double-clicked window doesn't vanish."""
    wait_for_key(c(message, "red"))
    return 1


# ---------------------------------------------------------------- creating a venv

def suggested_venv_name():
    """The first name from VENV_NAMES that isn't already taken."""
    for name in VENV_NAMES:
        if not (HERE / name).exists():
            return name
    return ".venv"


def venv_name_problem(name):
    if name in (".", "..") or name != name.rstrip(" ."):
        return "That isn't a usable folder name."
    if set(name) & set('<>:"/\\|?*'):
        return 'Use a plain folder name, without any of: < > : " / \\ | ? *'
    if (HERE / name).exists():
        return f"{name} already exists here - choose another name."
    return None


def create_venv(name):
    target = HERE / name
    print(f"\nCreating {name} with {base_python()}...", flush=True)
    try:
        rc = subprocess.call([str(base_python()), "-m", "venv", str(target)], cwd=HERE)
    except OSError as e:
        report_problem(f"Could not start Python: {e}")
        return None
    py = target / "Scripts" / "python.exe"
    if rc != 0 or not py.exists():
        report_problem(f"Creating {name} failed (exit code {rc}). "
                       "A partial folder may be left behind.")
        return None
    print(c(f"Created {name}.", "green"), flush=True)
    return py


def offer_requirements(py):
    if not (HERE / "requirements.txt").exists():
        return
    print("Install requirements.txt? [Y/n] ", end="", flush=True)
    key = read_key()
    print("yes" if key == "y" or key in ENTER_KEYS else "no", flush=True)
    if key != "y" and key not in ENTER_KEYS:
        return
    try:
        rc = subprocess.call([str(py), "-m", "pip", "install", "-r", "requirements.txt"], cwd=HERE)
    except OSError as e:
        report_problem(f"Could not start pip: {e}")
        return
    if rc != 0:
        report_problem(f"Installing requirements.txt failed (exit code {rc}). "
                       "The venv was kept.")


def offer_create_venv():
    """Ask to create a venv, suggesting a folder name. Returns its python, or None."""
    print("No venv found in this folder. Create one? [y/N] ", end="", flush=True)
    key = read_key()
    print("yes" if key == "y" else "no", flush=True)
    if key != "y":
        print()
        return None

    suggested = suggested_venv_name()
    while True:
        answer = read_line(f"Folder name [{suggested}]: ")
        if answer is None:
            return None
        name = answer or suggested
        problem = venv_name_problem(name)
        if problem is None:
            break
        print(c(problem, "yellow"))

    py = create_venv(name)
    if py is None:
        return None
    offer_requirements(py)
    if name.lower() not in {n.lower() for n in VENV_NAMES}:
        wait_for_key(c(f"{name} isn't in VENV_NAMES, so it's only used for this session. "
                       "Add it to find it next time.", "yellow"))
    print()
    return py


# ---------------------------------------------------------------- actions

def venv_env(py):
    """The same env changes activate.bat makes, done here so no .bat file has to run."""
    venv_dir = py.parent.parent
    env = {**os.environ, **EXTRA_ENV}
    env.pop("PYTHONHOME", None)
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["VIRTUAL_ENV_PROMPT"] = venv_dir.name
    env["PATH"] = str(py.parent) + os.pathsep + env.get("PATH", "")
    env["PROMPT"] = f"({venv_dir.name}) " + env.get("PROMPT", "$P$G")
    return env


def script_env():
    return {**os.environ, **EXTRA_ENV}


def open_terminal(py):
    """Open the chosen terminal with the venv active; the launchpad doesn't wait."""
    venv_dir = py.parent.parent
    print(f"Opening {TERMINAL} with {venv_dir.name} active in a new window.", flush=True)
    env = venv_env(py)
    try:
        if TERMINAL == "wt":
            # A running Windows Terminal may not pass our environment to a new
            # tab, so the tab runs the launchpad, which sets it up and starts cmd.
            subprocess.Popen(["wt.exe", "-d", str(HERE), str(py), str(SELF),
                              WORKER_TERMINAL, str(py)], cwd=HERE)
        elif TERMINAL == "powershell":
            label = venv_dir.name.replace("'", "''")
            prompt = f"function prompt {{ '({label}) PS ' + (Get-Location) + '> ' }}"
            subprocess.Popen(["powershell.exe", "-NoLogo", "-NoExit", "-Command", prompt],
                             cwd=HERE, env=env, creationflags=CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(["cmd.exe"], cwd=HERE, env=env, creationflags=CREATE_NEW_CONSOLE)
    except OSError as e:
        return report_problem(f"Could not start {TERMINAL}: {e}")
    return 0


def open_editor(exe):
    print(f"Opening {editor_label(exe)} in {HERE}", flush=True)
    try:
        subprocess.Popen([str(exe), str(HERE)], cwd=HERE,
                         creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as e:
        return report_problem(f"Could not start {editor_label(exe)}: {e}")
    return 0


def run_and_report(py, name, target, cwd):
    """Run in this window and wait, then report and pause as PAUSE_AFTER_RUN says.
    target is what follows python on the command line: a script or -m module, then args."""
    print(c(f"Running {name}", "bold") + c(f"  ({py})", "dim"), flush=True)
    print(c(BOX["h"] * 60, "dim"), flush=True)
    try:
        rc = subprocess.call([str(py), *target], cwd=cwd, env=script_env())
    except KeyboardInterrupt:
        rc = INTERRUPTED
    except OSError as e:
        print(c(f"Could not start {name}: {e}", "red"))
        rc = 1

    pause = PAUSE_AFTER_RUN == "always" or (PAUSE_AFTER_RUN == "on_error" and rc != 0)
    if rc == 0 and not pause:
        return rc
    print("\n" + c(BOX["h"] * 60, "dim"))
    if rc == INTERRUPTED:
        message = c(f"{name} stopped with Ctrl+C.", "yellow", "bold")
    elif rc != 0:
        message = c(f"{name} failed - exit code {rc}.", "red", "bold")
    else:
        message = c(f"{name} finished.", "green", "bold")
    if pause:
        wait_for_key(message)
    else:
        print(message, flush=True)
    return rc


def start_new_window(py, name, target, cwd):
    """New console that runs this file as a worker, so the pause still works there."""
    subprocess.Popen([str(py), str(SELF), WORKER_RUN, str(py), name, *target],
                     cwd=cwd, env=script_env(), creationflags=CREATE_NEW_CONSOLE)


def start_no_window(py, name, target, cwd):
    """No console at all: pythonw.exe, with output going to NO_WINDOW_LOG."""
    pythonw = py.parent / "pythonw.exe"
    if not pythonw.exists():
        print(c(f"pythonw.exe not found - using {py.name} without a window.", "yellow"))
        pythonw = py
    env = {**script_env(), "PYTHONUNBUFFERED": "1"}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    command = [str(pythonw), *target]
    if NO_WINDOW_LOG is None:
        subprocess.Popen(command, cwd=cwd, env=env, creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return
    log_path = HERE / NO_WINDOW_LOG
    with open(log_path, "a", encoding="utf-8") as log:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"\n--- {stamp} {name}\n")
        log.flush()
        subprocess.Popen(command, cwd=cwd, env=env, creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    print(f"Output goes to {log_path}", flush=True)


def launch(py, entry):
    """Run a menu entry: a script path or a Module."""
    if isinstance(entry, Module):
        name, key, cwd = entry.label, entry.label.lower(), HERE
        target = ["-m", entry.name, *entry.args]
    else:
        name, key, cwd = rel_name(entry), script_key(entry), entry.parent
        target = [str(entry), *ARGS_BY_SCRIPT.get(key, [])]
    target += sys.argv[1:]
    mode = MODE_BY_SCRIPT.get(key, RUN_MODE)

    if mode == SAME_WINDOW:
        started = time.monotonic()
        rc = run_and_report(py, name, target, cwd)
        return Result(name, rc, time.monotonic() - started, mode)

    print(f"Starting {name} ({mode.replace('_', ' ')}).", flush=True)
    try:
        if mode == NEW_WINDOW:
            start_new_window(py, name, target, cwd)
        else:
            start_no_window(py, name, target, cwd)
    except OSError as e:
        report_problem(f"Could not start {name}: {e}")
        return Result(name, 1, None, mode)
    return Result(name, None, None, mode)


# ---------------------------------------------------------------- workers

def worker_main(argv):
    """Runs inside a new window started by the launchpad. Returns an exit code."""
    kind, py = argv[0], Path(argv[1])
    if kind == WORKER_RUN:
        return run_and_report(py, argv[2], argv[3:], Path.cwd())
    terminal = subprocess.Popen(["cmd.exe"], cwd=HERE, env=venv_env(py))
    while True:
        try:
            return terminal.wait()
        except KeyboardInterrupt:  # Ctrl+C is meant for cmd, so keep waiting
            pass


# ---------------------------------------------------------------- menu

def last_result_row(result):
    if result.rc is None:
        text = f"Last: {result.name} {DOT} started in {result.mode.replace('_', ' ')}"
        return (c(text, "dim"), "")
    if result.rc == INTERRUPTED:
        outcome, colour = "stopped with Ctrl+C", "yellow"
    else:
        outcome, colour = f"exit {result.rc}", "green" if result.rc == 0 else "red"
    text = f"Last: {result.name} {DOT} {outcome}"
    if result.seconds is not None:
        text += f" {DOT} {format_seconds(result.seconds)}"
    return (c(text, colour), "")


def choose(venv_py, run_py, entries, editor, last_result):
    """Show the menu. Scripts and modules need a Python to run with, the terminal
    needs a venv; the editor and quit always work."""
    keyed = dict(zip(KEYS, entries)) if run_py else {}
    actions = {}

    # Header: title + Python in use, then the folder path.
    if venv_py:
        ver = venv_version(venv_py)
        python_info = venv_py.parent.parent.name + (f" {DOT} Python {ver}" if ver else "")
    elif run_py:
        python_info = f"system {DOT} Python {sys.version_info[0]}.{sys.version_info[1]}"
    else:
        python_info = ""
    cols = shutil.get_terminal_size().columns
    path = shorten(str(HERE), max(20, cols - 6))
    header = [(c(TITLE, *HEADER_STYLE), c(python_info, "dim")), (c(path, "dim"), "")]
    if SHOW_LAST_RESULT and last_result:
        header.append(last_result_row(last_result))

    # Body: the modules and scripts, or why there aren't any.
    if run_py is None:
        body = [(c("No venv found - scripts can't be run.", "yellow"), "")]
    elif not entries:
        body = [(c("No .py files in this folder.", "yellow"), "")]
    else:
        name_room = max(10, cols - 12)
        body = []
        for k, entry in keyed.items():
            body.append((f"{c(f'[{k}]', *KEY_STYLE)} {shorten(entry_label(entry), name_room)}", ""))
        if len(entries) > len(KEYS):
            body.append((c(f"(showing first {len(KEYS)} of {len(entries)})", "dim"), ""))
        body.append(("", ""))  # blank line after the last entry

    # Footer: standard options on one line.
    footer = []
    if venv_py and SHOW_TERMINAL_OPTION:
        actions[CMD_KEY] = CMD
        footer.append(f"{c(f'[{CMD_KEY}]', *KEY_STYLE)} {TERMINAL} + venv")
    if editor:
        actions[CODE_KEY] = CODE
        footer.append(f"{c(f'[{CODE_KEY}]', *KEY_STYLE)} {editor_label(editor)}")
    footer.append(f"{c('[q]', *KEY_STYLE)} quit")

    draw_box([header, body, [("   ".join(footer), "")]], MENU_MIN_WIDTH)
    print("\n" + c("Pick: ", "bold"), end="", flush=True)
    while True:
        key = read_key()
        if key in ENTER_KEYS:
            if DEFAULT_KEY is not None:
                key = DEFAULT_KEY
            elif key == "":  # blank piped line: nothing more is coming
                key = "q"
            else:
                continue
        if key in QUIT_KEYS:
            print("quit", end="\n\n")
            return None
        if key in actions or key in keyed:
            print(key, end="\n\n")
            return actions.get(key) or keyed[key]


def main():
    if len(sys.argv) > 2 and sys.argv[1] in (WORKER_RUN, WORKER_TERMINAL):
        return worker_main(sys.argv[1:])

    problems = settings_problems()
    if problems:
        print(c("Fix these settings at the top of x-launchpad.py:", "red", "bold"))
        for problem in problems:
            print(f"  {problem}")
        wait_for_key("")
        return 2

    created_py = None
    if find_venv_python() is None and OFFER_CREATE_VENV:
        created_py = offer_create_venv()

    last_result = None
    first_pass = True
    while True:
        venv_py = created_py or find_venv_python()
        run_py = venv_py or (base_python() if ALLOW_SYSTEM_PYTHON else None)
        entries = [*find_modules(), *find_scripts()]
        editor = find_editor() if SHOW_EDITOR_OPTION else None

        if first_pass and AUTO_RUN_SINGLE and run_py and len(entries) == 1:
            choice = entries[0]
        else:
            if CLEAR_SCREEN:
                clear_screen()
            choice = choose(venv_py, run_py, entries, editor, last_result)
        first_pass = False

        if choice is None:
            return 0
        if choice is CMD:
            rc = open_terminal(venv_py)
        elif choice is CODE:
            rc = open_editor(editor)
        else:
            last_result = launch(run_py, choice)
            rc = last_result.rc or 0
        if not RETURN_TO_MENU:
            return rc


if __name__ == "__main__":
    sys.exit(main())
