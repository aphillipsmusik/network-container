"""
Windows Orchestrator GUI – tkinter wizard + pystray system tray.
Guides the user through model selection and launches the inference server.
"""
import json
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import pystray
from PIL import Image, ImageDraw

import config as cfg_module
from discovery import DiscoveryService, WorkerRegistry
from launcher import InferenceLauncher

log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_tray_icon() -> Image.Image:
    """Draw a simple 64×64 green circle icon."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], fill=(34, 197, 94))
    d.text((18, 20), "LLM", fill=(255, 255, 255))
    return img


# ── Wizard ────────────────────────────────────────────────────────────────────

STEPS = ["Welcome", "Model", "Network", "Installing", "Done"]

ACCENT = "#2563EB"
BG = "#F8FAFC"
FG = "#1E293B"
CARD = "#FFFFFF"


class OrchestratorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LLM Cluster – Orchestrator Setup")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.geometry("560x440")

        self._conf: Optional[cfg_module.OrchestratorConfig] = None
        self._registry: Optional[WorkerRegistry] = None
        self._discovery: Optional[DiscoveryService] = None
        self._launcher: Optional[InferenceLauncher] = None
        self._tray: Optional[pystray.Icon] = None
        self._step = 0

        # Wizard pages stored as frames
        self._pages: list[tk.Frame] = []
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._show_step(0)

    # ── Build wizard pages ────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=ACCENT, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="LLM Cluster  –  Orchestrator", bg=ACCENT,
                 fg="white", font=("Segoe UI", 14, "bold")).pack(side="left", padx=20)

        # Step indicator
        self._step_var = tk.StringVar(value="Step 1 of 5")
        tk.Label(hdr, textvariable=self._step_var, bg=ACCENT, fg="white",
                 font=("Segoe UI", 10)).pack(side="right", padx=20)

        # Content area
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True, padx=24, pady=16)

        # Nav buttons
        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=24, pady=(0, 16))
        self._btn_back = tk.Button(nav, text="← Back", command=self._go_back,
                                   width=10, bg=CARD, fg=FG,
                                   relief="flat", bd=1, cursor="hand2")
        self._btn_back.pack(side="left")
        self._btn_next = tk.Button(nav, text="Next →", command=self._go_next,
                                   width=10, bg=ACCENT, fg="white",
                                   relief="flat", bd=0, cursor="hand2",
                                   activebackground="#1D4ED8", activeforeground="white")
        self._btn_next.pack(side="right")

        # Build each page
        self._pages = [
            self._page_welcome(),
            self._page_model(),
            self._page_network(),
            self._page_installing(),
            self._page_done(),
        ]

    def _card(self, title: str) -> tk.Frame:
        """Return a white card frame with a section title."""
        for w in self._content.winfo_children():
            w.destroy()
        f = tk.Frame(self._content, bg=CARD, bd=1, relief="solid")
        f.pack(fill="both", expand=True)
        tk.Label(f, text=title, bg=CARD, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        ttk.Separator(f).pack(fill="x", padx=16)
        return f

    # Page 0 – Welcome
    def _page_welcome(self) -> tk.Frame:
        f = tk.Frame(self._content, bg=BG)
        tk.Label(f, text="Welcome to the LLM Cluster\nOrchestrator", bg=BG, fg=FG,
                 font=("Segoe UI", 16, "bold"), justify="center").pack(pady=(30, 12))
        tk.Label(f, text=(
            "This wizard will configure your machine as the\n"
            "cluster orchestrator — it coordinates distributed\n"
            "inference across all worker nodes on your network.\n\n"
            "You will need:\n"
            "  • A GGUF model file (.gguf)\n"
            "  • Workers already running on the same WiFi/LAN"
        ), bg=BG, fg=FG, font=("Segoe UI", 10), justify="left").pack(padx=40)
        return f

    # Page 1 – Model selection
    def _page_model(self) -> tk.Frame:
        f = tk.Frame(self._content, bg=BG)
        tk.Label(f, text="Model File", bg=BG, fg=FG,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(16, 4))

        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=4)
        self._model_var = tk.StringVar()
        e = tk.Entry(row, textvariable=self._model_var, width=44,
                     font=("Segoe UI", 10), bg=CARD)
        e.pack(side="left", ipady=4)
        tk.Button(row, text="Browse…", command=self._browse_model,
                  bg=ACCENT, fg="white", relief="flat", cursor="hand2",
                  font=("Segoe UI", 9)).pack(side="left", padx=(6, 0), ipady=4)

        tk.Label(f, text="GPU layers offloaded to VRAM  (0 = CPU only)",
                 bg=BG, fg=FG, font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 2))
        self._gpu_var = tk.IntVar(value=0)
        ttk.Scale(f, from_=0, to=100, orient="horizontal",
                  variable=self._gpu_var, length=340).pack(anchor="w")
        self._gpu_lbl = tk.Label(f, textvariable=tk.StringVar(), bg=BG, fg=FG,
                                 font=("Segoe UI", 9))
        self._gpu_lbl.pack(anchor="w")
        self._gpu_var.trace_add("write",
            lambda *_: self._gpu_lbl.config(
                text=f"  {self._gpu_var.get()} layers"))
        self._gpu_var.set(0)

        tk.Label(f, text="Context size (tokens)", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 2))
        self._ctx_var = tk.IntVar(value=4096)
        ctx_opts = [2048, 4096, 8192, 16384, 32768]
        ttk.Combobox(f, values=ctx_opts, textvariable=self._ctx_var,
                     width=12, state="readonly").pack(anchor="w")

        return f

    # Page 2 – Network settings
    def _page_network(self) -> tk.Frame:
        f = tk.Frame(self._content, bg=BG)
        tk.Label(f, text="Network Settings", bg=BG, fg=FG,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(16, 4))

        def _row(label, var, default):
            r = tk.Frame(f, bg=BG)
            r.pack(fill="x", pady=3)
            tk.Label(r, text=label, bg=BG, fg=FG, width=26,
                     font=("Segoe UI", 10), anchor="w").pack(side="left")
            var.set(default)
            tk.Entry(r, textvariable=var, width=12,
                     font=("Segoe UI", 10), bg=CARD).pack(side="left", ipady=3)

        self._llm_port_var  = tk.IntVar()
        self._mgmt_port_var = tk.IntVar()
        self._parallel_var  = tk.IntVar()
        _row("Inference port",     self._llm_port_var,  8080)
        _row("Management API port", self._mgmt_port_var, 8888)
        _row("Parallel slots",     self._parallel_var,  4)

        tk.Label(f, text="\nAuto-start server when orchestrator launches",
                 bg=BG, fg=FG, font=("Segoe UI", 10)).pack(anchor="w")
        self._autostart_var = tk.BooleanVar(value=True)
        tk.Checkbutton(f, text="Enable auto-start", variable=self._autostart_var,
                       bg=BG, fg=FG, font=("Segoe UI", 10),
                       activebackground=BG).pack(anchor="w")
        return f

    # Page 3 – Installing (progress)
    def _page_installing(self) -> tk.Frame:
        f = tk.Frame(self._content, bg=BG)
        tk.Label(f, text="Starting Orchestrator…", bg=BG, fg=FG,
                 font=("Segoe UI", 13, "bold")).pack(pady=(30, 16))
        self._progress = ttk.Progressbar(f, mode="indeterminate", length=340)
        self._progress.pack()
        self._status_var = tk.StringVar(value="Initialising…")
        tk.Label(f, textvariable=self._status_var, bg=BG, fg=FG,
                 font=("Segoe UI", 10), wraplength=380).pack(pady=12)
        return f

    # Page 4 – Done
    def _page_done(self) -> tk.Frame:
        f = tk.Frame(self._content, bg=BG)
        tk.Label(f, text="✓  Orchestrator Running", bg=BG, fg="#16A34A",
                 font=("Segoe UI", 16, "bold")).pack(pady=(30, 12))
        self._done_info = tk.StringVar(value="")
        tk.Label(f, textvariable=self._done_info, bg=BG, fg=FG,
                 font=("Segoe UI", 10), justify="left").pack(padx=40)
        tk.Button(f, text="Open Dashboard", command=self._open_dashboard,
                  bg=ACCENT, fg="white", relief="flat", cursor="hand2",
                  font=("Segoe UI", 10), padx=16, pady=6).pack(pady=16)
        tk.Label(f, text="The orchestrator continues running in the system tray.",
                 bg=BG, fg="#64748B", font=("Segoe UI", 9)).pack()
        return f

    # ── Navigation ────────────────────────────────────────────────────────────

    def _show_step(self, idx: int):
        self._step = idx
        self._step_var.set(f"Step {idx + 1} of {len(STEPS)}")

        for w in self._content.winfo_children():
            w.pack_forget()
        self._pages[idx].pack(fill="both", expand=True)

        self._btn_back.config(state="normal" if idx > 0 else "disabled")
        if idx == len(STEPS) - 1:
            self._btn_next.config(text="Finish", command=self._finish)
        elif idx == len(STEPS) - 2:
            self._btn_next.config(text="Next →", state="disabled", command=self._go_next)
        else:
            self._btn_next.config(text="Next →", state="normal", command=self._go_next)

    def _go_next(self):
        if self._step == 1 and not self._validate_model():
            return
        if self._step == 2:
            self._save_config()
            self._show_step(3)
            self._start_services()
            return
        self._show_step(self._step + 1)

    def _go_back(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    def _finish(self):
        self.withdraw()
        self._start_tray()

    # ── Validation / config ───────────────────────────────────────────────────

    def _validate_model(self) -> bool:
        path = self._model_var.get().strip()
        if not path:
            messagebox.showwarning("Model Required",
                                   "Please select a GGUF model file.")
            return False
        if not os.path.exists(path):
            messagebox.showerror("File Not Found",
                                 f"Model file not found:\n{path}")
            return False
        return True

    def _browse_model(self):
        p = filedialog.askopenfilename(
            title="Select GGUF model",
            filetypes=[("GGUF models", "*.gguf"), ("All files", "*.*")],
        )
        if p:
            self._model_var.set(p)

    def _save_config(self):
        self._conf = cfg_module.OrchestratorConfig(
            model_path=self._model_var.get().strip(),
            gpu_layers=self._gpu_var.get(),
            context_size=self._ctx_var.get(),
            llama_server_port=self._llm_port_var.get(),
            mgmt_port=self._mgmt_port_var.get(),
            parallel=self._parallel_var.get(),
            auto_start=self._autostart_var.get(),
        )
        cfg_module.save(self._conf)

    # ── Service startup ───────────────────────────────────────────────────────

    def _start_services(self):
        threading.Thread(target=self._run_startup, daemon=True).start()

    def _run_startup(self):
        self._set_status("Starting mDNS discovery…")
        self._progress.start(12)

        self._registry = WorkerRegistry(on_change=self._on_worker_change)
        self._discovery = DiscoveryService(self._registry)
        self._discovery.start()

        import time
        time.sleep(self._conf.discovery_timeout)

        count = len(self._registry.active_workers())
        self._set_status(f"Found {count} worker(s). Launching inference server…")

        self._launcher = InferenceLauncher(
            self._registry, on_status_change=self._set_status
        )
        ok = self._launcher.start(self._conf)

        self._progress.stop()
        if ok:
            self.after(0, self._on_startup_done)
        else:
            self.after(0, lambda: messagebox.showerror(
                "Launch Failed",
                "Could not start llama-server.exe.\n"
                "Check that the model file exists and llama-server.exe "
                "is installed in the LLMCluster\\bin directory."
            ))

    def _set_status(self, msg: str):
        self.after(0, lambda: self._status_var.set(msg))

    def _on_startup_done(self):
        workers = self._registry.active_workers()
        info_lines = [
            f"Inference server:  {self._conf.inference_url}",
            f"Management API:    {self._conf.mgmt_url}",
            f"Active workers:    {len(workers)}",
        ]
        if workers:
            info_lines.append("\nConnected workers:")
            for w in workers[:5]:
                info_lines.append(f"  • {w.name}  ({w.ip})")
        self._done_info.set("\n".join(info_lines))
        self._btn_next.config(state="normal")
        self._show_step(4)

    def _on_worker_change(self, event: str, node):
        log.info("Worker %s: %s", event, node.name)
        if self._launcher and self._launcher.running:
            threading.Thread(target=self._launcher.restart, daemon=True).start()

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def _open_dashboard(self):
        if self._conf:
            webbrowser.open(self._conf.mgmt_url)

    # ── System tray ───────────────────────────────────────────────────────────

    def _start_tray(self):
        def _workers_label():
            if self._registry:
                c = len(self._registry.active_workers())
                return f"Workers online: {c}"
            return "Workers: –"

        def _status_label():
            if self._launcher and self._launcher.running:
                return f"Running  ({self._launcher.uptime_s}s uptime)"
            return "Stopped"

        menu = pystray.Menu(
            pystray.MenuItem(lambda _: _status_label(), lambda: None, enabled=False),
            pystray.MenuItem(lambda _: _workers_label(), lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Dashboard", self._tray_open_dashboard),
            pystray.MenuItem("Restart Inference Server", self._tray_restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Window", self._tray_show),
            pystray.MenuItem("Quit", self._tray_quit),
        )
        self._tray = pystray.Icon(
            "LLMCluster-Orchestrator",
            icon=_make_tray_icon(),
            title="LLM Cluster Orchestrator",
            menu=menu,
        )
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _tray_open_dashboard(self, icon=None, item=None):
        self._open_dashboard()

    def _tray_restart(self, icon=None, item=None):
        if self._launcher:
            threading.Thread(target=self._launcher.restart, daemon=True).start()

    def _tray_show(self, icon=None, item=None):
        self.after(0, self.deiconify)

    def _tray_quit(self, icon=None, item=None):
        self._shutdown()

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _on_close(self):
        if messagebox.askyesno(
            "Minimise to Tray?",
            "Keep the orchestrator running in the system tray?"
        ):
            self.withdraw()
            if self._tray is None:
                self._start_tray()
        else:
            self._shutdown()

    def _shutdown(self):
        if self._launcher:
            self._launcher.stop()
        if self._discovery:
            self._discovery.stop()
        if self._tray:
            self._tray.stop()
        self.destroy()
