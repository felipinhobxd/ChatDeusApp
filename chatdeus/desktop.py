from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import AppConfig, CONFIG_PATH, load_config, save_config
from .runtime import Runtime
from .tts import TTSManager

log = logging.getLogger(__name__)


class QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue[str]):
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.q.put_nowait(self.format(record))
        except queue.Full:
            pass


class DesktopApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ChatDeusApp")
        self.root.geometry("820x720")
        self.root.minsize(760, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.config = load_config()
        self.runtime: Runtime | None = None
        self.log_queue: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.vars: dict[str, tk.Variable] = {}
        self._install_logging()
        self._build_ui()
        self._fill_from_config()
        self._poll_logs()

    def _install_logging(self) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
        root_logger.addHandler(handler)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        wrapper = ttk.Frame(self.root, padding=14)
        wrapper.pack(fill="both", expand=True)
        ttk.Label(wrapper, text="ChatDeusApp", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(wrapper, text="Configure Twitch, voz e OBS sem editar código ou variáveis de ambiente.").pack(anchor="w", pady=(0, 12))
        notebook = ttk.Notebook(wrapper)
        notebook.pack(fill="both", expand=True)
        self.tab_connections = ttk.Frame(notebook, padding=14)
        self.tab_app = ttk.Frame(notebook, padding=14)
        self.tab_logs = ttk.Frame(notebook, padding=14)
        notebook.add(self.tab_connections, text="Conexões")
        notebook.add(self.tab_app, text="Aplicativo")
        notebook.add(self.tab_logs, text="Status")
        self._build_connections_tab(); self._build_app_tab(); self._build_logs_tab()
        actions = ttk.Frame(wrapper); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Salvar configurações", command=self.save).pack(side="left")
        self.start_btn = ttk.Button(actions, text="Iniciar ChatDeusApp", command=self.start); self.start_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(actions, text="Abrir painel", command=self.open_panel, state="disabled"); self.open_btn.pack(side="left")
        ttk.Button(actions, text="Testar voz", command=self.test_voice).pack(side="right")
        self.status_var = tk.StringVar(value="Pronto para configurar.")
        ttk.Label(wrapper, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def _field(self, parent, row: int, label: str, key: str, *, show: str | None = None, width: int = 48):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
        var = tk.StringVar(); self.vars[key] = var
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _build_connections_tab(self) -> None:
        tab = self.tab_connections; tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Twitch", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        self._field(tab, 1, "Canal", "twitch_channel"); self._field(tab, 2, "Token OAuth", "twitch_token", show="•")
        ttk.Label(tab, text="O token precisa permitir leitura do chat. Ele fica salvo apenas no perfil local do Windows.").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Separator(tab).grid(row=4, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(tab, text="Microsoft Azure TTS", font=("Segoe UI", 12, "bold")).grid(row=5, column=0, columnspan=2, sticky="w")
        self.vars["azure_enabled"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Usar Azure TTS quando configurado", variable=self.vars["azure_enabled"]).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        self._field(tab, 7, "Chave", "azure_key", show="•"); self._field(tab, 8, "Região (ex.: brazilsouth)", "azure_region")
        self.vars["fallback_gtts"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Usar voz gratuita (gTTS) se Azure falhar", variable=self.vars["fallback_gtts"]).grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 12))
        ttk.Separator(tab).grid(row=10, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(tab, text="OBS WebSocket (opcional)", font=("Segoe UI", 12, "bold")).grid(row=11, column=0, columnspan=2, sticky="w")
        self.vars["obs_enabled"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Ativar integração com OBS", variable=self.vars["obs_enabled"]).grid(row=12, column=0, columnspan=2, sticky="w", pady=4)
        self._field(tab, 13, "Host", "obs_host"); self._field(tab, 14, "Porta", "obs_port"); self._field(tab, 15, "Senha", "obs_password", show="•")
        self._field(tab, 16, "Fonte de áudio", "obs_source"); self._field(tab, 17, "Filtro Jogador 1", "obs_filter_1"); self._field(tab, 18, "Filtro Jogador 2", "obs_filter_2"); self._field(tab, 19, "Filtro Jogador 3", "obs_filter_3")

    def _build_app_tab(self) -> None:
        tab = self.tab_app; tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Comandos do chat", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        self._field(tab, 1, "Jogador 1", "command_player_1"); self._field(tab, 2, "Jogador 2", "command_player_2"); self._field(tab, 3, "Jogador 3", "command_player_3")
        ttk.Separator(tab).grid(row=4, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(tab, text="Servidor local / OBS Browser Source", font=("Segoe UI", 12, "bold")).grid(row=5, column=0, columnspan=2, sticky="w")
        self._field(tab, 6, "Host", "web_host"); self._field(tab, 7, "Porta", "web_port")
        self.vars["open_panel_on_start"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Abrir painel automaticamente ao iniciar", variable=self.vars["open_panel_on_start"]).grid(row=8, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(tab, text="No OBS, adicione uma Fonte de Navegador e use /overlay. O endereço aparece no painel depois que o aplicativo iniciar.", wraplength=650).grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_logs_tab(self) -> None:
        self.logs = tk.Text(self.tab_logs, wrap="word", state="disabled", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(self.tab_logs, orient="vertical", command=self.logs.yview)
        self.logs.configure(yscrollcommand=scrollbar.set); self.logs.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")

    def _fill_from_config(self) -> None:
        for key, var in self.vars.items():
            if hasattr(self.config, key): var.set(getattr(self.config, key))

    def _read_config(self) -> AppConfig:
        base = load_config()
        for key, var in self.vars.items():
            if not hasattr(base, key): continue
            value = var.get(); current = getattr(base, key)
            if isinstance(current, bool): value = bool(value)
            elif isinstance(current, int):
                try: value = int(value)
                except (TypeError, ValueError): raise ValueError(f"O campo {key} precisa ser numérico.")
            setattr(base, key, value)
        return base.normalized()

    def save(self) -> AppConfig | None:
        try:
            self.config = self._read_config(); save_config(self.config)
            self.status_var.set(f"Configurações salvas em {CONFIG_PATH}"); return self.config
        except Exception as exc:
            messagebox.showerror("Configuração inválida", str(exc)); return None

    def start(self) -> None:
        config = self.save()
        if not config: return
        if self.runtime: self.open_panel(); return
        try:
            self.runtime = Runtime(config); self.runtime.start(); self.start_btn.configure(state="disabled"); self.open_btn.configure(state="normal")
            self.status_var.set(f"Executando em {self.runtime.base_url}"); log.info("ChatDeusApp iniciado em %s", self.runtime.base_url)
            if config.open_panel_on_start: self.root.after(800, self.open_panel)
        except Exception as exc:
            self.runtime = None; messagebox.showerror("Erro ao iniciar", str(exc)); log.exception("Falha ao iniciar ChatDeusApp.")

    def open_panel(self) -> None:
        if self.runtime: self.runtime.open_panel()
        else: messagebox.showinfo("ChatDeusApp", "Inicie o aplicativo primeiro.")

    def test_voice(self) -> None:
        config = self.save()
        if not config: return
        def work():
            try:
                manager = TTSManager(config)
                path = manager.synthesize("Olá! O ChatDeusApp está configurado e pronto para falar em português.", config.default_voice_1, "default")
                if not path: raise RuntimeError("Não foi possível gerar áudio. Confira Azure ou habilite o fallback gTTS.")
                from .audio import AudioWorker
                AudioWorker._play(path)
                self.root.after(0, lambda: self.status_var.set("Teste de voz concluído."))
            except Exception as exc:
                log.exception("Falha no teste de voz."); self.root.after(0, lambda: messagebox.showerror("Teste de voz", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _poll_logs(self) -> None:
        changed = False
        while True:
            try: line = self.log_queue.get_nowait()
            except queue.Empty: break
            self.logs.configure(state="normal"); self.logs.insert("end", line + "\n"); self.logs.see("end"); self.logs.configure(state="disabled"); changed = True
        self.root.after(200 if changed else 400, self._poll_logs)

    def run(self) -> None:
        self.root.mainloop()


def run_desktop() -> None:
    DesktopApp().run()
