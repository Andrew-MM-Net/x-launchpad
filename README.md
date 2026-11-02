# x-launchpad

A single-keypress menu for the folder it sits in. Use it to run a Python script with the folder's virtual environment, open a terminal with the venv active, or start your editor.

It's one file, uses only the standard library, and is built for Windows.

## Getting started

1. Copy `x-launchpad.py` into your project folder.
2. Double-click it, or run `python x-launchpad.py`.
3. Press a key. You don't need to press Enter.

If there's no venv, it asks whether to create one. See [Creating a venv](#creating-a-venv).

```text
╭──────────────────────────────────────────────────╮
│ x-launchpad                  .venv · Python 3.14 │
│ D:\code-live\my-project                          │
├──────────────────────────────────────────────────┤
│ [1] main.py                                      │
│ [2] sync.py                                      │
│                                                  │
├──────────────────────────────────────────────────┤
│ [c] cmd + venv   [v] VS Code   [q] quit          │
╰──────────────────────────────────────────────────╯

Pick:
```

## Menu keys

| Key | Action |
|---|---|
| `1`–`9`, then letters | Run that script |
| `c` | Open a terminal with the venv active, in a new window |
| `v` | Open this folder in your editor |
| `q`, Esc or Ctrl+C | Quit |

Up to 32 scripts get a key. If there are more, the menu shows a "showing first 32" note.

Anything you pass to the launchpad goes to the script you pick, so `x-launchpad.py --foo` runs `yourscript.py --foo`.

## Settings

All settings are at the top of `x-launchpad.py`. A setting with an invalid value stops the launchpad at startup, with a message saying what to fix.

Script names ignore case. Use the bare name for a file in this folder (`sync.py`) and `folder/name` for a subfolder (`tools/sync.py`).

### Python and venv

| Setting | Default | What it does |
|---|---|---|
| `VENV_NAMES` | `[".venv", "venv", "env"]` | Folders to check, in order; the first match wins |
| `ALLOW_SYSTEM_PYTHON` | `False` | With no venv, runs scripts with the system Python |
| `OFFER_CREATE_VENV` | `True` | With no venv, asks to create one at startup |

### Running scripts

| Setting | Default | What it does |
|---|---|---|
| `RUN_MODE` | `"same_window"` | Where scripts run: `"same_window"`, `"new_window"` or `"no_window"` |
| `SCRIPT_RUN_MODES` | `{}` | Per-script overrides, such as `{"server.py": "new_window"}` |
| `PAUSE_AFTER_RUN` | `"on_error"` | When to wait for a key after a script ends: `"always"`, `"on_error"` or `"never"` |
| `RETURN_TO_MENU` | `False` | `True` goes back to the menu; `False` closes the launchpad |
| `NO_WINDOW_LOG` | `"launchpad.log"` | Output file for `"no_window"`; `None` discards the output |
| `SCRIPT_ARGS` | `{}` | Arguments to always pass, such as `{"sync.py": ["--dry-run"]}` |
| `EXTRA_ENV` | `{}` | Environment variables for scripts and the terminal |

### Which scripts are listed

Scripts are listed by name, starting with this folder and then each subfolder in `SCAN_SUBFOLDERS`.

| Setting | Default | What it does |
|---|---|---|
| `EXCLUDE_LIST` | `["x-run_py.py"]` | Exact script names to hide |
| `EXCLUDE_PATTERNS` | `[]` | Wildcards to hide, matched on the file name or path, such as `["test_*"]` |
| `PINNED_SCRIPTS` | `[]` | Scripts to list first, in this order |
| `SCRIPT_LABELS` | `{}` | Friendly names, such as `{"sync.py": "Sync database"}` |
| `SCAN_SUBFOLDERS` | `[]` | Extra folders to list scripts from, such as `["tools"]` |

### Menu behaviour

| Setting | Default | What it does |
|---|---|---|
| `CLEAR_SCREEN` | `False` | Clears the screen before drawing the menu |
| `DEFAULT_KEY` | `None` | The key Enter triggers, such as `"1"`; `None` ignores Enter |
| `AUTO_RUN_SINGLE` | `False` | Skips the menu at startup if there's only one script |
| `SHOW_LAST_RESULT` | `False` | Shows the last script's name, exit code and run time in the menu |

### Terminal and editor

| Setting | Default | What it does |
|---|---|---|
| `TERMINAL` | `"cmd"` | What the terminal key opens: `"cmd"`, `"powershell"` or `"wt"` |
| `EDITOR_PATHS` | `["Code.exe"]` | Editor names or full paths; the first one found is used |
| `SHOW_TERMINAL_OPTION` | `True` | Shows the terminal option in the menu |
| `SHOW_EDITOR_OPTION` | `True` | Shows the editor option in the menu |
| `CMD_KEY` | `"c"` | Key for the terminal option: a letter other than `q` |
| `CODE_KEY` | `"v"` | Key for the editor option: a letter other than `q` |

### Appearance

| Setting | Default | What it does |
|---|---|---|
| `TITLE` | `"x-launchpad"` | Menu header text |
| `MENU_MIN_WIDTH` | `50` | Minimum box width |
| `HEADER_STYLE` | `("bold",)` | Title style |
| `KEY_STYLE` | `("bold",)` | Style of the `[1]` `[c]` `[q]` labels |

Styles can combine `bold`, `dim`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan` and `white`. A single style needs the trailing comma, as in `("bold",)`. Setting the `NO_COLOR` environment variable turns colour off.

## Run modes

| `RUN_MODE` | Where the script runs | Launchpad waits? | Good for |
|---|---|---|---|
| `"same_window"` | In the launchpad's window | Yes | Short scripts where you want to read the output |
| `"new_window"` | In its own console window | No | Servers, watchers and long jobs |
| `"no_window"` | With no console, using `pythonw.exe` | No | Tray apps and other GUI scripts |

To start a script, close the launchpad and leave the script running, use `"new_window"` or `"no_window"` with `RETURN_TO_MENU = False`. With `RETURN_TO_MENU = True`, the menu stays open so you can start several scripts.

When the launchpad doesn't wait, it can't see whether the script succeeded:

- **`"new_window"`:** the failure message and `PAUSE_AFTER_RUN` still work, but they appear in the script's own window.
- **`"no_window"`:** there's no pause and no failure message, so check `NO_WINDOW_LOG` for output and errors.

If you use `CLEAR_SCREEN` with `RETURN_TO_MENU` in `"same_window"`, set `PAUSE_AFTER_RUN = "always"`. Otherwise the menu clears the script's output as soon as it ends.

## Creating a venv

With `OFFER_CREATE_VENV` on and no venv found, the launchpad asks at startup:

```text
No venv found in this folder. Create one? [y/N] yes
Folder name [.venv]:
```

- **Folder name:** it suggests the first name from `VENV_NAMES` that isn't already taken. Press Enter to accept it, or type another name.
- **Names outside `VENV_NAMES`:** the new venv works for that session, and the launchpad warns you. Add the name to `VENV_NAMES` so it's found next time.
- **Requirements:** if `requirements.txt` exists, it asks before installing it.

The venv uses the Python that's running the launchpad. If you decline, the launchpad asks again on the next launch unless you set `OFFER_CREATE_VENV = False`.

## Good to know

- **Working folder:** scripts run from their own folder, so relative paths work. That includes scripts in a subfolder.
- **Exit codes:** with `RETURN_TO_MENU = False`, the launchpad exits with the script's exit code when it waited for the script. Otherwise it exits with 0 when you quit.
- **Finding the editor:** it looks for the `.exe` directly because commands like `code.cmd` may be blocked.
- **PowerShell:** the venv is set up without running `Activate.ps1`, so the execution policy doesn't block it.
- **Windows Terminal:** `"wt"` opens `cmd` with the venv active in a Windows Terminal window or tab.
- **Other systems:** venv detection only looks for `Scripts\python.exe`, so it won't find a Linux or macOS venv.
