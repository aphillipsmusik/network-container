"""
LLM Cluster – Windows GUI
Tkinter wizard + system tray icon (pystray).
"""
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pystray
from PIL import Image, ImageDraw

import config as cfg_module
import firewall
import node

log = logging.getLogger(__name__)

APP_NAME = "LLM Cluster"
ACCENT = "#1a73e8"
BG = "#f8f9fa"
CARD = "#ffffff"
FG = "#202124"
FG2 = "#5f6368"


# ── Tray icon image (drawn programmatically) ──────────────────────────────────

def _make_icon_image(size=64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Simple cluster icon: central circle + 3 satellite circles
    cx, cy, r = size // 2, size // 2, size // 5
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    for dx, dy in [(-size // 3, -size // 3), (size // 3, -size // 3), (0, size // 3)]:
        x, y = cx + dx, cy + dy
        sr = size // 8
        d.ellipse([x - sr, y - sr, x + sr, y + sr], fill="#34a853")
        d.line([cx, cy, x, y], fill="#ffffff", width=2)
    return img


# ── Startup registry ──────────────────────────────────────────────────────────

def _set_auto_start(enabled: bool) -> None:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                             winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, sys.executable)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as exc:
        log.warning("Could not set auto-start: %s", exc)


# ── Main Application ──────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.conf = cfg_module.load()
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self._center(600, 480)
        self._apply_theme()

        # Hide window initially – show wizard or go straight to tray
        self.root.withdraw()
        self._tray: pystray.Icon | None = None

    def run(self):
        if not self.conf.install_dir or not Path(self.conf.install_dir).exists():
            self.root.after(0, self._show_wizard)
        else:
            self.root.after(0, self._start_tray)
        self.root.mainloop()

    # ── Wizard ────────────────────────────────────────────────────────────────

    def _show_wizard(self):
        self.root.deiconify()
        self._clear()
        self._page_welcome()

    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _header(self, title: str, subtitle: str = ""):
        bar = tk.Frame(self.root, bg=ACCENT, height=70)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=title, bg=ACCENT, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=20, pady=16)
        if subtitle:
            tk.Label(bar, text=subtitle, bg=ACCENT, fg="#c8deff",
                     font=("Segoe UI", 10)).pack(side="left", padx=4, pady=16)

    def _footer(self, back_cmd=None, next_cmd=None, next_text="Next →",
                next_enabled=True):
        bar = tk.Frame(self.root, bg=BG, pady=12)
        bar.pack(fill="x", side="bottom")
        ttk.Separator(self.root).pack(fill="x", side="bottom")
        if back_cmd:
            ttk.Button(bar, text="← Back", command=back_cmd,
                       width=10).pack(side="left", padx=20)
        if next_cmd:
            btn = ttk.Button(bar, text=next_text, command=next_cmd,
                             width=14, style="Accent.TButton")
            btn.pack(side="right", padx=20)
            if not next_enabled:
                btn.state(["disabled"])

    def _page_welcome(self):
        self._clear()
        self._header(f"Welcome to {APP_NAME}")
        body = tk.Frame(self.root, bg=BG, padx=40, pady=30)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Turn any Windows PC into a cluster node.",
                 bg=BG, fg=FG, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(body, text=(
            "\nPool the RAM and GPU memory of multiple computers on your network\n"
            "to run large AI models that won't fit on a single machine.\n\n"
            "This wizard will:\n"
            "  • Configure your role  (Worker or Orchestrator)\n"
            "  • Open the required firewall ports\n"
            "  • Add a system-tray icon so the node runs in the background\n"
            "  • Auto-start with Windows (optional)"
        ), bg=BG, fg=FG2, font=("Segoe UI", 10), justify="left").pack(anchor="w")

        if not firewall.is_elevated():
            tk.Label(body,
                     text="⚠  Run as Administrator to open firewall ports automatically.",
                     bg=BG, fg="#f29900", font=("Segoe UI", 9)).pack(anchor="w", pady=(16, 0))

        self._footer(next_cmd=self._page_role)

    def _page_role(self):
        self._clear()
        self._header("Choose Your Role", "Step 1 of 3")
        body = tk.Frame(self.root, bg=BG, padx=40, pady=20)
        body.pack(fill="both", expand=True)

        self._role_var = tk.StringVar(value=self.conf.role)

        for role, title, desc in [
            ("worker",
             "Worker Node",
             "Contributes RAM and GPU to the cluster.\n"
             "Runs the RPC server on port 50052.\n"
             "You need at least 8 GB of RAM."),
            ("orchestrator",
             "Orchestrator Node",
             "Manages the cluster and holds the model file.\n"
             "Exposes the OpenAI-compatible API on port 8080.\n"
             "Needs enough disk space for the model (4–40 GB)."),
        ]:
            card = tk.Frame(body, bg=CARD, relief="solid", bd=1, padx=16, pady=12)
            card.pack(fill="x", pady=6)
            tk.Radiobutton(card, text=title, variable=self._role_var, value=role,
                           bg=CARD, fg=FG, font=("Segoe UI", 11, "bold"),
                           activebackground=CARD).pack(anchor="w")
            tk.Label(card, text=desc, bg=CARD, fg=FG2,
                     font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=20)

        self._footer(back_cmd=self._page_welcome, next_cmd=self._page_network)

    def _page_network(self):
        self._clear()
        self.conf.role = self._role_var.get()
        self._header("Network Configuration", "Step 2 of 3")
        body = tk.Frame(self.root, bg=BG, padx=40, pady=16)
        body.pack(fill="both", expand=True)

        fields = {}

        def row(label, var, placeholder="", browse=False):
            f = tk.Frame(body, bg=BG)
            f.pack(fill="x", pady=4)
            tk.Label(f, text=label, bg=BG, fg=FG,
                     font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
            e = ttk.Entry(f, textvariable=var, width=34)
            e.pack(side="left", padx=(0, 4))
            if not var.get() and placeholder:
                var.set(placeholder)
            if browse:
                ttk.Button(f, text="Browse…", width=8,
                           command=lambda: _browse(var)).pack(side="left")
            fields[label] = var

        def _browse(var):
            path = filedialog.askopenfilename(
                title="Select GGUF model file",
                filetypes=[("GGUF model", "*.gguf"), ("All files", "*.*")]
            )
            if path:
                var.set(path)

        self._v_name = tk.StringVar(value=self.conf.node_name)
        self._v_ip   = tk.StringVar(value=self.conf.advertise_ip)
        self._v_gpu  = tk.StringVar(value=str(self.conf.gpu_layers))

        row("Node name:", self._v_name)
        row("Advertise IP:", self._v_ip)
        row("GPU layers (0=CPU):", self._v_gpu, "0")

        if self.conf.role == "orchestrator":
            tk.Label(body, text="Model file (GGUF):", bg=BG, fg=FG,
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(12, 2))
            self._v_model = tk.StringVar(value=self.conf.model_path)
            f2 = tk.Frame(body, bg=BG)
            f2.pack(fill="x")
            ttk.Entry(f2, textvariable=self._v_model, width=44).pack(side="left")
            ttk.Button(f2, text="Browse…", width=8,
                       command=lambda: _browse(self._v_model)).pack(side="left", padx=4)
        else:
            self._v_model = tk.StringVar(value="")

        self._v_auto = tk.BooleanVar(value=self.conf.auto_start)
        ttk.Checkbutton(body, text="Start automatically with Windows",
                        variable=self._v_auto).pack(anchor="w", pady=(16, 0))

        self._footer(back_cmd=self._page_role, next_cmd=self._page_install,
                     next_text="Install →")

    def _page_install(self):
        self._clear()
        # Save config
        self.conf.role        = self._role_var.get()
        self.conf.node_name   = self._v_name.get()
        self.conf.advertise_ip = self._v_ip.get()
        self.conf.gpu_layers  = int(self._v_gpu.get() or "0")
        self.conf.model_path  = self._v_model.get()
        self.conf.auto_start  = self._v_auto.get()
        self.conf.install_dir = str(
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "LLMCluster"
        )
        cfg_module.save(self.conf)

        self._header("Setting Up…", "Step 3 of 3")
        body = tk.Frame(self.root, bg=BG, padx=40, pady=20)
        body.pack(fill="both", expand=True)

        self._status_var = tk.StringVar(value="Starting…")
        tk.Label(body, textvariable=self._status_var, bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(anchor="w")

        self._log_box = tk.Text(body, height=10, font=("Consolas", 9),
                                state="disabled", bg="#1e1e1e", fg="#d4d4d4",
                                relief="flat")
        self._log_box.pack(fill="both", expand=True, pady=8)

        self._progress = ttk.Progressbar(body, mode="indeterminate")
        self._progress.pack(fill="x")
        self._progress.start(12)

        threading.Thread(target=self._do_install, daemon=True).start()

    def _log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _do_install(self):
        def step(msg):
            self._status_var.set(msg)
            self._log(f"→ {msg}")

        step("Opening firewall ports…")
        if firewall.is_elevated():
            for r in firewall.open_ports():
                self._log(f"   {r}")
        else:
            self._log("   Skipped (not running as Administrator)")

        step("Configuring auto-start…")
        _set_auto_start(self.conf.auto_start)
        self._log("   Done")

        step(f"Starting {self.conf.role} node…")
        try:
            node.start(self.conf)
            self._log(f"   {self.conf.role.capitalize()} started")
        except Exception as exc:
            self._log(f"   Warning: {exc}")

        self._progress.stop()
        self._status_var.set("Setup complete!")
        self._log("\nAll done! The node is running in the background.")
        self.root.after(0, self._page_done)

    def _page_done(self):
        self._clear()
        self._header("All Done!", f"{self.conf.role.capitalize()} node is running")
        body = tk.Frame(self.root, bg=BG, padx=40, pady=30)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="✓  Node is active", bg=BG, fg="#34a853",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")

        info_lines = [
            f"Role:       {self.conf.role.capitalize()}",
            f"Node name:  {self.conf.node_name}",
            f"Network IP: {self.conf.advertise_ip}",
        ]
        if self.conf.role == "worker":
            info_lines.append(f"RPC port:   {self.conf.rpc_port}")
        else:
            info_lines += [
                f"API port:   {self.conf.llama_server_port}  (OpenAI-compatible)",
                f"Mgmt port:  {self.conf.mgmt_port}",
            ]

        tk.Label(body, text="\n".join(info_lines), bg=BG, fg=FG2,
                 font=("Consolas", 10), justify="left").pack(anchor="w", pady=12)

        tk.Label(body,
                 text="The LLM Cluster icon will appear in your system tray.",
                 bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(anchor="w")

        bar = tk.Frame(self.root, bg=BG, pady=12)
        bar.pack(fill="x", side="bottom")
        ttk.Button(bar, text="Open Dashboard",
                   command=self._open_dashboard).pack(side="left", padx=20)
        ttk.Button(bar, text="Finish", style="Accent.TButton",
                   command=self._finish).pack(side="right", padx=20)

    def _finish(self):
        self.root.withdraw()
        self._start_tray()

    # ── System Tray ───────────────────────────────────────────────────────────

    def _start_tray(self):
        if not node.is_running():
            try:
                node.start(self.conf)
            except Exception as exc:
                log.error("Could not start node: %s", exc)

        icon_img = _make_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("LLM Cluster", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Status", self._tray_status),
            pystray.MenuItem("Workers on network", self._tray_workers),
            pystray.MenuItem("Open Dashboard", self._open_dashboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop node", self._tray_stop),
            pystray.MenuItem("Restart node", self._tray_restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._tray_exit),
        )
        self._tray = pystray.Icon(APP_NAME, icon_img, APP_NAME, menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _tray_status(self, icon, item):
        s = node.status()
        state = "Running" if s["running"] else "Stopped"
        msg = (
            f"Role:    {self.conf.role.capitalize()}\n"
            f"Node:    {self.conf.node_name}\n"
            f"Status:  {state}\n"
            f"Uptime:  {s['uptime_s']}s"
        )
        self.root.after(0, lambda: messagebox.showinfo("Node Status", msg))

    def _tray_workers(self, icon, item):
        self.root.after(0, self._show_workers)

    def _show_workers(self):
        win = tk.Toplevel(self.root)
        win.title("Workers on Network")
        win.geometry("400x300")
        win.configure(bg=BG)
        tk.Label(win, text="Discovering workers…", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(pady=10)
        box = tk.Text(win, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
                      state="disabled")
        box.pack(fill="both", expand=True, padx=10, pady=5)

        def _discover():
            workers = node.discover_workers(timeout=4)
            box.configure(state="normal")
            box.delete("1.0", "end")
            if workers:
                for w in workers:
                    box.insert("end",
                        f"{w['name']}  @  {w['ip']}:{w['port']}\n"
                        f"  RAM: {w['properties'].get('ram_gb','?')} GB  "
                        f"GPU layers: {w['properties'].get('gpu_layers','0')}\n\n"
                    )
            else:
                box.insert("end", "No workers found.\n\nMake sure worker nodes are running\non the same network.")
            box.configure(state="disabled")

        threading.Thread(target=_discover, daemon=True).start()

    def _open_dashboard(self, *_):
        import webbrowser
        if self.conf.role == "orchestrator":
            url = f"http://localhost:{self.conf.mgmt_port}"
        else:
            url = f"http://localhost:{self.conf.sidecar_port}/health"
        webbrowser.open(url)

    def _tray_stop(self, icon, item):
        node.stop()

    def _tray_restart(self, icon, item):
        node.stop()
        node.start(self.conf)

    def _tray_exit(self, icon, item):
        node.stop()
        icon.stop()
        self.root.quit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _center(self, w, h):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _apply_theme(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 9), padding=6)
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=("Segoe UI", 9, "bold"), padding=6)
        style.map("Accent.TButton",
                  background=[("active", "#1557b0"), ("pressed", "#0d47a1")])
        style.configure("TEntry", padding=4)
        style.configure("TCheckbutton", background=BG, font=("Segoe UI", 9))
        style.configure("TRadiobutton", background=CARD, font=("Segoe UI", 10))
