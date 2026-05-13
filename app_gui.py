from __future__ import annotations

import logging
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import requests

import config
from nfse_automacao import executar
from runtime_settings import get_email_to, get_pasta_certs, save_runtime_settings
from scheduler import SchedulerService

# ── Paleta ────────────────────────────────────────────────────────────────────
CLR = {
    "bg":        "#F4F6F8",
    "header_bg": "#1A2740",
    "header_fg": "#FFFFFF",
    "card":      "#FFFFFF",
    "border":    "#DDE1E7",
    "primary":   "#2563EB",
    "success":   "#16A34A",
    "danger":    "#DC2626",
    "warning":   "#D97706",
    "muted":     "#6B7280",
    "log_bg":    "#0F1923",
    "log_fg":    "#C9D1D9",
    "log_info":  "#58A6FF",
    "log_ok":    "#3FB950",
    "log_err":   "#F85149",
    "log_warn":  "#D29922",
    "log_ts":    "#8B949E",
}


class _QueueLogHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.log_queue.put((record.levelno, self.format(record)))
        except Exception:
            self.handleError(record)


class NFSeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("NFSe Automação")
        self.root.geometry("860x620")
        self.root.minsize(760, 540)
        self.root.configure(bg=CLR["bg"])

        self.status_var   = tk.StringVar(value="Serviço parado")
        self.pasta_var    = tk.StringVar(value=get_pasta_certs())
        self.email_var    = tk.StringVar(value=get_email_to())
        self.servidor_var = tk.StringVar(value="Iniciando servidor...")
        self.ngrok_var    = tk.StringVar(value="Iniciando ngrok...")

        self.service: SchedulerService | None = None
        self.log_queue: queue.Queue[tuple[int, str]] = queue.Queue()
        self._log_handler: _QueueLogHandler | None = None
        self._ngrok_proc: subprocess.Popen | None = None

        self._build_ui()
        self._attach_log_handler()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(200, self._flush_logs)
        threading.Thread(target=self._iniciar_infraestrutura, daemon=True).start()

    # ── Log handler ───────────────────────────────────────────────────────────

    def _attach_log_handler(self) -> None:
        handler = _QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(levelname)-8s  %(message)s"))
        self._log_handler = handler
        for nome_logger in ("nfse", "api_server", "cert_manager", "nfse_browser"):
            lg = logging.getLogger(nome_logger)
            lg.addHandler(handler)
            lg.setLevel(logging.DEBUG)

    def _detach_log_handler(self) -> None:
        if self._log_handler:
            for nome_logger in ("nfse", "api_server", "cert_manager", "nfse_browser"):
                logging.getLogger(nome_logger).removeHandler(self._log_handler)
            self._log_handler = None

    # ── Interface ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Header
        header = tk.Frame(self.root, bg=CLR["header_bg"], height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="  NFSe Automação",
            font=("Segoe UI", 15, "bold"),
            bg=CLR["header_bg"],
            fg=CLR["header_fg"],
        ).pack(side="left", padx=16, pady=14)

        self._srv_dot = tk.Label(
            header, text="●", font=("Segoe UI", 12),
            bg=CLR["header_bg"], fg=CLR["warning"],
        )
        self._srv_dot.pack(side="right", padx=(0, 8))
        tk.Label(
            header, textvariable=self.ngrok_var,
            font=("Segoe UI", 8), bg=CLR["header_bg"], fg="#94A3B8",
        ).pack(side="right", padx=(0, 4))

        # Corpo
        body = tk.Frame(self.root, bg=CLR["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=14)

        # ── Linha superior: Certificados | E-mail ─────────────────────────
        top = tk.Frame(body, bg=CLR["bg"])
        top.pack(fill="x", pady=(0, 10))
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)

        self._card_field(
            top, "Pasta dos certificados (.pfx)", self.pasta_var,
            btn_text="Escolher", btn_cmd=self.escolher_pasta,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._card_field(
            top, "E-mail de destino", self.email_var,
            btn_text="Salvar", btn_cmd=self.salvar_email,
        ).grid(row=0, column=1, sticky="ew")

        # ── Painel de status ──────────────────────────────────────────────
        status_card = self._card(body)
        status_card.pack(fill="x", pady=(0, 10))

        left_status = tk.Frame(status_card, bg=CLR["card"])
        left_status.pack(side="left", fill="x", expand=True)

        horario = (
            f"Agendamento mensal: dia {config.SCHEDULE_DAY} "
            f"às {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MIN:02d}"
        )
        tk.Label(
            left_status, text=horario,
            font=("Segoe UI", 9), bg=CLR["card"], fg=CLR["muted"],
        ).pack(anchor="w")

        self.status_label = tk.Label(
            left_status, textvariable=self.status_var,
            font=("Segoe UI", 10, "bold"), bg=CLR["card"], fg=CLR["danger"],
        )
        self.status_label.pack(anchor="w", pady=(2, 0))

        tk.Label(
            left_status, textvariable=self.servidor_var,
            font=("Segoe UI", 8), bg=CLR["card"], fg=CLR["muted"],
        ).pack(anchor="w")

        # ── Botões ────────────────────────────────────────────────────────
        btn_frame = tk.Frame(body, bg=CLR["bg"])
        btn_frame.pack(fill="x", pady=(0, 10))

        self.btn_iniciar = self._btn(
            btn_frame, "▶  Iniciar", self.iniciar, CLR["primary"]
        )
        self.btn_iniciar.pack(side="left")

        self.btn_finalizar = self._btn(
            btn_frame, "■  Parar", self.finalizar, CLR["muted"]
        )
        self.btn_finalizar.pack(side="left", padx=(8, 0))
        self.btn_finalizar.config(state="disabled")

        self.btn_executar = self._btn(
            btn_frame, "⚡  Executar agora", self.executar_agora, CLR["success"]
        )
        self.btn_executar.pack(side="left", padx=(8, 0))

        self._btn(
            btn_frame, "Copiar log", self.copiar_log, CLR["muted"], small=True
        ).pack(side="right", padx=(0, 6))

        self._btn(
            btn_frame, "Limpar log", self.limpar_log, CLR["muted"], small=True
        ).pack(side="right")

        # ── Log ───────────────────────────────────────────────────────────
        tk.Label(
            body, text="Log da aplicação",
            font=("Segoe UI", 9, "bold"), bg=CLR["bg"], fg=CLR["muted"],
        ).pack(anchor="w")

        log_outer = tk.Frame(body, bg=CLR["log_bg"], bd=0, relief="flat")
        log_outer.pack(fill="both", expand=True, pady=(4, 0))

        scrollbar = ttk.Scrollbar(log_outer, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.log_widget = tk.Text(
            log_outer,
            state="disabled",
            yscrollcommand=scrollbar.set,
            wrap="word",
            font=("Consolas", 9),
            bg=CLR["log_bg"],
            fg=CLR["log_fg"],
            bd=0,
            padx=10,
            pady=8,
            insertbackground=CLR["log_fg"],
            selectbackground="#264F78",
        )
        self.log_widget.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_widget.yview)

        self.log_widget.tag_config("ts",   foreground=CLR["log_ts"])
        self.log_widget.tag_config("info", foreground=CLR["log_info"])
        self.log_widget.tag_config("ok",   foreground=CLR["log_ok"])
        self.log_widget.tag_config("err",  foreground=CLR["log_err"])
        self.log_widget.tag_config("warn", foreground=CLR["log_warn"])
        self.log_widget.tag_config("def",  foreground=CLR["log_fg"])

    def _card(self, parent: tk.Frame) -> tk.Frame:
        frame = tk.Frame(
            parent, bg=CLR["card"],
            highlightbackground=CLR["border"], highlightthickness=1,
            padx=12, pady=8,
        )
        return frame

    def _card_field(
        self, parent, label: str, var: tk.StringVar,
        btn_text: str, btn_cmd,
    ) -> tk.Frame:
        card = self._card(parent)
        tk.Label(
            card, text=label,
            font=("Segoe UI", 8), bg=CLR["card"], fg=CLR["muted"],
        ).pack(anchor="w")
        row = tk.Frame(card, bg=CLR["card"])
        row.pack(fill="x", pady=(2, 0))
        tk.Entry(
            row, textvariable=var,
            font=("Segoe UI", 9),
            relief="flat", bd=1,
            highlightbackground=CLR["border"],
            highlightthickness=1,
        ).pack(side="left", fill="x", expand=True, ipady=4)
        self._btn(row, btn_text, btn_cmd, CLR["primary"], small=True).pack(
            side="left", padx=(6, 0)
        )
        return card

    def _btn(
        self, parent, text: str, cmd, color: str, small: bool = False
    ) -> tk.Button:
        pad = (8, 4) if small else (14, 6)
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=color,
            fg="#FFFFFF",
            activebackground=color,
            activeforeground="#FFFFFF",
            relief="flat",
            font=("Segoe UI", 9, "bold") if not small else ("Segoe UI", 8),
            padx=pad[0],
            pady=pad[1],
            cursor="hand2",
            bd=0,
        )

    # ── Infraestrutura ────────────────────────────────────────────────────────

    def _iniciar_infraestrutura(self) -> None:
        # Flask
        try:
            from api_server import app as flask_app
            threading.Thread(
                target=lambda: flask_app.run(
                    host="0.0.0.0", port=5000, debug=False, use_reloader=False
                ),
                daemon=True,
            ).start()
            time.sleep(2)
            self.root.after(0, lambda: self.servidor_var.set("Servidor Flask: porta 5000"))
            self._queue_log(logging.INFO, "Servidor Flask iniciado na porta 5000.")
        except Exception as exc:
            self.root.after(0, lambda: self.servidor_var.set(f"Erro no servidor: {exc}"))
            self._queue_log(logging.ERROR, f"Erro ao iniciar Flask: {exc}")
            return

        # Ngrok
        try:
            base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
            self._ngrok_proc = subprocess.Popen(
                ["ngrok", "http", "5000"],
                cwd=str(base),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(3)
        except FileNotFoundError:
            self.root.after(0, lambda: (
                self.ngrok_var.set("Ngrok não encontrado"),
                self._srv_dot.config(fg=CLR["danger"]),
            ))
            self._queue_log(logging.ERROR, "Ngrok não encontrado. Baixe em ngrok.com/download")
            return

        # URL pública
        url = None
        for _ in range(10):
            try:
                resp = requests.get("http://localhost:4040/api/tunnels", timeout=3)
                for tunnel in resp.json().get("tunnels", []):
                    if tunnel.get("public_url", "").startswith("https://"):
                        url = tunnel["public_url"]
                        break
                if url:
                    break
            except Exception:
                pass
            time.sleep(2)

        if url:
            config.API_URL = url
            self.root.after(0, lambda: (
                self.ngrok_var.set(url),
                self._srv_dot.config(fg=CLR["success"]),
            ))
            self._queue_log(logging.INFO, f"Ngrok ativo: {url}")
            try:
                cfg = Path(__file__).resolve().parent / "config.py"
                if cfg.exists():
                    texto = cfg.read_text(encoding="utf-8")
                    novo = re.sub(r'(API_URL\s*=\s*")[^"]*(")', rf'\g<1>{url}\g<2>', texto)
                    cfg.write_text(novo, encoding="utf-8")
            except Exception:
                pass
        else:
            self.root.after(0, lambda: (
                self.ngrok_var.set("Ngrok: falha ao obter URL"),
                self._srv_dot.config(fg=CLR["danger"]),
            ))
            self._queue_log(logging.WARNING, "Não foi possível obter a URL do ngrok.")

    # ── Ações ─────────────────────────────────────────────────────────────────

    def escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory(
            title="Selecione a pasta dos certificados",
            initialdir=self.pasta_var.get() or str(Path.home()),
        )
        if pasta:
            self.pasta_var.set(pasta)
            self._queue_log(logging.INFO, f"Pasta selecionada: {pasta}")

    def salvar_email(self) -> None:
        email = self.email_var.get().strip()
        if not email or "@" not in email:
            messagebox.showerror("NFSe Automação", "Informe um e-mail válido.")
            return
        save_runtime_settings({"pasta_certs": self.pasta_var.get().strip(), "email_to": email})
        self._queue_log(logging.INFO, f"E-mail salvo: {email}")
        messagebox.showinfo("NFSe Automação", "E-mail salvo com sucesso.")

    def iniciar(self) -> None:
        pasta = self.pasta_var.get().strip()
        if not pasta:
            messagebox.showerror("NFSe Automação", "Selecione a pasta dos certificados.")
            return
        if not Path(pasta).exists():
            messagebox.showerror("NFSe Automação", "A pasta dos certificados não existe.")
            return
        save_runtime_settings({"pasta_certs": pasta, "email_to": self.email_var.get().strip()})
        self.service = SchedulerService(log_callback=lambda m: self._queue_log(logging.INFO, m))
        self.service.start()
        self._set_status("Serviço em execução", CLR["success"])
        self.btn_iniciar.config(state="disabled")
        self.btn_finalizar.config(state="normal")
        self._queue_log(logging.INFO, f"Serviço iniciado | pasta: {pasta}")

    def finalizar(self) -> None:
        if self.service:
            self.service.stop()
            self.service = None
        self._set_status("Serviço parado", CLR["danger"])
        self.btn_iniciar.config(state="normal")
        self.btn_finalizar.config(state="disabled")
        self._queue_log(logging.INFO, "Serviço finalizado.")

    def executar_agora(self) -> None:
        pasta = self.pasta_var.get().strip()
        if not pasta:
            messagebox.showerror("NFSe Automação", "Selecione a pasta dos certificados.")
            return
        if not Path(pasta).exists():
            messagebox.showerror("NFSe Automação", "A pasta dos certificados não existe.")
            return

        self.btn_executar.config(state="disabled")
        self._queue_log(logging.INFO, "Iniciando execução imediata...")

        def _run() -> None:
            try:
                executar(pasta_certs=pasta)
            except Exception as exc:
                self._queue_log(logging.ERROR, f"Erro na execução: {exc}")
            finally:
                self.root.after(0, lambda: self.btn_executar.config(state="normal"))
                self._queue_log(logging.INFO, "Execução concluída.")

        threading.Thread(target=_run, daemon=True).start()

    def copiar_log(self) -> None:
        conteudo = self.log_widget.get("1.0", "end").strip()
        if conteudo:
            self.root.clipboard_clear()
            self.root.clipboard_append(conteudo)
            self._queue_log(logging.INFO, "Log copiado para a área de transferência.")

    def limpar_log(self) -> None:
        self.log_widget.config(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.config(state="disabled")

    def on_close(self) -> None:
        if self.service:
            self.service.stop()
        if self._ngrok_proc:
            self._ngrok_proc.terminate()
        self._detach_log_handler()
        self.root.destroy()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, texto: str, cor: str) -> None:
        self.status_var.set(texto)
        self.status_label.config(fg=cor)

    def _queue_log(self, level: int, message: str) -> None:
        self.log_queue.put((level, message))

    def _flush_logs(self) -> None:
        while not self.log_queue.empty():
            level, msg = self.log_queue.get_nowait()
            self._append_log(level, msg)
        self.root.after(200, self._flush_logs)

    def _append_log(self, level: int, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")

        if level >= logging.ERROR:
            tag = "err"
        elif level >= logging.WARNING:
            tag = "warn"
        elif "ok" in message.lower() or "concluí" in message.lower() or "sucesso" in message.lower():
            tag = "ok"
        elif level >= logging.INFO:
            tag = "info"
        else:
            tag = "def"

        self.log_widget.config(state="normal")
        self.log_widget.insert("end", f"[{ts}]  ", "ts")
        self.log_widget.insert("end", f"{message}\n", tag)
        self.log_widget.see("end")
        self.log_widget.config(state="disabled")


# ── Ponto de entrada ──────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = tk.Tk()
    root.configure(bg=CLR["bg"])

    # Remove borda padrão no Windows para visual mais limpo
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    NFSeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
