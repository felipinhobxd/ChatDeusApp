from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .config import (
    AppConfig,
    CHARACTER_DIR,
    CONFIG_PATH,
    install_character_image,
    load_config,
    remove_character_image,
    save_config,
)
from .runtime import Runtime
from .tts import TTSManager

log = logging.getLogger(__name__)

IDLE_CHOICES = [("none", "Parado"), ("float", "Flutuar"), ("breathe", "Respirar")]
SPEAK_CHOICES = [
    ("auto", "Automático por emoção"), ("bounce", "Pular"), ("shake", "Balançar"),
    ("pulse", "Pulsar"), ("talk", "Falar"), ("none", "Sem animação"),
]


class QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue[str]):
        super().__init__(); self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        try: self.q.put_nowait(self.format(record))
        except queue.Full: pass


class DesktopApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ChatDeusApp")
        self.root.geometry("900x760")
        self.root.minsize(820, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.config = load_config()
        self.runtime: Runtime | None = None
        self.log_queue: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.vars: dict[str, tk.Variable] = {}
        self._install_logging(); self._build_ui(); self._fill_from_config(); self._poll_logs()

    def _install_logging(self) -> None:
        root_logger = logging.getLogger(); root_logger.setLevel(logging.INFO)
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
        root_logger.addHandler(handler)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        try: style.theme_use("vista")
        except tk.TclError: pass
        wrapper = ttk.Frame(self.root, padding=14); wrapper.pack(fill="both", expand=True)
        ttk.Label(wrapper, text="ChatDeusApp", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(wrapper, text="Configure Twitch, vozes, personagens animados e OBS sem editar código.").pack(anchor="w", pady=(0, 12))
        notebook = ttk.Notebook(wrapper); notebook.pack(fill="both", expand=True)
        self.tab_connections = ttk.Frame(notebook, padding=14)
        self.tab_app = ttk.Frame(notebook, padding=14)
        self.tab_characters = ttk.Frame(notebook, padding=14)
        self.tab_logs = ttk.Frame(notebook, padding=14)
        notebook.add(self.tab_connections, text="Conexões")
        notebook.add(self.tab_app, text="Aplicativo")
        notebook.add(self.tab_characters, text="Personagens")
        notebook.add(self.tab_logs, text="Status")
        self._build_connections_tab(); self._build_app_tab(); self._build_characters_tab(); self._build_logs_tab()
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
        ttk.Label(tab, text="O token precisa permitir leitura do chat e fica salvo apenas no perfil local do Windows.").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Separator(tab).grid(row=4, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(tab, text="Microsoft Azure TTS", font=("Segoe UI", 12, "bold")).grid(row=5, column=0, columnspan=2, sticky="w")
        self.vars["azure_enabled"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Usar Azure TTS quando configurado", variable=self.vars["azure_enabled"]).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        self._field(tab, 7, "Chave", "azure_key", show="•"); self._field(tab, 8, "Região (ex.: brazilsouth)", "azure_region")
        self.vars["fallback_gtts"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Usar voz gratuita (gTTS) se Azure falhar", variable=self.vars["fallback_gtts"]).grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 12))
        ttk.Separator(tab).grid(row=10, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(tab, text="OBS WebSocket (opcional)", font=("Segoe UI", 12, "bold")).grid(row=11, column=0, columnspan=2, sticky="w")
        self.vars["obs_enabled"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Ativar integração avançada com OBS", variable=self.vars["obs_enabled"]).grid(row=12, column=0, columnspan=2, sticky="w", pady=4)
        self._field(tab, 13, "Host", "obs_host"); self._field(tab, 14, "Porta", "obs_port"); self._field(tab, 15, "Senha", "obs_password", show="•")
        self._field(tab, 16, "Fonte de áudio", "obs_source"); self._field(tab, 17, "Filtro Jogador 1", "obs_filter_1"); self._field(tab, 18, "Filtro Jogador 2", "obs_filter_2"); self._field(tab, 19, "Filtro Jogador 3", "obs_filter_3")

    def _build_app_tab(self) -> None:
        tab = self.tab_app; tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Comandos do chat", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        self._field(tab, 1, "Jogador 1", "command_player_1"); self._field(tab, 2, "Jogador 2", "command_player_2"); self._field(tab, 3, "Jogador 3", "command_player_3")
        ttk.Separator(tab).grid(row=4, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(tab, text="Servidor local / Fonte de Navegador do OBS", font=("Segoe UI", 12, "bold")).grid(row=5, column=0, columnspan=2, sticky="w")
        self._field(tab, 6, "Host", "web_host"); self._field(tab, 7, "Porta", "web_port")
        self.vars["open_panel_on_start"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Abrir painel automaticamente ao iniciar", variable=self.vars["open_panel_on_start"]).grid(row=8, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(tab, text="No OBS, adicione uma única Fonte de Navegador usando /overlay. As imagens dos personagens e as animações já aparecem nela; WebSocket não é obrigatório.", wraplength=700).grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_characters_tab(self) -> None:
        tab = self.tab_characters
        ttk.Label(tab, text="Personagens do overlay", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(tab, text="Escolha uma imagem PNG/JPG/WebP/GIF. Ela é copiada para o perfil do ChatDeusApp e aparece automaticamente na Fonte de Navegador do OBS.", wraplength=760).pack(anchor="w", pady=(0, 10))
        for player in (1, 2, 3):
            box = ttk.LabelFrame(tab, text=f"Jogador {player}", padding=10); box.pack(fill="x", pady=5)
            box.columnconfigure(1, weight=1)
            image_key = f"character_image_{player}"; self.vars[image_key] = tk.StringVar()
            ttk.Label(box, text="Imagem").grid(row=0, column=0, sticky="w", padx=(0, 8))
            ttk.Entry(box, textvariable=self.vars[image_key], state="readonly").grid(row=0, column=1, columnspan=4, sticky="ew")
            ttk.Button(box, text="Escolher...", command=lambda p=player: self.choose_character(p)).grid(row=0, column=5, padx=(8, 4))
            ttk.Button(box, text="Remover", command=lambda p=player: self.remove_character(p)).grid(row=0, column=6)
            numeric = [("Tamanho px", "size", 320), ("Intensidade 0-10", "intensity", 5), ("X px", "x", 0), ("Y px", "y", 0)]
            for col, (label, suffix, _default) in enumerate(numeric):
                key = f"character_{suffix}_{player}"; self.vars[key] = tk.StringVar()
                ttk.Label(box, text=label).grid(row=1, column=col * 2, sticky="w", pady=(8, 0), padx=(0, 4))
                ttk.Entry(box, textvariable=self.vars[key], width=8).grid(row=1, column=col * 2 + 1, sticky="w", pady=(8, 0), padx=(0, 10))
            idle_key = f"character_idle_{player}"; self.vars[idle_key] = tk.StringVar()
            speak_key = f"character_speaking_{player}"; self.vars[speak_key] = tk.StringVar()
            mirror_key = f"character_mirror_{player}"; self.vars[mirror_key] = tk.BooleanVar()
            ttk.Label(box, text="Parado").grid(row=2, column=0, sticky="w", pady=(8, 0))
            ttk.Combobox(box, textvariable=self.vars[idle_key], values=[v for v, _ in IDLE_CHOICES], state="readonly", width=12).grid(row=2, column=1, sticky="w", pady=(8, 0))
            ttk.Label(box, text="Falando").grid(row=2, column=2, sticky="w", pady=(8, 0))
            ttk.Combobox(box, textvariable=self.vars[speak_key], values=[v for v, _ in SPEAK_CHOICES], state="readonly", width=18).grid(row=2, column=3, sticky="w", pady=(8, 0))
            ttk.Checkbutton(box, text="Espelhar", variable=self.vars[mirror_key]).grid(row=2, column=4, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(tab, text="Dica: deixe 'Falando = auto'. O movimento muda conforme (bravo), (animado), (sussurro), etc.", foreground="#555").pack(anchor="w", pady=(8, 0))

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

    def choose_character(self, player: int) -> None:
        path = filedialog.askopenfilename(title=f"Escolher imagem do Jogador {player}", filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.gif"), ("Todos os arquivos", "*.*")])
        if not path: return
        try:
            filename = install_character_image(player, path); self.vars[f"character_image_{player}"].set(filename); self.save(); self.status_var.set(f"Imagem do Jogador {player} salva em {CHARACTER_DIR}")
        except Exception as exc: messagebox.showerror("Imagem inválida", str(exc))

    def remove_character(self, player: int) -> None:
        remove_character_image(player); self.vars[f"character_image_{player}"].set(""); self.save(); self.status_var.set(f"Imagem do Jogador {player} removida.")

    def save(self) -> AppConfig | None:
        try:
            self.config = self._read_config(); save_config(self.config)
            if self.runtime: self.runtime.apply_visual_config(self.config)
            self.status_var.set(f"Configurações salvas em {CONFIG_PATH}"); return self.config
        except Exception as exc: messagebox.showerror("Configuração inválida", str(exc)); return None

    def start(self) -> None:
        config = self.save()
        if not config: return
        if self.runtime: self.open_panel(); return
        try:
            self.runtime = Runtime(config); self.runtime.start(); self.start_btn.configure(state="disabled"); self.open_btn.configure(state="normal"); self.status_var.set(f"Executando em {self.runtime.base_url}"); log.info("ChatDeusApp iniciado em %s", self.runtime.base_url)
            if config.open_panel_on_start: self.root.after(800, self.open_panel)
        except Exception as exc: self.runtime = None; messagebox.showerror("Erro ao iniciar", str(exc)); log.exception("Falha ao iniciar ChatDeusApp.")

    def open_panel(self) -> None:
        if self.runtime: self.runtime.open_panel()
        else: messagebox.showinfo("ChatDeusApp", "Inicie o aplicativo primeiro.")

    def test_voice(self) -> None:
        config = self.save()
        if not config: return
        def work():
            try:
                manager = TTSManager(config); path = manager.synthesize("Olá! O ChatDeusApp está configurado e pronto para falar em português.", config.default_voice_1, "default")
                if not path: raise RuntimeError("Não foi possível gerar áudio. Confira Azure ou habilite o fallback gTTS.")
                from .audio import AudioWorker
                AudioWorker._play(path); self.root.after(0, lambda: self.status_var.set("Teste de voz concluído."))
            except Exception as exc: log.exception("Falha no teste de voz."); self.root.after(0, lambda: messagebox.showerror("Teste de voz", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _poll_logs(self) -> None:
        changed = False
        while True:
            try: line = self.log_queue.get_nowait()
            except queue.Empty: break
            self.logs.configure(state="normal"); self.logs.insert("end", line + "\n"); self.logs.see("end"); self.logs.configure(state="disabled"); changed = True
        self.root.after(200 if changed else 400, self._poll_logs)

    def run(self) -> None: self.root.mainloop()

def run_desktop() -> None: DesktopApp().run()
