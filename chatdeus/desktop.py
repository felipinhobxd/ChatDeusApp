from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

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
from .twitch_auth import TwitchAuthError, TwitchAuthManager

log = logging.getLogger(__name__)

IDLE_CHOICES = [("none", "Parado"), ("float", "Flutuar"), ("breathe", "Respirar")]
SPEAK_CHOICES = [
    ("auto", "Automático por emoção"),
    ("bounce", "Pular"),
    ("shake", "Balançar"),
    ("pulse", "Pulsar"),
    ("talk", "Falar"),
    ("none", "Sem animação"),
]


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
        self.root.geometry("920x790")
        self.root.minsize(840, 700)
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
        self._poll_logs()
        self._poll_runtime_status()

        if self.auth.has_managed_credentials:
            threading.Thread(target=self._validate_saved_twitch, daemon=True).start()

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
        ttk.Label(
            wrapper,
            text="Conecte a Twitch com um clique, configure vozes, personagens animados e OBS.",
        ).pack(anchor="w", pady=(0, 12))

        notebook = ttk.Notebook(wrapper)
        notebook.pack(fill="both", expand=True)
        self.tab_connections = ttk.Frame(notebook, padding=14)
        self.tab_app = ttk.Frame(notebook, padding=14)
        self.tab_characters = ttk.Frame(notebook, padding=14)
        self.tab_logs = ttk.Frame(notebook, padding=14)
        notebook.add(self.tab_connections, text="Conexões")
        notebook.add(self.tab_app, text="Aplicativo")
        notebook.add(self.tab_characters, text="Personagens")
        notebook.add(self.tab_logs, text="Status")

        self._build_connections_tab()
        self._build_app_tab()
        self._build_characters_tab()
        self._build_logs_tab()

        actions = ttk.Frame(wrapper)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Salvar configurações", command=self.save).pack(side="left")
        self.start_btn = ttk.Button(actions, text="Iniciar ChatDeusApp", command=self.start)
        self.start_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(actions, text="Abrir painel", command=self.open_panel, state="disabled")
        self.open_btn.pack(side="left")
        ttk.Button(actions, text="Testar voz", command=self.test_voice).pack(side="right")

        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(wrapper, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def _field_grid(
        self,
        parent,
        row: int,
        label: str,
        key: str,
        *,
        show: str | None = None,
        width: int = 48,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
        var = tk.StringVar()
        self.vars[key] = var
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _build_connections_tab(self) -> None:
        tab = self.tab_connections

        twitch = ttk.LabelFrame(tab, text="Twitch", padding=12)
        twitch.pack(fill="x", pady=(0, 10))
        twitch.columnconfigure(0, weight=1)

        self.twitch_status_var = tk.StringVar(value="Twitch: verificando...")
        ttk.Label(twitch, textvariable=self.twitch_status_var, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        ttk.Label(
            twitch,
            text="Recomendado: clique em Entrar com Twitch. O navegador abre, você autoriza e o canal/token são configurados automaticamente.",
            wraplength=790,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 9))

        self.login_btn = ttk.Button(twitch, text="Entrar com Twitch", command=self.login_twitch)
        self.login_btn.grid(row=2, column=0, sticky="w")
        self.disconnect_btn = ttk.Button(twitch, text="Desconectar", command=self.disconnect_twitch)
        self.disconnect_btn.grid(row=2, column=1, sticky="w", padx=8)
        self.open_auth_btn = ttk.Button(twitch, text="Abrir autorização", command=self.open_twitch_authorization, state="disabled")
        self.open_auth_btn.grid(row=2, column=2, sticky="w")

        self.twitch_code_var = tk.StringVar(value="")
        ttk.Label(twitch, textvariable=self.twitch_code_var).grid(row=3, column=0, columnspan=4, sticky="w", pady=(7, 0))

        manual = ttk.LabelFrame(twitch, text="Compatibilidade / modo manual (opcional)", padding=8)
        manual.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        manual.columnconfigure(1, weight=1)
        self.vars["twitch_manual_mode"] = tk.BooleanVar()
        ttk.Checkbutton(
            manual,
            text="Usar canal + OAuth token manual das versões antigas",
            variable=self.vars["twitch_manual_mode"],
            command=self._set_manual_state,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        self._manual_entries.append(self._field_grid(manual, 1, "Canal", "twitch_channel"))
        self._manual_entries.append(self._field_grid(manual, 2, "Token OAuth", "twitch_token", show="•"))

        azure = ttk.LabelFrame(tab, text="Microsoft Azure TTS", padding=12)
        azure.pack(fill="x", pady=(0, 10))
        azure.columnconfigure(1, weight=1)
        self.vars["azure_enabled"] = tk.BooleanVar()
        ttk.Checkbutton(azure, text="Usar Azure TTS quando configurado", variable=self.vars["azure_enabled"]).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=2
        )
        self._field_grid(azure, 1, "Chave", "azure_key", show="•")
        self._field_grid(azure, 2, "Região (ex.: brazilsouth)", "azure_region")
        self.vars["fallback_gtts"] = tk.BooleanVar()
        ttk.Checkbutton(azure, text="Usar voz gratuita (gTTS) se Azure falhar", variable=self.vars["fallback_gtts"]).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=2
        )

        obs = ttk.LabelFrame(tab, text="OBS WebSocket — opcional", padding=12)
        obs.pack(fill="x")
        obs.columnconfigure(1, weight=1)
        self.vars["obs_enabled"] = tk.BooleanVar()
        ttk.Checkbutton(obs, text="Ativar integração avançada com OBS", variable=self.vars["obs_enabled"]).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=2
        )
        self._field_grid(obs, 1, "Host", "obs_host")
        self._field_grid(obs, 2, "Porta", "obs_port")
        self._field_grid(obs, 3, "Senha", "obs_password", show="•")
        self._field_grid(obs, 4, "Fonte de áudio", "obs_source")
        self._field_grid(obs, 5, "Filtro Jogador 1", "obs_filter_1")
        self._field_grid(obs, 6, "Filtro Jogador 2", "obs_filter_2")
        self._field_grid(obs, 7, "Filtro Jogador 3", "obs_filter_3")

    def _build_app_tab(self) -> None:
        tab = self.tab_app
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Comandos do chat", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self._field_grid(tab, 1, "Jogador 1", "command_player_1")
        self._field_grid(tab, 2, "Jogador 2", "command_player_2")
        self._field_grid(tab, 3, "Jogador 3", "command_player_3")
        ttk.Separator(tab).grid(row=4, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(tab, text="Servidor local / Fonte de Navegador do OBS", font=("Segoe UI", 12, "bold")).grid(
            row=5, column=0, columnspan=2, sticky="w"
        )
        self._field_grid(tab, 6, "Host", "web_host")
        self._field_grid(tab, 7, "Porta", "web_port")
        self.vars["open_panel_on_start"] = tk.BooleanVar()
        ttk.Checkbutton(
            tab,
            text="Abrir painel automaticamente ao iniciar",
            variable=self.vars["open_panel_on_start"],
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(
            tab,
            text="No OBS, adicione uma única Fonte de Navegador usando /overlay. Personagens e animações funcionam mesmo sem OBS WebSocket.",
            wraplength=700,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_characters_tab(self) -> None:
        tab = self.tab_characters
        ttk.Label(tab, text="Personagens do overlay", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            tab,
            text="Escolha PNG/JPG/WebP/GIF. A imagem é copiada para o ChatDeusApp e aparece automaticamente na Fonte de Navegador do OBS.",
            wraplength=780,
        ).pack(anchor="w", pady=(0, 10))

        for player in (1, 2, 3):
            box = ttk.LabelFrame(tab, text=f"Jogador {player}", padding=10)
            box.pack(fill="x", pady=5)
            box.columnconfigure(1, weight=1)

            image_key = f"character_image_{player}"
            self.vars[image_key] = tk.StringVar()
            ttk.Label(box, text="Imagem").grid(row=0, column=0, sticky="w", padx=(0, 8))
            ttk.Entry(box, textvariable=self.vars[image_key], state="readonly").grid(
                row=0, column=1, columnspan=4, sticky="ew"
            )
            ttk.Button(box, text="Escolher...", command=lambda p=player: self.choose_character(p)).grid(
                row=0, column=5, padx=(8, 4)
            )
            ttk.Button(box, text="Remover", command=lambda p=player: self.remove_character(p)).grid(row=0, column=6)

            numeric = [
                ("Tamanho px", "size"),
                ("Intensidade 0-10", "intensity"),
                ("X px", "x"),
                ("Y px", "y"),
            ]
            for col, (label, suffix) in enumerate(numeric):
                key = f"character_{suffix}_{player}"
                self.vars[key] = tk.StringVar()
                ttk.Label(box, text=label).grid(row=1, column=col * 2, sticky="w", pady=(8, 0), padx=(0, 4))
                ttk.Entry(box, textvariable=self.vars[key], width=8).grid(
                    row=1, column=col * 2 + 1, sticky="w", pady=(8, 0), padx=(0, 10)
                )

            idle_key = f"character_idle_{player}"
            speak_key = f"character_speaking_{player}"
            mirror_key = f"character_mirror_{player}"
            self.vars[idle_key] = tk.StringVar()
            self.vars[speak_key] = tk.StringVar()
            self.vars[mirror_key] = tk.BooleanVar()
            ttk.Label(box, text="Parado").grid(row=2, column=0, sticky="w", pady=(8, 0))
            ttk.Combobox(
                box,
                textvariable=self.vars[idle_key],
                values=[value for value, _ in IDLE_CHOICES],
                state="readonly",
                width=12,
            ).grid(row=2, column=1, sticky="w", pady=(8, 0))
            ttk.Label(box, text="Falando").grid(row=2, column=2, sticky="w", pady=(8, 0))
            ttk.Combobox(
                box,
                textvariable=self.vars[speak_key],
                values=[value for value, _ in SPEAK_CHOICES],
                state="readonly",
                width=18,
            ).grid(row=2, column=3, sticky="w", pady=(8, 0))
            ttk.Checkbutton(box, text="Espelhar", variable=self.vars[mirror_key]).grid(
                row=2, column=4, columnspan=2, sticky="w", pady=(8, 0)
            )

        ttk.Label(
            tab,
            text="Dica: deixe 'Falando = auto'. O movimento muda conforme (bravo), (animado), (sussurro), etc.",
        ).pack(anchor="w", pady=(8, 0))

    def _build_logs_tab(self) -> None:
        self.logs = tk.Text(self.tab_logs, wrap="word", state="disabled", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(self.tab_logs, orient="vertical", command=self.logs.yview)
        self.logs.configure(yscrollcommand=scrollbar.set)
        self.logs.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _fill_from_config(self) -> None:
        for key, var in self.vars.items():
            if hasattr(self.config, key):
                var.set(getattr(self.config, key))

    def _read_config(self) -> AppConfig:
        base = load_config()
        for key, var in self.vars.items():
            if not hasattr(base, key):
                continue
            value = var.get()
            current = getattr(base, key)
            if isinstance(current, bool):
                value = bool(value)
            elif isinstance(current, int):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise ValueError(f"O campo {key} precisa ser numérico.")
            setattr(base, key, value)
        return base.normalized()

    def _set_manual_state(self) -> None:
        enabled = bool(self.vars.get("twitch_manual_mode", tk.BooleanVar(value=False)).get())
        state = "normal" if enabled else "disabled"
        for entry in self._manual_entries:
            entry.configure(state=state)

    def _refresh_twitch_label(self) -> None:
        if self.auth.pending:
            self.twitch_status_var.set("Twitch: aguardando autorização no navegador...")
            return
        if self.config.twitch_access_token and self.config.twitch_login:
            self.twitch_status_var.set(f"Twitch: conectado como @{self.config.twitch_login} ✓")
            self.disconnect_btn.configure(state="normal")
        elif self.config.twitch_manual_mode and self.config.twitch_channel and self.config.twitch_token:
            self.twitch_status_var.set(f"Twitch: modo manual configurado para @{self.config.twitch_channel}")
            self.disconnect_btn.configure(state="disabled")
        else:
            self.twitch_status_var.set("Twitch: não conectado")
            self.disconnect_btn.configure(state="disabled")

    def login_twitch(self) -> None:
        self.vars["twitch_manual_mode"].set(False)
        self._set_manual_state()
        config = self.save()
        if not config:
            return
        self.auth.update_config(config)
        if not self.auth.begin_device_login():
            self.status_var.set("O login da Twitch já está em andamento.")
            return
        self.login_btn.configure(state="disabled")
        self.status_var.set("Abrindo a Twitch no navegador...")

    def open_twitch_authorization(self) -> None:
        url = self.auth.verification_uri
        if url:
            webbrowser.open(url)

    def disconnect_twitch(self) -> None:
        if not messagebox.askyesno("Desconectar Twitch", "Deseja remover a conta Twitch conectada deste computador?"):
            return
        self.status_var.set("Desconectando Twitch...")
        threading.Thread(target=self.auth.disconnect, daemon=True).start()

    def _auth_status_from_thread(self, status: dict) -> None:
        try:
            self.root.after(0, lambda s=dict(status): self._apply_auth_status(s))
        except tk.TclError:
            pass

    def _apply_auth_status(self, status: dict) -> None:
        state = status.get("state", "")
        if state == "requesting":
            self.twitch_status_var.set("Twitch: iniciando login...")
            self.twitch_code_var.set("")
        elif state == "waiting":
            code = status.get("user_code", "")
            self.twitch_status_var.set("Twitch: autorize sua conta no navegador")
            self.twitch_code_var.set(f"Código: {code}" if code else "Autorize na página aberta da Twitch.")
            self.open_auth_btn.configure(state="normal")
        elif state == "connected":
            self.config = load_config()
            self.auth.update_config(self.config)
            self.vars["twitch_manual_mode"].set(False)
            self.vars["twitch_channel"].set(self.config.twitch_channel)
            self.twitch_status_var.set(f"Twitch: conectado como @{self.config.twitch_login} ✓")
            self.twitch_code_var.set("")
            self.login_btn.configure(state="normal")
            self.disconnect_btn.configure(state="normal")
            self.open_auth_btn.configure(state="disabled")
            self.status_var.set("Twitch conectada. O canal foi configurado automaticamente.")
            if self.runtime:
                self.runtime.apply_connection_config(self.config)
            if self._start_after_login:
                self._start_after_login = False
                self.root.after(100, self.start)
        elif state == "disconnected":
            self.config = load_config()
            self.auth.update_config(self.config)
            self.twitch_status_var.set("Twitch: não conectado")
            self.twitch_code_var.set("")
            self.login_btn.configure(state="normal")
            self.disconnect_btn.configure(state="disabled")
            self.open_auth_btn.configure(state="disabled")
            self.status_var.set("Twitch desconectada deste computador.")
            if self.runtime:
                self.runtime.apply_connection_config(self.config)
        elif state == "error":
            self.login_btn.configure(state="normal")
            self.open_auth_btn.configure(state="disabled")
            self.twitch_code_var.set("")
            error = status.get("error", "Falha no login.")
            self.twitch_status_var.set("Twitch: não conectado")
            self.status_var.set(f"Twitch: {error}")
            self._start_after_login = False

    def _validate_saved_twitch(self) -> None:
        try:
            session = self.auth.ensure_valid()
            if session:
                self._auth_status_from_thread({"state": "connected", "login": session.login})
        except TwitchAuthError as exc:
            self._auth_status_from_thread({"state": "error", "error": str(exc)})
        except Exception as exc:
            log.warning("Não foi possível validar a sessão Twitch salva: %s", exc)

    def choose_character(self, player: int) -> None:
        path = filedialog.askopenfilename(
            title=f"Escolher imagem do Jogador {player}",
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.gif"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        try:
            filename = install_character_image(player, path)
            self.vars[f"character_image_{player}"].set(filename)
            self.save()
            self.status_var.set(f"Imagem do Jogador {player} salva em {CHARACTER_DIR}")
        except Exception as exc:
            messagebox.showerror("Imagem inválida", str(exc))

    def remove_character(self, player: int) -> None:
        remove_character_image(player)
        self.vars[f"character_image_{player}"].set("")
        self.save()
        self.status_var.set(f"Imagem do Jogador {player} removida.")

    def save(self) -> AppConfig | None:
        try:
            self.config = self._read_config()
            save_config(self.config)
            self.auth.update_config(self.config)
            if self.runtime:
                self.runtime.apply_visual_config(self.config)
                self.runtime.apply_connection_config(self.config)
            self.status_var.set(f"Configurações salvas em {CONFIG_PATH}")
            self._refresh_twitch_label()
            return self.config
        except Exception as exc:
            messagebox.showerror("Configuração inválida", str(exc))
            return None

    def start(self) -> None:
        config = self.save()
        if not config:
            return
        if self.runtime:
            self.open_panel()
            return

        has_auto = bool(config.twitch_access_token or config.twitch_refresh_token)
        has_manual = bool(config.twitch_manual_mode and config.twitch_channel and config.twitch_token)
        if not has_auto and not has_manual:
            self._start_after_login = True
            self.status_var.set("Primeiro acesso: conecte sua Twitch. O navegador será aberto automaticamente.")
            self.login_twitch()
            return

        try:
            self.runtime = Runtime(config)
            self.runtime.start()
            self.start_btn.configure(state="disabled")
            self.open_btn.configure(state="normal")
            self.status_var.set(f"Executando em {self.runtime.base_url}")
            log.info("ChatDeusApp iniciado em %s", self.runtime.base_url)
            if config.open_panel_on_start:
                self.root.after(800, self.open_panel)
        except Exception as exc:
            self.runtime = None
            messagebox.showerror("Erro ao iniciar", str(exc))
            log.exception("Falha ao iniciar ChatDeusApp.")

    def open_panel(self) -> None:
        if self.runtime:
            self.runtime.open_panel()
        else:
            messagebox.showinfo("ChatDeusApp", "Inicie o aplicativo primeiro.")

    def test_voice(self) -> None:
        config = self.save()
        if not config:
            return

        def work():
            try:
                manager = TTSManager(config)
                path = manager.synthesize(
                    "Olá! O ChatDeusApp está configurado e pronto para falar em português.",
                    config.default_voice_1,
                    "default",
                )
                if not path:
                    raise RuntimeError("Não foi possível gerar áudio. Confira Azure ou habilite o fallback gTTS.")
                from .audio import AudioWorker

                AudioWorker._play(path)
                self.root.after(0, lambda: self.status_var.set("Teste de voz concluído."))
            except Exception as exc:
                log.exception("Falha no teste de voz.")
                self.root.after(0, lambda: messagebox.showerror("Teste de voz", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _poll_runtime_status(self) -> None:
        if self.runtime and not self.auth.pending:
            status = self.runtime.twitch.public_status()
            if status.get("ready"):
                login = status.get("login") or self.config.twitch_login
                channel = status.get("channel") or login
                if login:
                    self.twitch_status_var.set(f"Twitch: @{login} conectado ao chat @{channel} ✓")
            elif status.get("error"):
                self.twitch_status_var.set(f"Twitch: {status['error']}")
        try:
            self.root.after(1200, self._poll_runtime_status)
        except tk.TclError:
            pass

    def _poll_logs(self) -> None:
        changed = False
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.logs.configure(state="normal")
            self.logs.insert("end", line + "\n")
            self.logs.see("end")
            self.logs.configure(state="disabled")
            changed = True
        try:
            self.root.after(200 if changed else 400, self._poll_logs)
        except tk.TclError:
            pass

    def run(self) -> None:
        self.root.mainloop()


def run_desktop() -> None:
    DesktopApp().run()
