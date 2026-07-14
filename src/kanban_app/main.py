from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from kanban_app.application.dto import StationRoleDTO
from kanban_app.bootstrap import AppContainer
from kanban_app.presentation.main_window import MainWindow
from kanban_app.presentation.theme import apply_theme
from kanban_app.infrastructure.demo import demo_paths
from kanban_app.infrastructure.logging_setup import configure_logging
from kanban_app.infrastructure.services.station_runtime import StationRuntimeStore


def _config_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "settings.json"
    return Path(__file__).resolve().parents[2] / "config" / "settings.json"


def _application_icon_path() -> Path:
    """Resolve o ícone distribuído tanto no código-fonte quanto no executável."""

    if getattr(sys, "frozen", False):
        # No PyInstaller em modo one-dir, arquivos adicionados ficam em
        # sys._MEIPASS (normalmente _internal), não ao lado do .exe.
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return bundle_root / "assets" / "producao_operacional.png"
    return Path(__file__).resolve().parents[2] / "assets" / "producao_operacional.png"


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Produção Operacional")
    parser.add_argument("--config")
    parser.add_argument("--configure-role", choices=("office", "tv", "demo"))
    parser.add_argument("--demo", action="store_true", help="Abre uma base local fictícia, isolada do NAS.")
    parser.add_argument("--tv-kiosk", action="store_true")
    parser.add_argument("--tv-windowed", action="store_true")
    parser.add_argument("--monitor", default="")
    return parser.parse_args(argv)



def _screen_for_name(name: str):
    screens = QGuiApplication.screens()
    if not screens:
        return None
    requested = str(name or "").strip().casefold()
    if requested:
        exact = next((screen for screen in screens if screen.name().casefold() == requested), None)
        if exact is not None:
            return exact
        partial = next((screen for screen in screens if requested in screen.name().casefold()), None)
        if partial is not None:
            return partial
    return QGuiApplication.primaryScreen() or screens[0]


def _uses_demo_mode(args: argparse.Namespace, launcher_role: StationRoleDTO) -> bool:
    """O perfil configurado pelo setup também deve iniciar o demo sem parâmetro."""

    return bool(
        args.demo
        or args.configure_role == "demo"
        or (not args.configure_role and launcher_role.role == "demo")
    )

def run() -> int:
    args = _arguments(sys.argv[1:])
    # O perfil é mantido fora da base do demo para que o atalho normal saiba
    # iniciar a demonstração depois que ela for escolhida no instalador.
    launcher_runtime = StationRuntimeStore()
    launcher_role = launcher_runtime.load_role()
    demo_mode = _uses_demo_mode(args, launcher_role)
    configure_logging(demo_paths().root / "logs" if demo_mode else None)
    container = AppContainer.create_demo() if demo_mode else AppContainer.create(_config_path(args.config))
    if args.configure_role:
        configured_role = StationRoleDTO(
            role=args.configure_role,
            fullscreen=args.configure_role == "tv" and not args.tv_windowed,
            monitor_name=str(args.monitor or ""),
            start_with_windows=args.configure_role == "tv",
        )
        launcher_runtime.save_role(configured_role)
        # O runtime isolado também conserva o perfil, porém a decisão de
        # abertura sempre parte do launcher local acima.
        if container.runtime_store.root != launcher_runtime.root:
            container.runtime_store.save_role(configured_role)
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("Produção Operacional — Demonstração" if demo_mode else "Produção Operacional")
    app.setWindowIcon(QIcon(str(_application_icon_path())))
    apply_theme(app, container.runtime_store.load_theme_mode(container.config.theme_mode))
    role = launcher_runtime.load_role()
    window = MainWindow(container)
    # O demo sempre inicia na tela de Escritório, mesmo numa estação configurada
    # como TV/Foco; a TV pode ser aberta pelo botão da própria demonstração.
    tv_mode = bool(args.tv_kiosk) or (not demo_mode and role.role == "tv")
    if tv_mode:
        screen = _screen_for_name(args.monitor or role.monitor_name)
        fullscreen = not args.tv_windowed and (bool(args.tv_kiosk) or role.fullscreen)
        window._open_tv(fullscreen=fullscreen, screen=screen)
        window.hide()
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
