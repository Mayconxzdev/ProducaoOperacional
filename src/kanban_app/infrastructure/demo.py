from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from kanban_app.application.dto import OpFormDTO
from kanban_app.domain.enums import OpStatus
from kanban_app.infrastructure.config import AppConfig, OpDiscoveryConfig, SmtpConfig
from kanban_app.infrastructure.db.repositories import ProductionRepository
from kanban_app.presentation.tv_settings import default_tv_settings


DEMO_SEED_VERSION = 2
DEMO_FOLDER_NAME = "Demonstracao"


@dataclass(frozen=True, slots=True)
class DemoPaths:
    root: Path

    @property
    def database_path(self) -> Path:
        return self.root / "data" / "demonstracao.db"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def imports_dir(self) -> Path:
        return self.root / "imports"

    @property
    def runtime_dir(self) -> Path:
        return self.root / "runtime"


def demo_paths(root: Path | None = None) -> DemoPaths:
    if root is None:
        app_root = Path(
            os.environ.get("KANBAN_LOCAL_APP_DIR")
            or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ProducaoOperacional"
        )
        root = app_root / DEMO_FOLDER_NAME
    return DemoPaths(Path(root).resolve())


def demo_config(paths: DemoPaths) -> AppConfig:
    """Configuração deliberadamente local: o demo não conhece o NAS real."""

    return AppConfig(
        config_path=paths.root / "settings.demo.json",
        nas_root=paths.root,
        database_path=paths.database_path,
        backups_dir=paths.backups_dir,
        state_dir=paths.state_dir,
        imports_dir=paths.imports_dir,
        theme_mode="system",
        smtp=SmtpConfig(enabled=False),
        op_discovery=OpDiscoveryConfig(enabled=False),
    )


def seed_demo_data(repository: ProductionRepository, *, station_id: str) -> None:
    """Cria uma base didática previsível, mas visualmente útil para a TV/Foco."""

    current_seed_version = repository.get_setting("demo.seed_version", None)
    if current_seed_version == DEMO_SEED_VERSION:
        return

    # Uma atualização do modo demonstração não altera as OPs que a pessoa já
    # praticou. Atualiza apenas o preset visual para que a TV preserve os
    # textos completos em uma tela Full HD.
    if current_seed_version is not None:
        repository.set_settings(_demo_tv_settings(), station_id=station_id)
        return

    sectors = {sector.nome: sector.id for sector in repository.list_sectors(active_only=True)}
    today = date.today()
    samples = (
        ("91001", "Cliente Demonstração Alfa", "Ventilador Industrial AX-450", 8, "220/380", "Projeto", -8, -2, OpStatus.EM_ATRASO, "Revisar desenho técnico antes da liberação."),
        ("91002", "Cliente Demonstração Beta", "Exaustor Linha Compacta", 12, "220", "Serralheria", -6, 1, OpStatus.PRIORIDADE, "Material principal separado para corte."),
        ("91003", "Cliente Demonstração Gama", "Coletor de Pó Série D", 4, "440", "Montagem", -5, 5, OpStatus.EM_DIA, "Aguardando conferência do conjunto motor."),
        ("91004", "Cliente Demonstração Delta", "Cabine de Pintura Mini", 2, "220/380", "Bicromatização", -4, 8, OpStatus.AGUARDANDO, "Fornecedor confirmou coleta para amanhã."),
        ("91005", "Cliente Demonstração Épsilon", "Ventilador Centrífugo CF-700", 6, "380", "Pintura", -3, 10, OpStatus.EM_DIA, "Aplicar acabamento padrão azul."),
        ("91006", "Cliente Demonstração Zeta", "Sistema de Exaustão Modular", 1, "440", "Testes", -2, 12, OpStatus.PRIORIDADE, "Validar ruído e vazão na bancada."),
        ("91007", "Cliente Demonstração Eta", "Filtro de Manga FM-12", 3, "220", "Qualidade", -1, 14, OpStatus.EM_DIA, "Checklist de inspeção inicial preenchido."),
        ("91008", "Cliente Demonstração Teta", "Lavador de Gases LG-90", 2, "220/380", "Expedição", 0, 16, OpStatus.AGUARDANDO, "Definir transportadora de demonstração."),
        ("91009", "Cliente Demonstração Iota", "Ventilador de Telhado VT-300", 10, "220", "Montagem", 1, 21, OpStatus.EM_DIA, "Produção liberada para montagem."),
        ("91010", "Cliente Demonstração Kappa", "Exaustor Axial AX-800", 5, "380", "Testes", 2, 30, OpStatus.EM_DIA, "Agendar teste de desempenho."),
    )
    for number, client, model, quantity, voltage, sector, start_offset, delivery_offset, status, pending in samples:
        repository.create_op(
            OpFormDTO(
                numero_op=number,
                cliente=client,
                modelo=model,
                quantidade=quantity,
                voltagem=voltage,
                data_inicio=today + timedelta(days=start_offset),
                data_entrega=today + timedelta(days=delivery_offset),
                setor_id=sectors[sector],
                status=status,
                pendencia=pending,
            ),
            station_id=station_id,
        )
    repository.set_settings(_demo_tv_settings(), station_id=station_id)


def _demo_tv_settings() -> dict[str, object]:
    """Preset de demonstração: mostra as 10 OPs sem reduzir a leitura."""

    settings = default_tv_settings()
    settings.update({"lines_per_page": 10, "page_interval_seconds": 8})
    return {"demo.seed_version": DEMO_SEED_VERSION, **{f"tv.{key}": value for key, value in settings.items()}}


def reset_demo_storage(paths: DemoPaths) -> None:
    """Remove somente artefatos sob a raiz exclusiva de demonstração."""

    for path in (paths.database_path, *paths.database_path.parent.glob(f"{paths.database_path.name}-*")):
        path.unlink(missing_ok=True)
    for directory in (paths.backups_dir, paths.state_dir, paths.imports_dir, paths.runtime_dir):
        if directory.exists():
            shutil.rmtree(directory)
