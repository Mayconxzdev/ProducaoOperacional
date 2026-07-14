from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kanban_app.application.document_import_service import DocumentImportService
from kanban_app.application.production_service import ProductionService
from kanban_app.infrastructure.config import AppConfig, load_config
from kanban_app.infrastructure.db.repositories import ProductionRepository
from kanban_app.infrastructure.db.session import Database
from kanban_app.infrastructure.demo import DemoPaths, demo_config, demo_paths, reset_demo_storage, seed_demo_data
from kanban_app.infrastructure.services.station_runtime import StationRuntimeStore, station_id
from kanban_app.presentation.tv_settings import default_tv_settings


@dataclass(slots=True)
class AppContainer:
    config: AppConfig
    database: Database
    repository: ProductionRepository
    production_service: ProductionService
    document_import_service: DocumentImportService
    runtime_store: StationRuntimeStore
    station_id: str
    is_demo: bool = False
    demo_paths: DemoPaths | None = None

    @classmethod
    def create(cls, config_path: str | Path) -> "AppContainer":
        config = load_config(config_path)
        database = Database(config.database_path, backups_dir=config.backups_dir)
        database.create_schema()
        current_station_id = station_id()
        repository = ProductionRepository(database)
        if not database.is_read_only():
            cls._ensure_default_settings(repository, current_station_id)
        return cls(
            config=config,
            database=database,
            repository=repository,
            production_service=ProductionService(repository, station_id=current_station_id),
            document_import_service=DocumentImportService(),
            runtime_store=StationRuntimeStore(),
            station_id=current_station_id,
        )

    @classmethod
    def create_demo(cls, root: Path | None = None) -> "AppContainer":
        """Inicializa a experiência demonstrativa sem usar configuração ou dados reais."""

        paths = demo_paths(root)
        paths.root.mkdir(parents=True, exist_ok=True)
        config = demo_config(paths)
        database = Database(config.database_path, backups_dir=config.backups_dir)
        database.create_schema()
        current_station_id = f"demo_{station_id()}"
        repository = ProductionRepository(database)
        cls._ensure_default_settings(repository, current_station_id)
        seed_demo_data(repository, station_id=current_station_id)
        return cls(
            config=config,
            database=database,
            repository=repository,
            production_service=ProductionService(repository, station_id=current_station_id),
            document_import_service=DocumentImportService(),
            runtime_store=StationRuntimeStore(root=paths.runtime_dir),
            station_id=current_station_id,
            is_demo=True,
            demo_paths=paths,
        )

    def reset_demo(self) -> "AppContainer":
        if not self.is_demo or self.demo_paths is None:
            raise RuntimeError("A restauração só está disponível no modo demonstração.")
        self.database.close()
        reset_demo_storage(self.demo_paths)
        return self.create_demo(self.demo_paths.root)

    @staticmethod
    def _ensure_default_settings(repository: ProductionRepository, station: str) -> None:
        defaults = {
            "deadline.warning_color": "#f9a8d4",
            "deadline.critical_color": "#ef4444",
            "deadline.warning_days": 14,
            "deadline.critical_days": 7,
            "deadline.cutoff_sector_id": None,
            "deadline.email_hour": "08:00",
            "deadline.email_recipients": [],
        }
        defaults.update({f"tv.{key}": value for key, value in default_tv_settings().items()})
        for key, value in defaults.items():
            if repository.get_setting(key, None) is None:
                repository.set_setting(key, value, station_id=station)
