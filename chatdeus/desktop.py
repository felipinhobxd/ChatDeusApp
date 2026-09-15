from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .audio import AudioWorker
from .config import (
    AppConfig, CHARACTER_DIR, CONFIG_PATH, install_character_image, load_config,
    remove_character_image, save_config,
)
from .runtime import Runtime
from .tts import TTSManager
from .twitch_auth import TwitchAuthError, TwitchAuthManager

log = logging.getLogger(__name__)

IDLE_CHOICES = ["none", "float", "breathe"]
SPEAK_CHOICES = ["auto", "bounce", "shake", "pulse", "talk", "none"]
TTS_LABELS = {
    "edge": "Microsoft Edge TTS — grátis, recomendado",
    "gtts": "gTTS — grátis, simples",
    "azure": "Azure TTS — requer chave/créditos",
}
AUDIO_LABELS = {
    "browser": "Fonte de Navegador do OBS — recomendado",
    "speakers": "Alto-falantes do PC",
}


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
        self.root.geometry("960x820")
        self.root.minsize(860, 720)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.config = load_config()
        self.runtime: Runtime | None = None
        self.auth = TwitchAuthManager(self.config, on_status=self._auth_status_from_thread)
        self.log_queue: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.vars: dict[str, tk.Variable] = {}
        self._manual_entries: list[ttk.Entry] = []
        self._start_after_login = False

        self._install_logging()
        self._build_ui()
        self._fill_from_config()
        self._set_manual_state()
        self._refresh_twitch_label()
        self._refresh_obs_url()
        self._poll_logs()
        self._poll_runtime_status()

        if self.auth.has_managed_credentials:
            threading.Thread(target=self._validate_saved_twitch, daemon=True).start()

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
        ttk.Label(wrapper, text="Twitch com um clique, voz grátis com emoções e OBS sem configuração complicada.").pack(anchor="w", pady=(0, 12))

        notebook = ttk.Notebook(wrapper); notebook.pack(fill="both", expand=True)
        self.tab_connections = ttk.Frame(notebook, padding=14)
        self.tab_obs = ttk.Frame(notebook, padding=14)
        self.tab_app = ttk.Frame(notebook, padding=14)
        self.tab_characters = ttk.Frame(notebook, padding=14)
        self.tab_logs = ttk.Frame(notebook, padding=14)
        notebook.add(self.tab_connections, text="Twitch e Voz")
        notebook.add(self.tab_obs, text="OBS Fácil")
        notebook.add(self.tab_app, text="Aplicativo")
        notebook.add(self.tab_characters, text="Personagens")
        notebook.add(self.tab_logs, text="Status")
        self._build_connections_tab(); self._build_obs_tab(); self._build_app_tab(); self._build_characters_tab(); self._build_logs_tab()

        actions = ttk.Frame(wrapper); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Salvar configurações", command=self.save).pack(side="left")
        self.start_btn = ttk.Button(actions, text="Iniciar ChatDeusApp", command=self.start); self.start_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(actions, text="Abrir painel", command=self.open_panel, state="disabled"); self.open_btn.pack(side="left")
        ttk.Button(actions, text="Testar voz", command=self.test_voice).pack(side="right")
        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(wrapper, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def _field_grid(self, parent, row: int, label: str, key: str, *, show: str | None = None, width: int = 48) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
        var = tk.StringVar(); self.vars[key] = var
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _build_connections_tab(self) -> None:
        tab = self.tab_connections
        twitch = ttk.LabelFrame(tab, text="Twitch", padding=12); twitch.pack(fill="x", pady=(0, 10)); twitch.columnconfigure(0, weight=1)
        self.twitch_status_var = tk.StringVar(value="Twitch: verificando...")
        ttk.Label(twitch, textvariable=self.twitch_status_var, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(twitch, text="Clique em Entrar com Twitch. O navegador abre e o canal/token são configurados automaticamente.", wraplength=800).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 9))
        self.login_btn = ttk.Button(twitch, text="Entrar com Twitch", command=self.login_twitch); self.login_btn.grid(row=2, column=0, sticky="w")
        self.disconnect_btn = ttk.Button(twitch, text="Desconectar", command=self.disconnect_twitch); self.disconnect_btn.grid(row=2, column=1, sticky="w", padx=8)
        self.open_auth_btn = ttk.Button(twitch, text="Abrir autorização", command=self.open_twitch_authorization, state="disabled"); self.open_auth_btn.grid(row=2, column=2, sticky="w")
        self.twitch_code_var = tk.StringVar(value=""); ttk.Label(twitch, textvariable=self.twitch_code_var).grid(row=3, column=0, columnspan=4, sticky="w", pady=(7, 0))
        manual = ttk.LabelFrame(twitch, text="Modo manual antigo (opcional)", padding=8); manual.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0)); manual.columnconfigure(1, weight=1)
        self.vars["twitch_manual_mode"] = tk.BooleanVar()
        ttk.Checkbutton(manual, text="Usar canal + OAuth token manual", variable=self.vars["twitch_manual_mode"], command=self._set_manual_state).grid(row=0, column=0, columnspan=2, sticky="w")
        self._manual_entries.append(self._field_grid(manual, 1, "Canal", "twitch_channel"))
        self._manual_entries.append(self._field_grid(manual, 2, "Token OAuth", "twitch_token", show="•"))

        voice = ttk.LabelFrame(tab, text="Voz / TTS", padding=12); voice.pack(fill="x"); voice.columnconfigure(1, weight=1)
        ttk.Label(voice, text="Provedor").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
        self.vars["tts_provider"] = tk.StringVar()
        ttk.Combobox(voice, textvariable=self.vars["tts_provider"], values=list(TTS_LABELS), state="readonly").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(voice, text="Edge TTS é o recomendado: vozes neurais da Microsoft, sem chave e sem créditos. Precisa de internet.", wraplength=800).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(voice, text="Força das emoções (0-10)").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=4)
        self.vars["emotion_strength"] = tk.StringVar(); ttk.Spinbox(voice, from_=0, to=10, textvariable=self.vars["emotion_strength"], width=8).grid(row=2, column=1, sticky="w")
        self.vars["fallback_gtts"] = tk.BooleanVar(); ttk.Checkbutton(voice, text="Usar gTTS como fallback se a voz principal falhar", variable=self.vars["fallback_gtts"]).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        azure = ttk.LabelFrame(voice, text="Azure (opcional — não é necessário)", padding=8); azure.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0)); azure.columnconfigure(1, weight=1)
        self._field_grid(azure, 0, "Chave", "azure_key", show="•"); self._field_grid(azure, 1, "Região", "azure_region")
        self.vars["azure_enabled"] = tk.BooleanVar()

    def _build_obs_tab(self) -> None:
        tab = self.tab_obs
        easy = ttk.LabelFrame(tab, text="OBS — modo simples (recomendado)", padding=12); easy.pack(fill="x", pady=(0, 10)); easy.columnconfigure(1, weight=1)
        ttk.Label(easy, text="O próprio /overlay toca o TTS. No OBS, a Fonte de Navegador vira uma fonte de áudio no Mixer.", wraplength=820).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(easy, text="Saída de áudio").grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.vars["audio_output"] = tk.StringVar()
        ttk.Combobox(easy, textvariable=self.vars["audio_output"], values=list(AUDIO_LABELS), state="readonly").grid(row=1, column=1, sticky="ew")
        self.vars["browser_audio_fallback"] = tk.BooleanVar()
        ttk.Checkbutton(easy, text="Se o OBS não estiver aberto, tocar no PC automaticamente", variable=self.vars["browser_audio_fallback"]).grid(row=2, column=0, columnspan=3, sticky="w", pady=(7, 8))
        ttk.Label(easy, text="URL da Fonte de Navegador").grid(row=3, column=0, sticky="w", padx=(0, 12))
        self.obs_url_var = tk.StringVar()
        ttk.Entry(easy, textvariable=self.obs_url_var, state="readonly").grid(row=3, column=1, sticky="ew")
        ttk.Button(easy, text="Copiar URL", command=self.copy_overlay_url).grid(row=3, column=2, padx=(8, 0))
        buttons = ttk.Frame(easy); buttons.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Abrir overlay", command=self.open_overlay).pack(side="left")
        ttk.Button(buttons, text="Testar áudio no OBS", command=self.test_obs_audio).pack(side="left", padx=8)
        ttk.Label(easy, text="No OBS: Fontes → + → Navegador → cole a URL → marque 'Controlar áudio via OBS'. Pronto: o áudio aparece no Mixer.", wraplength=820).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))

        advanced = ttk.LabelFrame(tab, text="OBS WebSocket avançado (opcional — não precisa para áudio/personagens)", padding=12); advanced.pack(fill="x"); advanced.columnconfigure(1, weight=1)
        self.vars["obs_enabled"] = tk.BooleanVar(); ttk.Checkbutton(advanced, text="Ativar apenas para ligar/desligar filtros automaticamente", variable=self.vars["obs_enabled"]).grid(row=0, column=0, columnspan=2, sticky="w")
        self._field_grid(advanced, 1, "Host", "obs_host"); self._field_grid(advanced, 2, "Porta", "obs_port")
        self._field_grid(advanced, 3, "Senha", "obs_password", show="•"); self._field_grid(advanced, 4, "Fonte", "obs_source")
        self._field_grid(advanced, 5, "Filtro Jogador 1", "obs_filter_1"); self._field_grid(advanced, 6, "Filtro Jogador 2", "obs_filter_2"); self._field_grid(advanced, 7, "Filtro Jogador 3", "obs_filter_3")

    def _build_app_tab(self) -> None:
        tab = self.tab_app; tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Quantidade de jogadores", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(tab, text="Jogadores ativos").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        self.vars["active_players"] = tk.StringVar(); ttk.Spinbox(tab, from_=1, to=3, textvariable=self.vars["active_players"], width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(tab, text="Escolha 1, 2 ou 3. Slots extras somem do painel/overlay e seus comandos deixam de participar.", wraplength=720).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(tab, text="Comandos do chat", font=("Segoe UI", 12, "bold")).grid(row=3, column=0, columnspan=2, sticky="w")
        self._field_grid(tab, 4, "Jogador 1", "command_player_1"); self._field_grid(tab, 5, "Jogador 2", "command_player_2"); self._field_grid(tab, 6, "Jogador 3", "command_player_3")
        ttk.Separator(tab).grid(row=7, column=0, columnspan=2, sticky="ew", pady=12)
        self._field_grid(tab, 8, "Host local", "web_host"); self._field_grid(tab, 9, "Porta", "web_port")
        self.vars["open_panel_on_start"] = tk.BooleanVar(); ttk.Checkbutton(tab, text="Abrir painel automaticamente ao iniciar", variable=self.vars["open_panel_on_start"]).grid(row=10, column=0, columnspan=2, sticky="w", pady=4)

    def _build_characters_tab(self) -> None:
        tab = self.tab_characters
        ttk.Label(tab, text="Personagens do overlay", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(tab, text="Escolha PNG/JPG/WebP/GIF. Só os jogadores ativos aparecem na live.", wraplength=780).pack(anchor="w", pady=(0, 10))
        for player in (1, 2, 3):
            box = ttk.LabelFrame(tab, text=f"Jogador {player}", padding=10); box.pack(fill="x", pady=5); box.columnconfigure(1, weight=1)
            image_key = f"character_image_{player}"; self.vars[image_key] = tk.StringVar()
            ttk.Label(box, text="Imagem").grid(row=0, column=0, sticky="w", padx=(0, 8))
            ttk.Entry(box, textvariable=self.vars[image_key], state="readonly").grid(row=0, column=1, columnspan=4, sticky="ew")
            ttk.Button(box, text="Escolher...", command=lambda p=player: self.choose_character(p)).grid(row=0, column=5, padx=(8, 4))
            ttk.Button(box, text="Remover", command=lambda p=player: self.remove_character(p)).grid(row=0, column=6)
            for col, (label, suffix) in enumerate([("Tamanho px", "size"), ("Intensidade", "intensity"), ("X px", "x"), ("Y px", "y")]):
                key = f"character_{suffix}_{player}"; self.vars[key] = tk.StringVar()
                ttk.Label(box, text=label).grid(row=1, column=col * 2, sticky="w", pady=(8, 0), padx=(0, 4))
                ttk.Entry(box, textvariable=self.vars[key], width=8).grid(row=1, column=col * 2 + 1, sticky="w", pady=(8, 0), padx=(0, 10))
            idle_key = f"character_idle_{player}"; speak_key = f"character_speaking_{player}"; mirror_key = f"character_mirror_{player}"
            self.vars[idle_key] = tk.StringVar(); self.vars[speak_key] = tk.StringVar(); self.vars[mirror_key] = tk.BooleanVar()
            ttk.Label(box, text="Parado").grid(row=2, column=0, sticky="w", pady=(8, 0)); ttk.Combobox(box, textvariable=self.vars[idle_key], values=IDLE_CHOICES, state="readonly", width=12).grid(row=2, column=1, sticky="w", pady=(8, 0))
            ttk.Label(box, text="Falando").grid(row=2, column=2, sticky="w", pady=(8, 0)); ttk.Combobox(box, textvariable=self.vars[speak_key], values=SPEAK_CHOICES, state="readonly", width=18).grid(row=2, column=3, sticky="w", pady=(8, 0))
            ttk.Checkbutton(box, text="Espelhar", variable=self.vars[mirror_key]).grid(row=2, column=4, columnspan=2, sticky="w", pady=(8, 0))

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

    def _set_manual_state(self) -> None:
        enabled = bool(self.vars.get("twitch_manual_mode", tk.BooleanVar(value=False)).get())
        for entry in self._manual_entries: entry.configure(state="normal" if enabled else "disabled")

    def _refresh_twitch_label(self) -> None:
        if self.auth.pending:
            self.twitch_status_var.set("Twitch: aguardando autorização..."); return
        if self.config.twitch_access_token and self.config.twitch_login:
            self.twitch_status_var.set(f"Twitch: conectado como @{self.config.twitch_login} ✓"); self.disconnect_btn.configure(state="normal")
        elif self.config.twitch_manual_mode and self.config.twitch_channel and self.config.twitch_token:
            self.twitch_status_var.set(f"Twitch: modo manual @{self.config.twitch_channel}"); self.disconnect_btn.configure(state="disabled")
        else:
            self.twitch_status_var.set("Twitch: não conectado"); self.disconnect_btn.configure(state="disabled")

    def _refresh_obs_url(self) -> None:
        try:
            cfg = self._read_config()
            host = "127.0.0.1" if cfg.web_host in {"0.0.0.0", "::"} else cfg.web_host
            self.obs_url_var.set(f"http://{host}:{cfg.web_port}/overlay")
        except Exception:
            self.obs_url_var.set("http://127.0.0.1:5000/overlay")

    def copy_overlay_url(self) -> None:
        self._refresh_obs_url(); self.root.clipboard_clear(); self.root.clipboard_append(self.obs_url_var.get()); self.status_var.set("URL do OBS copiada.")

    def open_overlay(self) -> None:
        self._refresh_obs_url(); webbrowser.open(self.obs_url_var.get())

    def test_obs_audio(self) -> None:
        if not self.runtime:
            messagebox.showinfo("Teste do OBS", "Clique em Iniciar ChatDeusApp primeiro e deixe a Fonte de Navegador ativa no OBS.")
            return
        if self.runtime.config.audio_output != "browser":
            messagebox.showinfo("Teste do OBS", "Selecione 'browser' em Saída de áudio e salve primeiro.")
            return
        self.runtime.test_audio(); self.status_var.set("Teste enviado para a Fonte de Navegador do OBS.")

    def login_twitch(self) -> None:
        self.vars["twitch_manual_mode"].set(False); self._set_manual_state()
        config = self.save()
        if not config: return
        self.auth.update_config(config)
        if not self.auth.begin_device_login(): self.status_var.set("O login da Twitch já está em andamento."); return
        self.login_btn.configure(state="disabled"); self.status_var.set("Abrindo a Twitch no navegador...")

    def open_twitch_authorization(self) -> None:
        if self.auth.verification_uri: webbrowser.open(self.auth.verification_uri)

    def disconnect_twitch(self) -> None:
        if messagebox.askyesno("Desconectar Twitch", "Deseja remover a conta Twitch deste computador?"):
            self.status_var.set("Desconectando Twitch..."); threading.Thread(target=self.auth.disconnect, daemon=True).start()

    def _auth_status_from_thread(self, status: dict) -> None:
        try: self.root.after(0, lambda s=dict(status): self._apply_auth_status(s))
        except tk.TclError: pass

    def _apply_auth_status(self, status: dict) -> None:
        state = status.get("state", "")
        if state == "requesting": self.twitch_status_var.set("Twitch: iniciando login..."); self.twitch_code_var.set("")
        elif state == "waiting":
            code = status.get("user_code", ""); self.twitch_status_var.set("Twitch: autorize sua conta no navegador"); self.twitch_code_var.set(f"Código: {code}" if code else "Autorize na página aberta."); self.open_auth_btn.configure(state="normal")
        elif state == "connected":
            self.config = load_config(); self.auth.update_config(self.config); self.vars["twitch_manual_mode"].set(False); self.vars["twitch_channel"].set(self.config.twitch_channel)
            self.twitch_status_var.set(f"Twitch: conectado como @{self.config.twitch_login} ✓"); self.twitch_code_var.set(""); self.login_btn.configure(state="normal"); self.disconnect_btn.configure(state="normal"); self.open_auth_btn.configure(state="disabled"); self.status_var.set("Twitch conectada.")
            if self.runtime: self.runtime.apply_connection_config(self.config)
            if self._start_after_login: self._start_after_login = False; self.root.after(100, self.start)
        elif state == "disconnected":
            self.config = load_config(); self.auth.update_config(self.config); self.twitch_status_var.set("Twitch: não conectado"); self.twitch_code_var.set(""); self.login_btn.configure(state="normal"); self.disconnect_btn.configure(state="disabled"); self.open_auth_btn.configure(state="disabled"); self.status_var.set("Twitch desconectada.")
            if self.runtime: self.runtime.apply_connection_config(self.config)
        elif state == "error":
            self.login_btn.configure(state="normal"); self.open_auth_btn.configure(state="disabled"); self.twitch_code_var.set(""); self.twitch_status_var.set("Twitch: não conectado"); self.status_var.set(f"Twitch: {status.get('error', 'Falha no login.')}"); self._start_after_login = False

    def _validate_saved_twitch(self) -> None:
        try:
            session = self.auth.ensure_valid()
            if session: self._auth_status_from_thread({"state": "connected", "login": session.login})
        except TwitchAuthError as exc: self._auth_status_from_thread({"state": "error", "error": str(exc)})
        except Exception as exc: log.warning("Não foi possível validar a sessão Twitch salva: %s", exc)

    def choose_character(self, player: int) -> None:
        path = filedialog.askopenfilename(title=f"Escolher imagem do Jogador {player}", filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.gif"), ("Todos", "*.*")])
        if not path: return
        try:
            filename = install_character_image(player, path); self.vars[f"character_image_{player}"].set(filename); self.save(); self.status_var.set(f"Imagem do Jogador {player} salva em {CHARACTER_DIR}")
        except Exception as exc: messagebox.showerror("Imagem inválida", str(exc))

    def remove_character(self, player: int) -> None:
        remove_character_image(player); self.vars[f"character_image_{player}"].set(""); self.save(); self.status_var.set(f"Imagem do Jogador {player} removida.")

    def save(self) -> AppConfig | None:
        try:
            self.config = self._read_config(); save_config(self.config); self.auth.update_config(self.config)
            if self.runtime:
                self.runtime.apply_live_config(self.config); self.runtime.apply_connection_config(self.config)
            self._refresh_obs_url(); self.status_var.set(f"Configurações salvas em {CONFIG_PATH}"); self._refresh_twitch_label(); return self.config
        except Exception as exc: messagebox.showerror("Configuração inválida", str(exc)); return None

    def start(self) -> None:
        config = self.save()
        if not config: return
        if self.runtime: self.open_panel(); return
        has_auto = bool(config.twitch_access_token or config.twitch_refresh_token)
        has_manual = bool(config.twitch_manual_mode and config.twitch_channel and config.twitch_token)
        if not has_auto and not has_manual:
            self._start_after_login = True; self.status_var.set("Primeiro acesso: conecte sua Twitch."); self.login_twitch(); return
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
                manager = TTSManager(config); path = manager.synthesize("Olá! Este é o teste de voz do ChatDeusApp.", config.default_voice_1, "cheerful")
                if not path: raise RuntimeError("Não foi possível gerar áudio.")
                AudioWorker._play(path); path.unlink(missing_ok=True)
                self.root.after(0, lambda: self.status_var.set("Teste de voz concluído."))
            except Exception as exc:
                log.exception("Falha no teste de voz."); self.root.after(0, lambda: messagebox.showerror("Teste de voz", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _poll_runtime_status(self) -> None:
        if self.runtime and not self.auth.pending:
            status = self.runtime.twitch.public_status()
            if status.get("ready"):
                login = status.get("login") or self.config.twitch_login; channel = status.get("channel") or login
                if login: self.twitch_status_var.set(f"Twitch: @{login} conectado ao chat @{channel} ✓")
            elif status.get("error"): self.twitch_status_var.set(f"Twitch: {status['error']}")
        try: self.root.after(1200, self._poll_runtime_status)
        except tk.TclError: pass

    def _poll_logs(self) -> None:
        changed = False
        while True:
            try: line = self.log_queue.get_nowait()
            except queue.Empty: break
            self.logs.configure(state="normal"); self.logs.insert("end", line + "\n"); self.logs.see("end"); self.logs.configure(state="disabled"); changed = True
        try: self.root.after(200 if changed else 400, self._poll_logs)
        except tk.TclError: pass

    def run(self) -> None: self.root.mainloop()


def run_desktop() -> None:
    DesktopApp().run()
