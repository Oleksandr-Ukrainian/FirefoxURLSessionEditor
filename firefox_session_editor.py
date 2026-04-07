#!/usr/bin/env python3
"""
Firefox / Browser sessionstore.jsonlz4 Editor  v4
- Browser filter panel: list all supported browsers, detect which are installed,
  checkboxes to include/exclude, Refresh button rescans and adds unknown profiles
- Auto-find scoped to checked browsers
- Domain replace with correct prefix handling (no auto-add https://)
- Dry-run, 20-level undo, backup archive (.rar / .zip), JSON validate, round-trip verify
- Persistent settings + field history, Themes, Font profiles, Scaling
- Done popup: Open Folder / Continue / Close App
Requires: pip install lz4
"""

import os, sys, json, glob, shutil, struct, re, zipfile, subprocess, datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, font as tkfont
import lz4.block

# ─── Config persistence ───────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".firefox_session_editor_config.json"
HISTORY_MAX = 25
MAGIC = b"mozLz40\0"

DEFAULT_CONFIG = {
    "theme": "🌸 Sakura",
    "font_profile": "Mono",
    "scaling": 1.0,
    "backup_fmt": "rar",
    "backup_enabled": True,
    "validate": True,
    "verify": True,
    "match_scheme": False,
    "match_subdomains": False,
    "geometry": "860x760+80+40",
    "enabled_browsers": [],   # empty = all
    "histories": {},
}

def load_config() -> dict:
    try:
        if CONFIG_PATH.is_file():
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text("utf-8"))}
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)

def save_config(data: dict):
    try:
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass

# ─── Themes ───────────────────────────────────────────────────────────────────

THEMES: Dict[str, dict] = {
    # bg, fg, accent, entry, log_bg, cb_fg (checkbox text — bright on dark, dark on light), cb_sel (checkmark box)
    "🌑 Dark":           {"bg":"#121212","fg":"#E0E0E0","accent":"#03DAC6","entry":"#1E1E1E","log_bg":"#0D0D0D",    "cb_fg":"#FFFFFF","cb_sel":"#222222"},
    "🟣 Dark Purple":    {"bg":"#14001F","fg":"#E9D8FD","accent":"#9F7AEA","entry":"#1F102A","log_bg":"#0A0012",    "cb_fg":"#F5EEFF","cb_sel":"#2A0040"},
    "🌙 Midnight Blue":  {"bg":"#020817","fg":"#E0F2FE","accent":"#38BDF8","entry":"#020617","log_bg":"#010412",    "cb_fg":"#F0F9FF","cb_sel":"#0A2040"},
    "🎨 Monokai":        {"bg":"#272822","fg":"#F8F8F2","accent":"#FD971F","entry":"#3E3D32","log_bg":"#1E1F1A",    "cb_fg":"#FFFFFF","cb_sel":"#4A4840"},
    "❄️ Nord":           {"bg":"#2E3440","fg":"#E5E9F0","accent":"#88C0D0","entry":"#3B4252","log_bg":"#252A34",    "cb_fg":"#FFFFFF","cb_sel":"#434C5E"},
    "💻 Cyberpunk":      {"bg":"#0A0015","fg":"#E8F0FF","accent":"#FF00FF","entry":"#1A0033","log_bg":"#06000D",    "cb_fg":"#F0E0FF","cb_sel":"#300060"},
    "🌲 Forest":         {"bg":"#022C22","fg":"#ECFDF5","accent":"#34D399","entry":"#064E3B","log_bg":"#011A15",    "cb_fg":"#F0FFF8","cb_sel":"#065040"},
    "🌸 Sakura":         {"bg":"#F3E8F1","fg":"#5C2D4A","accent":"#D4608A","entry":"#E8C8DC","log_bg":"#EDD5E8",    "cb_fg":"#2A0018","cb_sel":"#8B1A3A"},
    "☀️ Solarized":      {"bg":"#002B36","fg":"#EEE8D5","accent":"#B58900","entry":"#073642","log_bg":"#001F29",    "cb_fg":"#FDF6E3","cb_sel":"#103040"},
    "🧡 Amber":          {"bg":"#1A0F00","fg":"#FFD080","accent":"#FFA500","entry":"#2A1800","log_bg":"#110A00",    "cb_fg":"#FFE8A0","cb_sel":"#3A2000"},
    "🐼 Darkula":        {"bg":"#2B2B2B","fg":"#A9B7C6","accent":"#FFA500","entry":"#323232","log_bg":"#1E1E1E",    "cb_fg":"#D8E6F5","cb_sel":"#404040"},
    "☀️ Light":          {"bg":"#FFFFFF","fg":"#202020","accent":"#1E88E5","entry":"#E8E8E8","log_bg":"#EEEEEE",    "cb_fg":"#0A0A0A","cb_sel":"#1565C0"},
}
THEME_CODES = list(THEMES.keys())
FONT_PROFILES = ["Default","Mono","Mono Large","Mono Small","Coding","Large","Tiny","Serif","Rounded"]
SCALING_LABELS = [f"{i}%" for i in range(60, 181, 5)]

# ─── Browser definitions ──────────────────────────────────────────────────────
# Each entry: display_name -> list of (relative profile root segments by platform)
# Format: {"win": [relative from APPDATA], "mac": [relative from ~/Library/App Support], "lin": [relative from home]}

BROWSERS: Dict[str, dict] = {
    "Firefox":    {"win":["Mozilla/Firefox/Profiles"],          "mac":["Firefox/Profiles"],        "lin":[".mozilla/firefox","snap/firefox/common/.mozilla/firefox",".var/app/org.mozilla.firefox/.mozilla/firefox"]},
    "LibreWolf":  {"win":["LibreWolf/Profiles"],                 "mac":["LibreWolf/Profiles"],       "lin":[".librewolf","snap/librewolf/common/.librewolf"]},
    "Waterfox":   {"win":["Waterfox/Profiles"],                  "mac":["Waterfox/Profiles"],        "lin":[".waterfox"]},
    "Floorp":     {"win":["Floorp/Profiles"],                    "mac":["Floorp/Profiles"],          "lin":[".floorp"]},
    "Pale Moon":  {"win":["Moonchild Productions/Pale Moon/Profiles"],"mac":["Pale Moon/Profiles"], "lin":[".moonchild productions/pale moon"]},
    "Basilisk":   {"win":["Moonchild Productions/Basilisk/Profiles"],"mac":["Basilisk/Profiles"],   "lin":[".moonchild productions/basilisk"]},
    "IceCat":     {"win":["Mozilla/icecat/Profiles"],            "mac":["IceCat/Profiles"],          "lin":[".mozilla/icecat"]},
    "Iceweasel":  {"win":["Mozilla/iceweasel/Profiles"],         "mac":["Iceweasel/Profiles"],       "lin":[".mozilla/iceweasel"]},
    "Zen Browser":{"win":["Zen/Profiles"],                       "mac":["Zen/Profiles"],             "lin":[".zen"]},
    "Mercury":    {"win":["Mercury/Profiles"],                   "mac":["Mercury/Profiles"],         "lin":[".mercury"]},
    "Betterbird": {"win":["Betterbird/Profiles"],                 "mac":["Betterbird/Profiles"],      "lin":[".betterbird"]},
}

def _profile_roots(browser_name: str) -> List[Path]:
    """Return list of Paths that might be the profile root for this browser."""
    home = Path.home()
    info = BROWSERS.get(browser_name, {})
    roots: List[Path] = []

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        for rel in info.get("win", []):
            roots.append(Path(appdata) / rel)
            roots.append(Path(localappdata) / rel)
        # MSIX / Microsoft Store packages
        pkg_dir = Path(localappdata) / "Packages"
        if pkg_dir.is_dir():
            kw = browser_name.lower().replace(" ", "")
            for entry in pkg_dir.iterdir():
                if kw in entry.name.lower() or "mozilla.firefox" in entry.name.lower():
                    for rel in info.get("win", []):
                        roots.append(entry / "LocalCache" / "Roaming" / rel)
    elif sys.platform == "darwin":
        lib = home / "Library" / "Application Support"
        for rel in info.get("mac", []):
            roots.append(lib / rel)
    else:
        for rel in info.get("lin", []):
            roots.append(home / rel)

    return roots

def scan_browser(browser_name: str) -> List[str]:
    """Return list of absolute paths to sessionstore.jsonlz4 for this browser."""
    results = []
    for root in _profile_roots(browser_name):
        if root.is_dir():
            for p in root.glob("*/sessionstore.jsonlz4"):
                results.append(str(p.resolve()))
    return results

def detect_installed_browsers() -> Dict[str, List[str]]:
    """Scan all browsers, return {name: [paths]} for those with at least 1 session file."""
    found: Dict[str, List[str]] = {}
    for name in BROWSERS:
        files = scan_browser(name)
        if files:
            found[name] = files
    return found

def find_session_files(enabled: Optional[Set[str]] = None) -> List[Tuple[str, str]]:
    """Returns list of (browser_name, abs_path) filtered by enabled set."""
    results = []
    for name in (enabled if enabled else BROWSERS):
        if name not in BROWSERS:
            continue
        for p in scan_browser(name):
            results.append((name, p))
    seen = set()
    deduped = []
    for b, p in results:
        if p not in seen:
            seen.add(p)
            deduped.append((b, p))
    return sorted(deduped)

# ─── Core codec ───────────────────────────────────────────────────────────────

def decode_mozlz4(path: str) -> str:
    with open(path, "rb") as f:
        magic = f.read(8)
        if magic != MAGIC:
            raise ValueError(f"Not a mozLz4 file (bad magic: {magic!r})")
        uncompressed_size = struct.unpack("<I", f.read(4))[0]
        compressed = f.read()
    return lz4.block.decompress(compressed, uncompressed_size=uncompressed_size).decode("utf-8")

def encode_mozlz4(json_text: str) -> bytes:
    raw = json_text.encode("utf-8")
    compressed = lz4.block.compress(raw, store_size=False)
    return MAGIC + struct.pack("<I", len(raw)) + compressed

def verify_roundtrip(encoded: bytes, expected: str) -> bool:
    import io
    buf = io.BytesIO(encoded)
    assert buf.read(8) == MAGIC
    sz = struct.unpack("<I", buf.read(4))[0]
    return lz4.block.decompress(buf.read(), uncompressed_size=sz).decode("utf-8") == expected

# ─── Replace logic ────────────────────────────────────────────────────────────

def replace_in_text(text: str, old: str, new: str,
                    match_scheme: bool, match_subdomains: bool,
                    dry_run: bool = False):
    flags = re.IGNORECASE
    scheme_pat = r"(https?://)" if match_scheme else r"(https?://)?"
    if match_subdomains:
        full_pat = re.compile(scheme_pat + r"((?:[a-zA-Z0-9\-]+\.)*)" + re.escape(old), flags)
        def repl(m): return (m.group(1) or "") + (m.group(2) or "") + new
    else:
        full_pat = re.compile(scheme_pat + re.escape(old), flags)
        def repl(m): return (m.group(1) or "") + new

    matches, count = [], 0
    def replacer(m):
        nonlocal count; count += 1; matches.append(m.group(0)); return repl(m)

    new_text = full_pat.sub(replacer, text)
    if dry_run:
        return text, count, matches
    return new_text, count, matches

# ─── URL prefix normalizer ───────────────────────────────────────────────────

def normalize_url_prefix(value: str) -> str:
    """
    When 'Require http(s)://' is enabled, ensure the value starts with https://.
    Handles: partial prefixes like 'ps://', 'ttps://', '://', '/', 's://' etc.
    If already valid http:// or https:// → leave untouched.
    If no scheme present → prepend https://.
    """
    v = value.strip()
    if not v:
        return v
    # Already correct
    if re.match(r'^https?://', v, re.IGNORECASE):
        return v
    # Remove any broken/partial scheme prefix: optional chars + "://"
    # e.g. "ps://", "ttps://", "s://", "ttp://", "://"
    cleaned = re.sub(r'^[a-zA-Z]{0,8}:/+', '', v)
    # Remove leading slashes
    cleaned = cleaned.lstrip('/')
    return 'https://' + cleaned

# ─── Backup ───────────────────────────────────────────────────────────────────

def _backup_name(base_dir: str, ext: str) -> str:
    date_str = datetime.datetime.now().strftime("%d.%m.%Y")
    n = 1
    while True:
        path = os.path.join(base_dir, f"sessionstore-backups_{date_str}_{n}{ext}")
        if not os.path.exists(path): return path
        n += 1

def _find_rar() -> Optional[str]:
    for cmd in ["rar", "rar.exe"]:
        r = shutil.which(cmd)
        if r: return r
    if sys.platform == "win32":
        for c in [r"C:\Program Files\WinRAR\Rar.exe", r"C:\Program Files (x86)\WinRAR\Rar.exe"]:
            if os.path.isfile(c): return c
    return None

def create_backup(source_file: str, fmt: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(source_file))
    if fmt == "rar":
        rar = _find_rar()
        if rar:
            path = _backup_name(base_dir, ".rar")
            r = subprocess.run([rar, "a", "-ep", path, source_file], capture_output=True, text=True)
            if r.returncode == 0: return path
            raise RuntimeError(f"WinRAR error:\n{r.stderr}")
        path = _backup_name(base_dir, ".zip")
    else:
        path = _backup_name(base_dir, ".zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(source_file, arcname=os.path.basename(source_file))
    note = " [ZIP fallback]" if fmt == "rar" else ""
    return path + note

def open_folder(path: str):
    p = Path(path)
    folder = p.parent if p.is_file() else p
    if not folder.exists(): return
    try:
        if sys.platform == "win32": os.startfile(str(folder))
        elif sys.platform == "darwin": subprocess.Popen(["open", str(folder)])
        else: subprocess.Popen(["xdg-open", str(folder)])
    except Exception: pass

# ─── DPI / high-DPI awareness ────────────────────────────────────────────────
try:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor v2
except Exception:
    pass
try:
    # Tk 8.6+ scaling hint
    import tkinter as _tk_dpi
    _r = _tk_dpi.Tk()
    _r.tk.call("tk", "scaling", _r.winfo_fpixels("1i") / 72)
    _r.destroy()
    del _tk_dpi, _r
except Exception:
    pass

# ─── GUI ──────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Foxy Session Editor")
        self.minsize(760, 680)

        self._cfg = load_config()
        self._json_text = ""
        self._source_path = ""
        self._history: List[str] = []
        self._last_output_path = ""
        self._histories: Dict[str, List[dict]] = self._cfg.get("histories", {})

        # browser check states: {name: BooleanVar}
        self._browser_vars: Dict[str, tk.BooleanVar] = {}
        # detected: {name: [paths]} — populated by refresh
        self._detected: Dict[str, List[str]] = {}

        self._current_theme = self._cfg.get("theme", "🌸 Sakura")
        if self._current_theme not in THEMES:
            self._current_theme = "🌸 Sakura"
        self._font_profile = self._cfg.get("font_profile", "Mono")
        self._scaling = float(self._cfg.get("scaling", 1.0))

        self.style = ttk.Style(self)
        try: self.style.theme_use("clam")
        except: pass

        self._build_scrollable_main()
        self._build_ui()
        self._apply_theme(self._current_theme)
        self._apply_font(self._font_profile, self._scaling)

        geom = self._cfg.get("geometry", "860x760+80+40")
        try: self.geometry(geom)
        except: pass

        # restore enabled browser selections
        enabled_saved = set(self._cfg.get("enabled_browsers", []))
        for name, var in self._browser_vars.items():
            var.set(name in enabled_saved if enabled_saved else True)

        # run initial detect in background-ish way (after mainloop starts)
        self.after(200, self._refresh_browsers)
        self._update_buttons()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Icon ──────────────────────────────────────────────────────────────
        _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        for ico_name in ("icon.ico", "icon.png"):
            ico_path = os.path.join(_base, ico_name)
            if os.path.isfile(ico_path):
                try:
                    if ico_name.endswith(".ico"):
                        self.iconbitmap(ico_path)
                    else:
                        img = tk.PhotoImage(file=ico_path)
                        self.iconphoto(True, img)
                    break
                except Exception:
                    pass

        # ── Ctrl+Scroll → scale ───────────────────────────────────────────────
        self.bind_all("<Control-MouseWheel>", self._ctrl_scroll)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _remember(self, key: str, value: str):
        value = value.strip()
        if not value: return
        hist = self._histories.get(key, [])
        hist = [e for e in hist if e.get("v") != value]
        hist.insert(0, {"v": value, "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
        self._histories[key] = hist[:HISTORY_MAX]

    def _hist_values(self, key: str) -> List[str]:
        return [e["v"] for e in self._histories.get(key, [])]

    def _update_combo(self, key: str, combo: ttk.Combobox):
        combo["values"] = self._hist_values(key)

    def _flush_config(self):
        self._cfg["histories"] = self._histories
        self._cfg["theme"] = self._current_theme
        self._cfg["font_profile"] = self._font_profile
        self._cfg["scaling"] = self._scaling
        self._cfg["backup_fmt"] = self.var_bak_fmt.get()
        self._cfg["backup_enabled"] = self.var_backup.get()
        self._cfg["validate"] = self.var_validate.get()
        self._cfg["verify"] = self.var_verify.get()
        self._cfg["match_scheme"] = self.var_match_scheme.get()
        self._cfg["match_subdomains"] = self.var_subdomains.get()
        self._cfg["geometry"] = self.winfo_geometry()
        self._cfg["enabled_browsers"] = [n for n, v in self._browser_vars.items() if v.get()]
        save_config(self._cfg)

    def _ctrl_scroll(self, event):
        """Ctrl+ScrollUp → increase scale, Ctrl+ScrollDown → decrease scale."""
        current = self.var_scale.get().strip().rstrip("%")
        try:
            val = int(current)
        except ValueError:
            return
        delta = 5 if event.delta > 0 else -5   # Windows gives +/-120
        new_val = max(60, min(180, val + delta))
        new_label = f"{new_val}%"
        if new_label in SCALING_LABELS:
            self.var_scale.set(new_label)
            self._apply_font(self._font_profile, new_val / 100)

    def _on_close(self):
        self._flush_config()
        self.destroy()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self, theme_key: str):
        if theme_key not in THEMES: theme_key = next(iter(THEMES))
        self._current_theme = theme_key
        t = THEMES[theme_key]
        bg, fg, ac, en, lb = t["bg"], t["fg"], t["accent"], t["entry"], t["log_bg"]
        self.configure(bg=bg)
        self.style.configure("TFrame",             background=bg)
        self.style.configure("TLabel",             background=bg, foreground=fg)
        self.style.configure("TCheckbutton",       background=bg, foreground=fg)
        self.style.configure("TRadiobutton",       background=bg, foreground=fg)
        self.style.configure("TButton",            background=bg, foreground=fg, padding=5)
        self.style.map("TButton",    background=[("active", ac)], foreground=[("active", fg)])
        self.style.configure("TLabelframe",        background=bg, foreground=fg)
        self.style.configure("TLabelframe.Label",  background=bg, foreground=ac)
        self.style.configure("TCombobox", fieldbackground=en, background=en, foreground=fg, arrowcolor=fg)
        self.style.map("TCombobox", fieldbackground=[("readonly", en)], foreground=[("readonly", fg)])
        self.style.configure("Accent.TButton", background=ac, foreground=bg, padding=6)
        self.style.map("Accent.TButton", background=[("active", fg)], foreground=[("active", bg)])
        self.style.configure("Status.TLabel", background=bg, foreground=ac,
                               font=("Consolas", 9), relief="sunken", padding=(6,3))
        # browser panel
        self.style.configure("Toggle.TButton",  background=bg, foreground=ac, padding=(4,2), relief="flat")
        self.style.map("Toggle.TButton", background=[("active", en)], foreground=[("active", ac)])
        self.style.configure("Browser.TCheckbutton", background=bg, foreground=fg)
        self.style.map("Browser.TCheckbutton",
            background=[("active", bg)],
            foreground=[("active", ac)])
        self.style.configure("BrowserFound.TCheckbutton", background=bg, foreground=ac)
        self.style.map("BrowserFound.TCheckbutton",
            background=[("active", bg)],
            foreground=[("active", ac)])

        if hasattr(self, "_main_canvas"):
            self._main_canvas.configure(bg=bg)
        if hasattr(self, "_scroll_frame"):
            self._scroll_frame.configure(style="TFrame")
        if hasattr(self, "_browser_inner"):
            self._browser_inner.configure(bg=bg)
            for w in self._browser_inner.winfo_children():
                try: w.configure(background=bg)
                except: pass
        if hasattr(self, "_frm_b_body"):
            self._frm_b_body.configure(style="TFrame")
        if hasattr(self, "log"):
            self.log.config(background=lb, foreground=fg)
        if hasattr(self, "var_theme"):
            self.var_theme.set(theme_key)

    # ── Font ──────────────────────────────────────────────────────────────────

    def _apply_font(self, profile: str, scale: float):
        self._font_profile = profile
        self._scaling = scale
        families = {
            "Mono":["Cascadia Mono","JetBrains Mono","Consolas","Courier New"],
            "Mono Large":["Cascadia Mono","Consolas","Courier New"],
            "Mono Small":["Cascadia Mono","Consolas","Courier New"],
            "Coding":["JetBrains Mono","Fira Code","Cascadia Code","Consolas"],
            "Large":["Segoe UI","Arial","Helvetica"],
            "Tiny":["Segoe UI","Arial","Helvetica"],
            "Serif":["Georgia","Times New Roman"],
            "Rounded":["Calibri","Verdana","Segoe UI"],
            "Default":["Segoe UI","Arial","Helvetica"],
        }
        extra = {"Mono Large":1.2,"Mono Small":0.85,"Large":1.3,"Tiny":0.8}
        size = max(6, int(9 * scale * extra.get(profile, 1.0)))
        try:
            df = tkfont.nametofont("TkDefaultFont")
            for fam in families.get(profile, families["Default"]):
                try: df.configure(family=fam, size=size); break
                except tk.TclError: continue
            self.option_add("*Font", df)
        except Exception: pass
        self._current_font_size = size
        # Scale ttk checkbox/radiobutton indicator to match font size
        ind_size = max(10, int(size * 1.4))
        self.style.configure("TCheckbutton",           indicatorsize=ind_size)
        self.style.configure("TRadiobutton",           indicatorsize=ind_size)
        self.style.configure("Browser.TCheckbutton",   indicatorsize=ind_size)
        self.style.configure("BrowserFound.TCheckbutton", indicatorsize=ind_size)
        # Rebuild checkboxes so they pick up new font size
        if hasattr(self, "_browser_inner"):
            self._refresh_browsers()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_scrollable_main(self):
        """Wraps the window in a vertical scrollbar so content can scroll if window is small."""
        self._main_canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self._vscroll = ttk.Scrollbar(self, orient="vertical", command=self._main_canvas.yview)
        self._main_canvas.configure(yscrollcommand=self._vscroll.set)
        self._vscroll.pack(side="right", fill="y")
        self._main_canvas.pack(side="left", fill="both", expand=True)
        self._scroll_frame = ttk.Frame(self._main_canvas)
        self._scroll_win = self._main_canvas.create_window((0,0), window=self._scroll_frame, anchor="nw")
        self._scroll_frame.bind("<Configure>", self._on_scroll_frame_configure)
        self._main_canvas.bind("<Configure>", self._on_canvas_configure)
        # MouseWheel on canvas and frame
        for w in (self._main_canvas, self._scroll_frame):
            w.bind("<MouseWheel>", self._on_mousewheel)
            w.bind("<Button-4>",   lambda e: self._main_canvas.yview_scroll(-1,"units"))
            w.bind("<Button-5>",   lambda e: self._main_canvas.yview_scroll(1,"units"))
        # propagate to children lazily
        self.bind_all("<MouseWheel>", self._on_mousewheel_all)

    def _on_scroll_frame_configure(self, event):
        self._main_canvas.configure(scrollregion=self._main_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._main_canvas.itemconfig(self._scroll_win, width=event.width)

    def _on_mousewheel(self, event):
        self._main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_mousewheel_all(self, event):
        widget = event.widget
        # only scroll main canvas if focus is NOT on log or an Entry/Combobox
        if isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
            return   # let the log scroll itself
        if isinstance(widget, (ttk.Combobox, tk.Entry, ttk.Entry)):
            return
        self._main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _build_ui(self):
        self._scroll_frame.columnconfigure(0, weight=1)
        self._scroll_frame.rowconfigure(6, weight=1)
        p  = dict(padx=10, pady=3)   # top bar / small widgets
        ps = dict(padx=10, pady=7)   # section frames (more breathing)

        # ── Top bar ───────────────────────────────────────────────────────────
        top = ttk.Frame(self._scroll_frame)
        top.grid(row=0, column=0, sticky="ew", **p)

        ttk.Label(top, text="🎨 Theme:").pack(side="left")
        self.var_theme = tk.StringVar(value=self._current_theme)
        _cb_theme = ttk.Combobox(top, textvariable=self.var_theme, values=THEME_CODES,
                      width=18, state="readonly")
        _cb_theme.pack(side="left", padx=(2,10))
        self._bind_no_scroll(_cb_theme)
        self.var_theme.trace_add("write", lambda *_: self._apply_theme(self.var_theme.get()))

        ttk.Label(top, text="🔤 Font:").pack(side="left")
        self.var_font = tk.StringVar(value=self._font_profile)
        _cb_font = ttk.Combobox(top, textvariable=self.var_font, values=FONT_PROFILES,
                      width=10, state="readonly")
        _cb_font.pack(side="left", padx=(2,10))
        self._bind_no_scroll(_cb_font)
        self.var_font.trace_add("write", lambda *_: self._apply_font(self.var_font.get(), self._scaling))

        ttk.Label(top, text="🔍 Scale:").pack(side="left")
        self.var_scale = tk.StringVar(value=f"{int(self._scaling*100)}%")
        _cb_scale = ttk.Combobox(top, textvariable=self.var_scale, values=SCALING_LABELS,
                      width=6, state="readonly")
        _cb_scale.pack(side="left", padx=(2,0))
        self._bind_no_scroll(_cb_scale)
        self.var_scale.trace_add("write", lambda *_: self._on_scale_change())

        # ── Browser Filter panel (collapsible) ───────────────────────────────
        self._browsers_expanded = tk.BooleanVar(value=True)

        frm_b_outer = ttk.Frame(self._scroll_frame)
        frm_b_outer.grid(row=1, column=0, sticky="ew", padx=10, pady=(6,3))
        frm_b_outer.columnconfigure(0, weight=1)

        # header row with toggle
        hdr = ttk.Frame(frm_b_outer)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        self._btn_toggle_browsers = ttk.Button(
            hdr, text="▼ Browsers  (✔ = include in Auto-Find)",
            command=self._toggle_browsers_panel, style="Toggle.TButton")
        self._btn_toggle_browsers.grid(row=0, column=0, sticky="w")

        # control row (always visible)
        ctrl = ttk.Frame(frm_b_outer)
        ctrl.grid(row=1, column=0, sticky="w", pady=(2,0))
        ttk.Button(ctrl, text="🔄 Refresh / Detect",
                    command=self._refresh_browsers).pack(side="left", padx=(0,6))
        ttk.Button(ctrl, text="✅ All",
                    command=lambda: self._set_all_browsers(True)).pack(side="left", padx=(0,4))
        ttk.Button(ctrl, text="☐ None",
                    command=lambda: self._set_all_browsers(False)).pack(side="left")
        self.lbl_detected = ttk.Label(ctrl, text="")
        self.lbl_detected.pack(side="left", padx=(10,0))

        # collapsible body
        self._frm_b_body = ttk.Frame(frm_b_outer)
        self._frm_b_body.grid(row=2, column=0, sticky="ew")
        self._frm_b_body.columnconfigure(0, weight=1)
        self._browser_inner = tk.Frame(self._frm_b_body, bd=0, highlightthickness=0)
        self._browser_inner.grid(row=0, column=0, sticky="ew", pady=(3,0))

        # add Toggle style (flat look)
        self.style.configure("Toggle.TButton", padding=(4,2), relief="flat")

        # create one checkbox per browser
        self._build_browser_checkboxes()

        # ── Step 1: File ──────────────────────────────────────────────────────
        frm1 = ttk.LabelFrame(self._scroll_frame, text="Step 1 · Open Session File", padding=7)
        frm1.grid(row=2, column=0, sticky="ew", **ps)
        frm1.columnconfigure(1, weight=1)

        ttk.Label(frm1, text="File:").grid(row=0, column=0, sticky="w")
        self.var_path = tk.StringVar()
        self.cb_path = ttk.Combobox(frm1, textvariable=self.var_path,
                                     values=self._hist_values("path"))
        self.cb_path.grid(row=0, column=1, sticky="ew", padx=5)
        self._bind_no_scroll(self.cb_path)

        btn_row = ttk.Frame(frm1)
        btn_row.grid(row=0, column=2)
        ttk.Button(btn_row, text="🔎 Auto-Find", command=self._auto_find).pack(side="left", padx=(0,3))
        ttk.Button(btn_row, text="Browse…",      command=self._browse).pack(side="left", padx=(0,3))
        ttk.Button(btn_row, text="Decode →",     command=self._decode).pack(side="left")

        # ── Step 2: Replace ───────────────────────────────────────────────────
        frm2 = ttk.LabelFrame(self._scroll_frame, text="Step 2 · Replace Domain in URLs", padding=7)
        frm2.grid(row=3, column=0, sticky="ew", **ps)
        frm2.columnconfigure(1, weight=1)
        frm2.columnconfigure(3, weight=1)

        ttk.Label(frm2, text="Old domain:").grid(row=0, column=0, sticky="w")
        self.var_old = tk.StringVar()
        self.cb_old = ttk.Combobox(frm2, textvariable=self.var_old,
                                    values=self._hist_values("old_domain"))
        self.cb_old.grid(row=0, column=1, sticky="ew", padx=5)
        self._bind_no_scroll(self.cb_old)

        ttk.Label(frm2, text="New domain:").grid(row=0, column=2, sticky="w", padx=(10,0))
        self.var_new = tk.StringVar()
        self.cb_new = ttk.Combobox(frm2, textvariable=self.var_new,
                                    values=self._hist_values("new_domain"))
        self.cb_new.grid(row=0, column=3, sticky="ew", padx=5)
        self._bind_no_scroll(self.cb_new)
        self.cb_new.bind("<FocusOut>", self._on_new_domain_focusout)
        self.cb_old.bind("<FocusOut>", self._on_old_domain_focusout)

        opt = ttk.Frame(frm2)
        opt.grid(row=1, column=0, columnspan=4, sticky="w", pady=(5,0))
        self.var_match_scheme = tk.BooleanVar(value=self._cfg.get("match_scheme", False))
        ttk.Checkbutton(opt, text="Require http(s):// prefix",
                         variable=self.var_match_scheme).pack(side="left", padx=(0,12))
        self.var_subdomains = tk.BooleanVar(value=self._cfg.get("match_subdomains", False))
        ttk.Checkbutton(opt, text="Include subdomains (sub.old→sub.new)",
                         variable=self.var_subdomains).pack(side="left", padx=(0,12))

        act = ttk.Frame(frm2)
        act.grid(row=2, column=0, columnspan=4, sticky="w", pady=(7,0))
        self.btn_dryrun  = ttk.Button(act, text="🔍 Dry Run",       command=self._dry_run,       state="disabled")
        self.btn_replace = ttk.Button(act, text="✏️ Apply Replace", command=self._apply_replace,  state="disabled")
        self.btn_undo    = ttk.Button(act, text="↩ Undo",           command=self._undo,           state="disabled")
        self.btn_dryrun.pack(side="left", padx=(0,6))
        self.btn_replace.pack(side="left", padx=(0,6))
        self.btn_undo.pack(side="left")

        # ── Step 3: Save ──────────────────────────────────────────────────────
        frm3 = ttk.LabelFrame(self._scroll_frame, text="Step 3 · Save", padding=7)
        frm3.grid(row=4, column=0, sticky="ew", **ps)
        frm3.columnconfigure(1, weight=1)

        bak_row = ttk.Frame(frm3)
        bak_row.grid(row=0, column=0, columnspan=3, sticky="w")
        self.var_backup = tk.BooleanVar(value=self._cfg.get("backup_enabled", True))
        ttk.Checkbutton(bak_row, text="Backup archive before saving:",
                         variable=self.var_backup).pack(side="left")
        self.var_bak_fmt = tk.StringVar(value=self._cfg.get("backup_fmt", "rar"))
        ttk.Radiobutton(bak_row, text=".rar (WinRAR, fallback→.zip)",
                         variable=self.var_bak_fmt, value="rar").pack(side="left", padx=(8,4))
        ttk.Radiobutton(bak_row, text=".zip (built-in)",
                         variable=self.var_bak_fmt, value="zip").pack(side="left")

        self.var_validate = tk.BooleanVar(value=self._cfg.get("validate", True))
        ttk.Checkbutton(frm3, text="Validate JSON before saving",
                         variable=self.var_validate).grid(row=1, column=0, columnspan=3,
                                                           sticky="w", pady=(3,0))
        self.var_verify = tk.BooleanVar(value=self._cfg.get("verify", True))
        ttk.Checkbutton(frm3, text="Verify round-trip decode after encoding",
                         variable=self.var_verify).grid(row=2, column=0, columnspan=3,
                                                         sticky="w", pady=(2,3))
        ttk.Label(frm3, text="Output:").grid(row=3, column=0, sticky="w")
        self.var_out = tk.StringVar()
        self.cb_out = ttk.Combobox(frm3, textvariable=self.var_out,
                                    values=self._hist_values("outpath"))
        self.cb_out.grid(row=3, column=1, sticky="ew", padx=5)
        self._bind_no_scroll(self.cb_out)
        ttk.Button(frm3, text="Browse…", command=self._browse_out).grid(row=3, column=2)

        save_row = ttk.Frame(frm3)
        save_row.grid(row=4, column=0, columnspan=3, sticky="w", pady=(7,0))
        self.btn_save      = ttk.Button(save_row, text="💾 Save .jsonlz4",  command=self._save,      state="disabled", style="Accent.TButton")
        self.btn_save_json = ttk.Button(save_row, text="📄 Export JSON",    command=self._save_json, state="disabled")
        self.btn_save.pack(side="left", padx=(0,8))
        self.btn_save_json.pack(side="left")

        # ── Log ───────────────────────────────────────────────────────────────
        frm4 = ttk.LabelFrame(self._scroll_frame, text="Log & Preview", padding=7)
        frm4.grid(row=6, column=0, sticky="nsew", **ps)
        frm4.rowconfigure(0, weight=1)
        frm4.columnconfigure(0, weight=1)
        self._scroll_frame.rowconfigure(6, weight=1)

        self.log = scrolledtext.ScrolledText(
            frm4, height=10, wrap="word", font=("Consolas", 9),
            state="disabled", background="#0A0012", foreground="#E9D8FD",
            insertbackground="white"
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        self.log.tag_config("info",   foreground="#9cdcfe")
        self.log.tag_config("ok",     foreground="#4ec9b0")
        self.log.tag_config("warn",   foreground="#dcdcaa")
        self.log.tag_config("error",  foreground="#f44747")
        self.log.tag_config("match",  foreground="#ce9178")
        self.log.tag_config("header", foreground="#c586c0")

        self.var_status = tk.StringVar(value="Ready")
        ttk.Label(self._scroll_frame, textvariable=self.var_status, style="Status.TLabel") \
            .grid(row=7, column=0, sticky="ew")

    # ── Browser panel helpers ─────────────────────────────────────────────────

    def _build_browser_checkboxes(self):
        """Build one checkbox per browser in BROWSERS."""
        for w in self._browser_inner.winfo_children():
            w.destroy()
        self._browser_vars.clear()
        col = row = 0
        per_row = 4
        for name in BROWSERS:
            var = tk.BooleanVar(value=True)
            self._browser_vars[name] = var
            _t = THEMES.get(self._current_theme, {})
            _sz = getattr(self, "_current_font_size", 9)
            cb = ttk.Checkbutton(
                self._browser_inner, text=name, variable=var,
                style="Browser.TCheckbutton",
            )
            cb.grid(row=row, column=col, sticky="w")
            col += 1
            if col >= per_row:
                col = 0; row += 1

    def _refresh_browsers(self):
        """Scan which browsers actually have session files; update checkbox labels."""
        self._status("Detecting installed browsers…")
        self.update_idletasks()
        self._detected = detect_installed_browsers()

        t = THEMES.get(self._current_theme, {})
        bg   = t.get("bg",     "#14001F")
        fg   = t.get("fg",     "#E9D8FD")
        ac   = t.get("accent", "#9F7AEA")
        en   = t.get("entry",  "#1F102A")
        warn = "#dcdcaa"

        # Update checkbox labels to show session count & enable/disable
        col = row = 0
        per_row = 4
        for widget in self._browser_inner.winfo_children():
            widget.destroy()

        for name in BROWSERS:
            var = self._browser_vars.get(name)
            if var is None:
                var = tk.BooleanVar(value=True)
                self._browser_vars[name] = var

            files = self._detected.get(name, [])
            count = len(files)
            label = f"{'✅' if count else '○'} {name}"
            if count:
                label += f" ({count})"

            fgc = ac if count else fg
            # Use a per-entry style so detected browsers appear in accent color
            entry_style = "BrowserFound.TCheckbutton" if count else "Browser.TCheckbutton"
            if count:
                self.style.configure("BrowserFound.TCheckbutton", foreground=fgc)
                self.style.map("BrowserFound.TCheckbutton",
                    foreground=[("active", ac)],
                    background=[("active", bg)])
            cb = ttk.Checkbutton(
                self._browser_inner, text=label, variable=var,
                style=entry_style,
            )
            cb.grid(row=row, column=col, sticky="w")
            col += 1
            if col >= per_row:
                col = 0; row += 1

        installed_count = len(self._detected)
        total_files = sum(len(v) for v in self._detected.values())
        msg = f"Found {installed_count} browser(s) with {total_files} session file(s)"
        self.lbl_detected.config(text=msg)
        self._log(f"🔄 Refresh: {msg}", "ok")
        self._status(f"Detect complete — {msg}")

    def _toggle_browsers_panel(self):
        expanded = self._browsers_expanded.get()
        if expanded:
            self._frm_b_body.grid_remove()
            self._btn_toggle_browsers.config(text="▶ Browsers  (✔ = include in Auto-Find)")
            self._browsers_expanded.set(False)
        else:
            self._frm_b_body.grid()
            self._btn_toggle_browsers.config(text="▼ Browsers  (✔ = include in Auto-Find)")
            self._browsers_expanded.set(True)

    def _set_all_browsers(self, state: bool):
        for var in self._browser_vars.values():
            var.set(state)

    def _get_enabled_browsers(self) -> Optional[Set[str]]:
        enabled = {n for n, v in self._browser_vars.items() if v.get()}
        return enabled if enabled else None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg, tag="info"):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def _sep(self):
        self._log("─" * 64, "header")

    def _status(self, msg):
        self.var_status.set(msg)
        self.update_idletasks()

    def _update_buttons(self):
        has = bool(self._json_text)
        self.btn_dryrun.config(state="normal"  if has else "disabled")
        self.btn_replace.config(state="normal" if has else "disabled")
        self.btn_save.config(state="normal"    if has else "disabled")
        self.btn_save_json.config(state="normal" if has else "disabled")
        self.btn_undo.config(state="normal"    if self._history else "disabled")

    def _no_scroll(self, event):
        """Absorb MouseWheel on comboboxes — prevents accidental list scrolling."""
        return "break"

    def _bind_no_scroll(self, widget):
        """Block MouseWheel scroll on a Combobox widget."""
        widget.bind("<MouseWheel>", self._no_scroll)
        widget.bind("<Button-4>",   self._no_scroll)
        widget.bind("<Button-5>",   self._no_scroll)

    def _on_scale_change(self):
        s = self.var_scale.get().strip().rstrip("%")
        try: self._apply_font(self._font_profile, int(s)/100)
        except ValueError: pass

    # ── Auto-Find ─────────────────────────────────────────────────────────────

    def _auto_find(self):
        enabled = self._get_enabled_browsers()
        self._sep()
        names = ", ".join(sorted(enabled)) if enabled else "all"
        self._log(f"Searching session files in: {names}…", "info")
        self._status("Scanning…")
        self.update_idletasks()

        results = find_session_files(enabled)

        if not results:
            self._log("✘ No session files found. Make sure the browser is closed.", "warn")
            self._status("Not found")
            messagebox.showwarning("Not found",
                "No session file found for the selected browsers.\n\n"
                "Make sure the browser is completely closed,\nor select more browsers and retry.")
            return

        if len(results) == 1:
            b, path = results[0]
            self._set_path(path)
            self._log(f"✔ [{b}] {path}", "ok")
            self._status(f"Found: {path}")
            return

        # picker dialog
        self._log(f"Found {len(results)} session file(s):", "ok")
        for b, path in results:
            self._log(f"  [{b}]  {path}", "match")

        win = tk.Toplevel(self)
        win.title("Choose Session File")
        win.grab_set()
        win.resizable(True, False)
        t = THEMES.get(self._current_theme, {})
        win.configure(bg=t.get("bg","#14001F"))
        ttk.Label(win, text="Multiple session files found. Select one to open:",
                   padding=10).pack()
        lb_fr = ttk.Frame(win)
        lb_fr.pack(fill="both", expand=True, padx=10)
        sb = ttk.Scrollbar(lb_fr); sb.pack(side="right", fill="y")
        lb = tk.Listbox(lb_fr, yscrollcommand=sb.set, font=("Consolas", 9),
                         height=min(len(results), 12),
                         bg=t.get("entry","#1F102A"), fg=t.get("fg","#E9D8FD"))
        lb.pack(fill="both", expand=True)
        sb.config(command=lb.yview)
        for b, path in results:
            lb.insert("end", f"[{b}]  {path}")
        lb.selection_set(0)

        def pick():
            sel = lb.curselection()
            if sel:
                self._set_path(results[sel[0]][1])
                self._log(f"✔ Selected: {results[sel[0]][1]}", "ok")
            win.destroy()

        ttk.Button(win, text="Open selected", command=pick,
                    style="Accent.TButton", padding=6).pack(pady=8)
        win.wait_window()

    def _set_path(self, path: str):
        self.var_path.set(path)
        self.var_out.set(path)
        self._update_combo("path", self.cb_path)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Open session file",
            filetypes=[("Session files","*.jsonlz4 *.mozlz4"),("All files","*.*")])
        if path: self._set_path(path)

    def _browse_out(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".jsonlz4",
            filetypes=[("Session","*.jsonlz4"),("All files","*.*")])
        if path: self.var_out.set(path)

    # ── Decode ────────────────────────────────────────────────────────────────

    def _decode(self):
        path = self.var_path.get().strip()
        if not path: messagebox.showwarning("No file","Select a file first."); return
        if not os.path.isfile(path): messagebox.showerror("Not found",f"Not found:\n{path}"); return
        try:
            self._status("Decoding…")
            self._json_text = decode_mozlz4(path)
            self._source_path = path
            self._history.clear()
            self._remember("path", path)
            self._update_combo("path", self.cb_path)
            size_kb = len(self._json_text) / 1024
            self._sep()
            self._log(f"✔ Decoded: {path}", "ok")
            self._log(f"  JSON: {size_kb:.1f} KB  |  ~tabs: {self._json_text.count(chr(34)+'entries'+chr(34))}", "info")
            self._status(f"Decoded — {size_kb:.1f} KB")
            self._update_buttons()
        except Exception as e:
            self._log(f"✘ {e}", "error"); self._status("Decode failed")
            messagebox.showerror("Decode error", str(e))

    # ── Replace ───────────────────────────────────────────────────────────────

    def _validate_replace_fields(self):
        old, new = self.var_old.get().strip(), self.var_new.get().strip()
        if not old: messagebox.showwarning("Missing","Enter old domain."); return None,None
        if not new: messagebox.showwarning("Missing","Enter new domain."); return None,None
        if old==new: messagebox.showwarning("Same","Domains are identical."); return None,None
        return old, new

    def _do_replace(self, dry_run: bool):
        old, new = self._validate_replace_fields()
        if old is None or not self._json_text: return
        # Auto-complete https:// prefix on new domain when scheme mode is on
        if self.var_match_scheme.get():
            fixed = normalize_url_prefix(new)
            if fixed != new:
                self.var_new.set(fixed)
                new = fixed
                self._log(f"  ℹ Auto-completed new domain prefix → {fixed}", "info")
        new_text, count, matches = replace_in_text(
            self._json_text, old, new,
            match_scheme=self.var_match_scheme.get(),
            match_subdomains=self.var_subdomains.get(),
            dry_run=dry_run)
        self._sep()
        self._log(f"[{'DRY RUN' if dry_run else 'APPLIED'}] '{old}' → '{new}'","header")
        self._log(f"  Matches: {count}", "ok" if count else "warn")
        if count:
            for m in matches[:10]: self._log(f"    {m}", "match")
            if len(matches)>10: self._log(f"    … and {len(matches)-10} more","info")
        if not dry_run and count:
            self._history.append(self._json_text)
            if len(self._history)>20: self._history.pop(0)
            self._json_text = new_text
            self._remember("old_domain",old); self._remember("new_domain",new)
            self._update_combo("old_domain",self.cb_old); self._update_combo("new_domain",self.cb_new)
            self._log("✔ Applied. Undo available.","ok")
            self._status(f"Replaced {count} occurrence(s).")
        elif dry_run: self._status(f"Dry run: {count} match(es) — no changes.")
        else: self._status("No matches — nothing changed.")
        self._update_buttons()

    def _on_new_domain_focusout(self, event=None):
        """Live-normalize the new domain field when Require prefix is ON."""
        if not self.var_match_scheme.get():
            return
        val = self.var_new.get()
        fixed = normalize_url_prefix(val)
        if fixed != val:
            self.var_new.set(fixed)

    def _on_old_domain_focusout(self, event=None):
        """Live-normalize the old domain field when Require prefix is ON."""
        if not self.var_match_scheme.get():
            return
        val = self.var_old.get()
        fixed = normalize_url_prefix(val)
        if fixed != val:
            self.var_old.set(fixed)

    def _dry_run(self):      self._do_replace(dry_run=True)
    def _apply_replace(self): self._do_replace(dry_run=False)

    def _undo(self):
        if not self._history: messagebox.showinfo("Nothing to undo","No history."); return
        self._json_text = self._history.pop()
        self._log("↩ Undo — reverted.","warn"); self._status("Undo applied.")
        self._update_buttons()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._json_text: messagebox.showwarning("No data","Nothing to save."); return
        out_path = self.var_out.get().strip()
        if not out_path:
            out_path = filedialog.asksaveasfilename(
                defaultextension=".jsonlz4", filetypes=[("Session","*.jsonlz4")])
            if not out_path: return
            self.var_out.set(out_path)
        if self.var_validate.get():
            try: json.loads(self._json_text); self._log("✔ JSON valid.","ok")
            except json.JSONDecodeError as e:
                self._log(f"✘ JSON invalid: {e}","error")
                if not messagebox.askyesno("Invalid JSON",f"Invalid JSON:\n{e}\n\nSave anyway?"): return
        if self.var_backup.get() and os.path.isfile(out_path):
            try:
                bak = create_backup(out_path, self.var_bak_fmt.get())
                self._log(f"✔ Backup: {bak}","ok")
            except Exception as e:
                self._log(f"⚠ Backup failed: {e}","warn")
                if not messagebox.askyesno("Backup failed",f"Backup failed:\n{e}\n\nContinue?"): return
        try:
            self._status("Encoding…"); encoded = encode_mozlz4(self._json_text)
        except Exception as e:
            self._log(f"✘ Encode: {e}","error"); messagebox.showerror("Encode error",str(e)); return
        if self.var_verify.get():
            try:
                ok = verify_roundtrip(encoded, self._json_text)
                self._log("✔ Round-trip OK." if ok else "⚠ Round-trip mismatch!","ok" if ok else "warn")
                if not ok and not messagebox.askyesno("Verify warning","Mismatch. Save anyway?"): return
            except Exception as e: self._log(f"⚠ Verify: {e}","warn")
        try:
            with open(out_path,"wb") as f: f.write(encoded)
            size_kb = len(encoded)/1024
            self._last_output_path = out_path
            self._remember("outpath",out_path); self._update_combo("outpath",self.cb_out)
            self._log(f"✔ Saved: {out_path}  ({size_kb:.1f} KB)","ok")
            self._status(f"Saved — {size_kb:.1f} KB")
            self._flush_config()
            self._show_done_dialog(out_path, f"File saved ({size_kb:.1f} KB):\n{out_path}")
        except Exception as e:
            self._log(f"✘ Write: {e}","error"); messagebox.showerror("Write error",str(e))

    def _save_json(self):
        if not self._json_text: messagebox.showwarning("No data","Decode first."); return
        out_path = filedialog.asksaveasfilename(
            title="Export JSON", defaultextension=".json",
            filetypes=[("JSON","*.json"),("All files","*.*")])
        if not out_path: return
        try:
            try: text = json.dumps(json.loads(self._json_text), ensure_ascii=False, indent=2)
            except: text = self._json_text
            with open(out_path,"w",encoding="utf-8") as f: f.write(text)
            self._last_output_path = out_path
            self._log(f"✔ JSON exported: {out_path}","ok"); self._status("JSON exported.")
            self._show_done_dialog(out_path, f"JSON exported:\n{out_path}")
        except Exception as e:
            self._log(f"✘ Export: {e}","error"); messagebox.showerror("Export error",str(e))

    # ── Done dialog ───────────────────────────────────────────────────────────

    def _show_done_dialog(self, file_path: str, message: str):
        win = tk.Toplevel(self)
        win.title("Done"); win.grab_set(); win.resizable(False,False)
        t = THEMES.get(self._current_theme, THEMES[next(iter(THEMES))])
        win.configure(bg=t["bg"])
        ttk.Label(win, text="✅ Done!", font=("Segoe UI",13,"bold"),
                   background=t["bg"], foreground=t["accent"]).pack(pady=(14,4))
        ttk.Label(win, text=message, background=t["bg"], foreground=t["fg"],
                   wraplength=460, justify="center").pack(padx=16, pady=4)
        btn_fr = ttk.Frame(win); btn_fr.pack(pady=12)
        ttk.Button(btn_fr, text="📁 Open Folder",   command=lambda: [open_folder(file_path), win.destroy()],
                    style="Accent.TButton").pack(side="left",padx=6)
        ttk.Button(btn_fr, text="Continue Editing", command=win.destroy).pack(side="left",padx=6)
        ttk.Button(btn_fr, text="❌ Close App",      command=lambda: [win.destroy(), self.destroy()]).pack(side="left",padx=6)
        win.wait_window()


if __name__ == "__main__":
    App().mainloop()
