# x-launchpad.py - menu to run a .py file in this folder with the venv
# (.venv first, then venv), open cmd with the venv active, or start VS Code.
# Stdlib only.
import os
import re
import shutil
import string
import subprocess
import sys
from pathlib import Path

try:
    import msvcrt  # Windows-only, part of the standard library
except ImportError:
    msvcrt = None

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).resolve()

# Files to hide from the menu (case-insensitive). Add more names here.
EXCLUDE_LIST = [
    "x-run_py.py",
]

EXCLUDE = {SELF.name.lower()} | {name.lower() for name in EXCLUDE_LIST}

# Menu keys: 1-9, then a-z (c = cmd, v = VS Code, q = quit are reserved) -> up to 32 entries.
CMD_KEY = "c"
CODE_KEY = "v"
KEYS = [str(n) for n in range(1, 10)] + [
    ch for ch in string.ascii_lowercase if ch not in ("q", CMD_KEY, CODE_KEY)
]
QUIT_KEYS = {"q", "\x1b", "\x03"}  # q, Esc, Ctrl+C
CMD = object()   # marker returned by choose() for the cmd option
CODE = object()  # marker returned by choose() for the VS Code option


# ---------------------------------------------------------------- display

def _enable_colour():
    """Colour only on a real console, and not when NO_COLOR is set."""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:  # turn on ANSI escape codes in the Windows console (no cmd needed)
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


COLOUR = _enable_colour()
FANCY = _can_print("╭─╮│├┤╰╯·…")
BOX = dict(tl="╭", tr="╮", bl="╰", br="╯", h="─", v="│", ml="├", mr="┤") if FANCY \
    else dict(tl="+", tr="+", bl="+", br="+", h="-", v="|", ml="+", mr="+")
DOT = "·" if FANCY else "-"
ELLIPSIS = "…" if FANCY else "..."

STYLES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
          "blue": "34", "magenta": "35", "cyan": "36", "white": "37"}

# Style for the [1] [c] [q] keys - any of the STYLES above, e.g. ("green",) or ("bold", "yellow").
KEY_STYLE = ("bold",)
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


# ---------------------------------------------------------------- finding things

def find_venv_python():
    for name in (".venv", "venv"):
        py = HERE / name / "Scripts" / "python.exe"
        if py.exists():
            return py
    return None


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


def find_scripts():
    files = [p for p in HERE.glob("*.py") if p.name.lower() not in EXCLUDE]
    return sorted(files, key=lambda p: p.name.lower())


def find_vscode():
    """Find Code.exe itself - the 'code' command is code.cmd, which may be blocked."""
    candidates = []
    on_path = shutil.which("code")
    if on_path:  # ...\Microsoft VS Code\bin\code.cmd -> ...\Microsoft VS Code\Code.exe
        candidates.append(Path(on_path).resolve().parent.parent / "Code.exe")
    for var in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base:
            candidates.append(Path(base) / "Programs" / "Microsoft VS Code" / "Code.exe")
            candidates.append(Path(base) / "Microsoft VS Code" / "Code.exe")
    return next((p for p in candidates if p.exists()), None)


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


# ---------------------------------------------------------------- actions

def open_venv_cmd(py):
    """Start cmd.exe with the venv active - same env changes activate.bat makes,
    done here in Python so no .bat file has to run."""
    venv_dir = py.parent.parent
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["VIRTUAL_ENV_PROMPT"] = venv_dir.name
    env["PATH"] = str(py.parent) + os.pathsep + env.get("PATH", "")
    env["PROMPT"] = f"({venv_dir.name}) " + env.get("PROMPT", "$P$G")
    print(f"Opening cmd with {venv_dir.name} active in a new window.", flush=True)
    try:
        # New console window; the launchpad doesn't wait for it.
        subprocess.Popen(["cmd.exe"], cwd=HERE, env=env,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    except OSError as e:
        sys.exit(c(f"Could not start cmd.exe: {e}", "red"))
    return 0


def open_vscode():
    exe = find_vscode()
    if exe is None:
        sys.exit(c("VS Code (Code.exe) not found.", "red"))
    print(f"Opening VS Code in {HERE}", flush=True)
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([str(exe), str(HERE)], cwd=HERE, creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as e:
        sys.exit(c(f"Could not start VS Code: {e}", "red"))
    return 0


def run_script(py, script):
    print(c(f"Running {script.name}", "bold") + c(f"  ({py})", "dim"), flush=True)
    print(c(BOX["h"] * 60, "dim"), flush=True)
    rc = subprocess.call([str(py), str(script), *sys.argv[1:]], cwd=HERE)
    if rc != 0:  # pause on error so a double-clicked window doesn't vanish
        print("\n" + c(BOX["h"] * 60, "dim"))
        print(c(f"{script.name} failed - exit code {rc}.", "red", "bold")
              + "  Press any key to close...", end="", flush=True)
        read_key()
        print()
    return rc


# ---------------------------------------------------------------- menu

def choose(py, scripts, has_code):
    """Show the menu. Scripts and cmd need a venv; VS Code and quit always work."""
    keyed = dict(zip(KEYS, scripts)) if py else {}
    actions = {}

    # Header: title + venv/version, then the folder path.
    venv_info = ""
    if py:
        ver = venv_version(py)
        venv_info = py.parent.parent.name + (f" {DOT} Python {ver}" if ver else "")
    cols = shutil.get_terminal_size().columns
    path = shorten(str(HERE), max(20, cols - 6))
    header = [(c("x-launchpad", "bold"), c(venv_info, "dim")), (c(path, "dim"), "")]

    # Body: the scripts, or why there aren't any.
    if py is None:
        body = [(c("No .venv or venv found - scripts can't be run.", "yellow"), "")]
    elif not scripts:
        body = [(c("No .py files in this folder.", "yellow"), "")]
    else:
        name_room = max(10, cols - 12)
        body = [(f"{c(f'[{k}]', *KEY_STYLE)} {shorten(p.name, name_room)}", "")
                for k, p in keyed.items()]
        if len(scripts) > len(KEYS):
            body.append((c(f"(showing first {len(KEYS)} of {len(scripts)})", "dim"), ""))
        body.append(("", ""))  # blank line after the last script

    # Footer: standard options on one line.
    footer = []
    if py:
        actions[CMD_KEY] = CMD
        footer.append(f"{c(f'[{CMD_KEY}]', *KEY_STYLE)} cmd + venv")
    if has_code:
        actions[CODE_KEY] = CODE
        footer.append(f"{c(f'[{CODE_KEY}]', *KEY_STYLE)} VS Code")
    footer.append(f"{c('[q]', *KEY_STYLE)} quit")

    draw_box([header, body, [("   ".join(footer), "")]])
    print("\n" + c("Pick: ", "bold"), end="", flush=True)
    while True:
        key = read_key()
        if key in QUIT_KEYS or key == "":
            print("quit", end="\n\n")
            return None
        if key in actions or key in keyed:
            print(key, end="\n\n")
            return actions.get(key) or keyed[key]


def main():
    py = find_venv_python()
    scripts = find_scripts()
    has_code = find_vscode() is not None

    choice = choose(py, scripts, has_code)
    if choice is None:
        return 0
    if choice is CMD:
        return open_venv_cmd(py)
    if choice is CODE:
        return open_vscode()
    return run_script(py, choice)


if __name__ == "__main__":
    sys.exit(main())
