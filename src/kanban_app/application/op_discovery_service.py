from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from kanban_app.application.document_import_service import DocumentImportService
from kanban_app.domain.enums import OpStatus
from kanban_app.infrastructure.config import OpDiscoveryConfig
from kanban_app.infrastructure.db.repositories import ProductionRepository


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    source_path: Path
    source_key: str
    source_group: str
    expected_number: str
    folder_key: str
    source_size: int
    source_modified_at: datetime


@dataclass(slots=True)
class DiscoveryResult:
    status: str
    active_root: str = ""
    baselined: int = 0
    imported: int = 0
    pending: int = 0
    blocked_duplicates: int = 0
    conflicts: int = 0
    skipped: int = 0
    message: str = ""

    def summary(self) -> str:
        fields = [
            f"status={self.status}",
            f"baseline={self.baselined}",
            f"importadas={self.imported}",
            f"pendentes={self.pending}",
            f"duplicadas_bloqueadas={self.blocked_duplicates}",
            f"conflitos={self.conflicts}",
            f"ignoradas={self.skipped}",
        ]
        if self.message:
            fields.append(f"mensagem={self.message}")
        return " | ".join(fields)


class OpDiscoveryService:
    """Descobre exclusivamente OPs criadas após a linha de base inicial.

    A origem é sempre uma chave relativa ao diretório de produção. Assim o
    mesmo NAS acessado por nome, IP ou unidade mapeada não produz reimportação.
    """

    LOCK_KEY = "op_discovery_worker"
    BASELINE_SETTING = "op_discovery.baseline_complete"
    BASELINE_SIGNATURE_SETTING = "op_discovery.baseline_signature"
    _FOLDER_NUMBER = re.compile(r"\bOP\s*[-–]?\s*(\d{3,})\b", re.IGNORECASE)
    _EXCLUDED_FOLDERS = {"00 - MODELOS", "ZZ00 - OP"}
    _EXTENSION_PRIORITY = (".odt", ".docx", ".pdf")
    _TERMINAL_STATES = {
        "BASELINED",
        "IMPORTED",
        "BLOCKED_DUPLICATE",
        "SKIPPED_COMPANION",
    }

    def __init__(
        self,
        repository: ProductionRepository,
        importer: DocumentImportService,
        config: OpDiscoveryConfig,
        *,
        station_id: str,
    ):
        self.repository = repository
        self.importer = importer
        self.config = config
        self.station_id = station_id

    def run(self) -> DiscoveryResult:
        if not self.config.enabled:
            return DiscoveryResult(status="DISABLED", message="Integração automática desativada na configuração local.")
        production_root = self._resolve_production_root()
        if production_root is None:
            return DiscoveryResult(status="NAS_UNAVAILABLE", message="Nenhum caminho configurado do NAS possui a estrutura de produção esperada.")

        owner_id = f"{self.station_id}:{uuid4()}"
        if not self.repository.claim_run_lock(self.LOCK_KEY, owner_id, lease_minutes=self.config.worker_lease_minutes):
            return DiscoveryResult(status="LOCKED", active_root=str(production_root), message="Outra estação integradora já está em execução.")
        try:
            candidates = self._candidates(production_root)
            result = DiscoveryResult(status="OK", active_root=str(production_root))
            signature = self._baseline_signature()
            if (
                not bool(self.repository.get_setting(self.BASELINE_SETTING, False))
                or self.repository.get_setting(self.BASELINE_SIGNATURE_SETTING, "") != signature
            ):
                result.baselined = self.repository.create_import_baseline(
                    (
                        (item.source_key, item.source_group, item.source_size, item.source_modified_at)
                        for item in candidates
                    ),
                    station_id=self.station_id,
                )
                self.repository.set_setting(self.BASELINE_SIGNATURE_SETTING, signature, station_id=self.station_id)
                result.status = "BASELINED"
                result.message = "Linha de base criada ou atualizada; documentos já existentes não foram abertos nem importados."
                return result

            records = self.repository.import_source_records(item.source_key for item in candidates)
            by_folder: dict[str, list[DiscoveryCandidate]] = defaultdict(list)
            for item in candidates:
                by_folder[item.folder_key].append(item)

            sector_id = self._project_sector_id()
            if not sector_id:
                return DiscoveryResult(
                    status="CONFIG_ERROR",
                    active_root=str(production_root),
                    message=f"Setor inicial '{self.config.initial_sector_name}' não encontrado ou inativo.",
                )
            for folder_candidates in by_folder.values():
                self._process_folder(folder_candidates, records, sector_id, result)
            return result
        finally:
            self.repository.release_run_lock(self.LOCK_KEY, owner_id)

    def _process_folder(
        self,
        candidates: list[DiscoveryCandidate],
        records,
        sector_id: str,
        result: DiscoveryResult,
    ) -> None:
        actionable: list[DiscoveryCandidate] = []
        for item in candidates:
            record = records.get(item.source_key)
            if record is None:
                actionable.append(item)
                continue
            unchanged = record.source_size == item.source_size and record.source_modified_at == item.source_modified_at
            if record.state in self._TERMINAL_STATES or (record.state == "PENDING_INCOMPLETE" and unchanged):
                result.skipped += 1
                continue
            actionable.append(item)
        if not actionable:
            return

        ready: list[tuple[DiscoveryCandidate, object]] = []
        for item in actionable:
            preview = self.importer.extract(item.source_path, default_sector_id=sector_id)
            if preview.errors:
                self.repository.record_import_source(
                    source_key=item.source_key, source_group=item.source_group, source_size=item.source_size,
                    source_modified_at=item.source_modified_at, state="PENDING_INCOMPLETE", error="; ".join(preview.errors),
                )
                result.pending += 1
                continue
            if preview.form.numero_op != item.expected_number:
                self.repository.record_import_source(
                    source_key=item.source_key, source_group=item.source_group, source_size=item.source_size,
                    source_modified_at=item.source_modified_at, state="CONFLICT_NUMBER", op_number=preview.form.numero_op,
                    error=f"Número do documento ({preview.form.numero_op or 'vazio'}) diverge da pasta ({item.expected_number}).",
                )
                result.conflicts += 1
                continue
            if preview.missing_fields:
                self.repository.record_import_source(
                    source_key=item.source_key, source_group=item.source_group, source_size=item.source_size,
                    source_modified_at=item.source_modified_at, state="PENDING_INCOMPLETE", op_number=preview.form.numero_op,
                    error="Campos obrigatórios ausentes: " + ", ".join(preview.missing_fields),
                )
                result.pending += 1
                continue
            ready.append((item, preview.form))

        if len(ready) > 1:
            for item, form in ready:
                self.repository.record_import_source(
                    source_key=item.source_key, source_group=item.source_group, source_size=item.source_size,
                    source_modified_at=item.source_modified_at, state="CONFLICT_MULTIPLE_DOCUMENTS", op_number=form.numero_op,
                    error="Mais de um documento completo e compatível foi encontrado para a mesma pasta de OP.",
                )
            result.conflicts += len(ready)
            return
        if not ready:
            return

        item, form = ready[0]
        final_form = replace(form, data_inicio=date.today(), setor_id=sector_id, status=OpStatus.EM_DIA)
        outcome, _op = self.repository.import_op_from_source(
            final_form,
            source_key=item.source_key,
            source_group=item.source_group,
            source_size=item.source_size,
            source_modified_at=item.source_modified_at,
            station_id=self.station_id,
        )
        if outcome == "IMPORTED":
            result.imported += 1
            for companion in actionable:
                if companion.source_key == item.source_key:
                    continue
                self.repository.record_import_source(
                    source_key=companion.source_key, source_group=companion.source_group, source_size=companion.source_size,
                    source_modified_at=companion.source_modified_at, state="SKIPPED_COMPANION", op_number=item.expected_number,
                    error="Outro documento da mesma pasta foi selecionado e importado com segurança.",
                )
            return
        if outcome == "BLOCKED_DUPLICATE":
            result.blocked_duplicates += 1
            return
        result.skipped += 1

    def _resolve_production_root(self) -> Path | None:
        for root in self.config.source_root_candidates:
            candidate = root / self.config.production_relative_path
            try:
                if candidate.is_dir() and all((candidate / group).is_dir() for group in self.config.groups):
                    return candidate
            except OSError:
                continue
        return None

    def _candidates(self, production_root: Path) -> list[DiscoveryCandidate]:
        candidates: list[DiscoveryCandidate] = []
        for group in self.config.groups:
            group_dir = production_root / group
            try:
                folders = sorted((item for item in group_dir.iterdir() if item.is_dir()), key=lambda item: item.name.casefold())
            except OSError:
                continue
            for folder in folders:
                if folder.name.casefold() in {name.casefold() for name in self._EXCLUDED_FOLDERS}:
                    continue
                number = self._FOLDER_NUMBER.search(folder.name)
                if number is None:
                    continue
                op_dir = folder / "OP"
                try:
                    files = [item for item in op_dir.iterdir() if item.is_file()] if op_dir.is_dir() else []
                except OSError:
                    continue
                selected_extension = next(
                    (
                        suffix
                        for suffix in self._EXTENSION_PRIORITY
                        if suffix in self.config.document_extensions and any(item.suffix.casefold() == suffix for item in files)
                    ),
                    None,
                )
                if selected_extension is None:
                    continue
                for document in sorted((item for item in files if item.suffix.casefold() == selected_extension), key=lambda item: item.name.casefold()):
                    try:
                        stat = document.stat()
                    except OSError:
                        continue
                    relative = document.relative_to(production_root).as_posix()
                    candidates.append(
                        DiscoveryCandidate(
                            source_path=document,
                            source_key=relative,
                            source_group=group,
                            expected_number=number.group(1),
                            folder_key=f"{group}/{folder.name}",
                            source_size=int(stat.st_size),
                            source_modified_at=datetime.fromtimestamp(stat.st_mtime),
                        )
                    )
        return candidates

    def _project_sector_id(self) -> str | None:
        expected = self.config.initial_sector_name.casefold()
        for sector in self.repository.list_sectors(active_only=True):
            if sector.nome.casefold() == expected:
                return sector.id
        return None

    def _baseline_signature(self) -> str:
        groups = "|".join(item.casefold() for item in self.config.groups)
        extensions = "|".join(self.config.document_extensions)
        return f"{self.config.production_relative_path.as_posix().casefold()}::{groups}::{extensions}"
