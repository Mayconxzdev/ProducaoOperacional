from __future__ import annotations

import sqlite3
import time
from functools import wraps
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from kanban_app.application.application_errors import ReadOnlyModeError
from kanban_app.domain.option_lists import DEFAULT_SECTOR_COLORS, DEFAULT_SECTOR_NAMES, stable_sector_id
from kanban_app.infrastructure.db.base import Base
from kanban_app.infrastructure.db.models import utc_now
from kanban_app.formatting import normalize_voltage_value


def _retry_schema_if_locked(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        delays = (0.0, 0.30, 0.80, 1.50)
        for attempt, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                return fn(*args, **kwargs)
            except (OperationalError, sqlite3.OperationalError) as exc:
                message = str(exc).casefold()
                locked = any(
                    token in message
                    for token in (
                        "database is locked",
                        "database table is locked",
                        "database is busy",
                        "sqlite_busy",
                        "sqlite_locked",
                    )
                )
                if not locked or attempt == len(delays) - 1:
                    raise
        return None  # pragma: no cover

    return wrapped


class Database:
    """Banco SQLite autoritativo no NAS com migração versionada e backup obrigatório."""

    SCHEMA_VERSION = 25
    SQLITE_BUSY_TIMEOUT_MS = 10_000

    def __init__(self, db_path: Path, *, backups_dir: Path | None = None):
        self.db_path = Path(db_path)
        self.backups_dir = Path(backups_dir) if backups_dir else self.db_path.parent / "backups"
        self._read_only_reason = ""
        self._read_only_recoverable = True
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # O aplicativo ainda deve abrir pelo cache quando o NAS estiver fora do ar.
            self._read_only_reason = f"NAS indisponível na inicialização: {exc}"
            self._read_only_recoverable = True
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False, "timeout": self.SQLITE_BUSY_TIMEOUT_MS / 1000},
            poolclass=NullPool,
            future=True,
        )
        event.listen(self.engine, "connect", self._configure_connection)
        self._session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False, future=True)

    @staticmethod
    def _configure_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA temp_store=MEMORY")
        finally:
            cursor.close()

    @_retry_schema_if_locked
    def create_schema(self) -> None:
        upgrade_required = False
        try:
            tables = set(inspect(self.engine).get_table_names())
            current_version = self._existing_schema_version(tables)
            if current_version > self.SCHEMA_VERSION:
                reason = (
                    f"O banco está na versão {current_version}, mais nova que esta aplicação "
                    f"(versão de banco {self.SCHEMA_VERSION}). Instale a versão mais recente do aplicativo."
                )
                self.set_read_only(reason, recoverable=False)
                raise RuntimeError(reason)
            upgrade_required = self._needs_v2_migration(tables) or bool(
                tables and current_version < self.SCHEMA_VERSION
            )
            if self._needs_v2_migration(tables):
                self._backup_and_migrate(tables)
            elif tables and current_version < self.SCHEMA_VERSION:
                self.create_verified_backup(prefix=f"producao_operacional_pre_v{self.SCHEMA_VERSION}")

            Base.metadata.create_all(self.engine)
            with self.engine.begin() as connection:
                # O modo DELETE é o mais conservador para SQLite em compartilhamento SMB.
                connection.execute(text("PRAGMA journal_mode=DELETE"))
                self._upgrade_incremental_schema(connection)
                self._seed_default_sectors_if_empty(connection)
                self._repair_sector_catalog(connection)
                self._normalize_status_values(connection)
                self._normalize_voltage_values(connection)
                self._drop_obsolete_runtime_tables(connection)
                connection.execute(
                    text("DELETE FROM app_settings WHERE setting_key = 'deadline.cutoff_sector_id'")
                )
                self._validate_schema(connection)
                self._set_meta(connection, "schema_version", str(self.SCHEMA_VERSION))
                self._set_meta(connection, "schema_name", "producao_operacional_v2")
            self.clear_read_only(force=True)
        except Exception as exc:
            if self._is_connectivity_error(exc):
                self.set_read_only(f"NAS indisponível na inicialização: {exc}", recoverable=True)
                return
            if upgrade_required:
                self.set_read_only(
                    f"Atualização do banco não concluída com segurança: {exc}",
                    recoverable=False,
                )
            raise

    @staticmethod
    def _is_connectivity_error(exc: Exception) -> bool:
        message = str(exc).casefold()
        return any(
            token in message
            for token in (
                "unable to open database file",
                "disk i/o error",
                "network",
                "the network path was not found",
                "the specified network name is no longer available",
                "winerror 53",
                "winerror 64",
                "winerror 67",
                "no such file or directory",
            )
        )

    def _existing_schema_version(self, tables: set[str]) -> int:
        if "app_meta" not in tables:
            return 0
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    text("SELECT meta_value FROM app_meta WHERE meta_key = 'schema_version'")
                ).fetchone()
        except Exception:
            return 0
        return int(row[0]) if row and str(row[0]).isdigit() else 0

    def _needs_v2_migration(self, tables: set[str]) -> bool:
        if "ops" not in tables:
            return False
        columns = {column["name"] for column in inspect(self.engine).get_columns("ops")}
        return "empresa_grupo" in columns or "status_geral" in columns or "setor_id" not in columns

    def _backup_and_migrate(self, tables: set[str]) -> None:
        backup_path = self.create_verified_backup()
        try:
            with self.engine.begin() as connection:
                self._migrate_legacy_schema(connection, tables, backup_path)
        except Exception:
            self.set_read_only("Migração do banco não concluída; a base original foi preservada no backup.", recoverable=False)
            raise

    def create_verified_backup(self, *, prefix: str = "kanban_pre_v2") -> Path:
        if not self.db_path.exists():
            raise RuntimeError("Banco do NAS não encontrado para criar backup de migração.")
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = self.backups_dir / f"{prefix}_{stamp}.db"

        # A API de backup do SQLite produz uma cópia consistente mesmo quando outra
        # estação está apenas lendo a base. É mais segura do que copiar o arquivo bruto.
        source = sqlite3.connect(str(self.db_path), timeout=self.SQLITE_BUSY_TIMEOUT_MS / 1000)
        destination = sqlite3.connect(str(target))
        try:
            source.execute(f"PRAGMA busy_timeout={self.SQLITE_BUSY_TIMEOUT_MS}")
            source.backup(destination)
            destination.commit()
            result = destination.execute("PRAGMA quick_check").fetchone()
        finally:
            destination.close()
            source.close()
        if not target.exists() or target.stat().st_size <= 0:
            raise RuntimeError("Backup de migração inválido: arquivo não foi criado corretamente.")
        if result is None or str(result[0]).lower() != "ok":
            target.unlink(missing_ok=True)
            raise RuntimeError("Backup de migração inválido: PRAGMA quick_check falhou.")
        return target

    def _migrate_legacy_schema(self, connection: Connection, tables: set[str], backup_path: Path) -> None:
        rename_targets = {
            "ops": "legacy_ops",
            "historico": "legacy_historico",
            "op_mutations": "legacy_op_mutations",
            "app_settings": "legacy_app_settings",
            "app_station_presence": "legacy_app_station_presence",
        }
        for source, target in rename_targets.items():
            if source in tables and target not in tables:
                self._drop_explicit_indexes(connection, source)
                connection.execute(text(f'ALTER TABLE "{source}" RENAME TO "{target}"'))

        Base.metadata.create_all(connection)
        self._seed_default_sectors(connection)
        sector_ids = self._migrate_legacy_ops(connection)
        self._migrate_legacy_history(connection)
        self._migrate_legacy_settings(connection)
        self._drop_legacy_tables(connection)
        self._set_meta(connection, "schema_version", str(self.SCHEMA_VERSION))
        self._set_meta(connection, "schema_name", "producao_operacional_v2")
        self._set_meta(connection, "v2_migration_backup", str(backup_path))
        self._set_meta(connection, "v2_migration_sector_count", str(len(sector_ids)))

    def _seed_default_sectors_if_empty(self, connection: Connection) -> None:
        count = int(connection.execute(text("SELECT COUNT(*) FROM sectors")).scalar_one())
        if count == 0:
            self._seed_default_sectors(connection)

    def _seed_default_sectors(self, connection: Connection) -> None:
        for index, name in enumerate(DEFAULT_SECTOR_NAMES, start=1):
            connection.execute(
                text(
                    "INSERT INTO sectors(id, nome, ordem, cor, cor_texto, ativo, created_at, updated_at) "
                    "VALUES (:id, :nome, :ordem, :cor, '#ffffff', 1, :now, :now) "
                    "ON CONFLICT(id) DO NOTHING"
                ),
                {
                    "id": stable_sector_id(name),
                    "nome": name,
                    "ordem": index,
                    "cor": DEFAULT_SECTOR_COLORS[index - 1],
                    "now": utc_now(),
                },
            )

    def _migrate_legacy_ops(self, connection: Connection) -> set[str]:
        if "legacy_ops" not in inspect(connection).get_table_names():
            return {stable_sector_id(name) for name in DEFAULT_SECTOR_NAMES}
        rows = connection.execute(text("SELECT * FROM legacy_ops ORDER BY id")).mappings().all()
        sector_lookup = {
            self._sector_key(row["nome"]): row["id"]
            for row in connection.execute(text("SELECT id, nome FROM sectors")).mappings()
        }
        used_sector_ids = set(sector_lookup.values())
        for row in rows:
            raw_sector = str(row.get("setor") or "").strip()
            sector_id = None
            if raw_sector:
                key = self._sector_key(raw_sector)
                sector_id = sector_lookup.get(key)
                if sector_id is None:
                    sector_id = stable_sector_id(raw_sector)
                    position = len(sector_lookup) + 1
                    connection.execute(
                        text(
                            "INSERT INTO sectors(id, nome, ordem, cor, cor_texto, ativo, created_at, updated_at) "
                            "VALUES (:id, :nome, :ordem, '#475569', '#ffffff', 1, :now, :now) "
                            "ON CONFLICT(id) DO NOTHING"
                        ),
                        {"id": sector_id, "nome": raw_sector, "ordem": position, "now": utc_now()},
                    )
                    sector_lookup[key] = sector_id
            status = self._map_legacy_status(row)
            completed_at = row.get("updated_at") if status == "CONCLUIDO" else None
            pendencia = str(row.get("pendencia_principal") or "").strip()
            if pendencia.casefold() in {"sem pendências", "sem pendencias"}:
                pendencia = ""
            connection.execute(
                text(
                    "INSERT INTO ops(id, numero_op, cliente, modelo, quantidade, voltagem, data_inicio, data_entrega, "
                    "setor_id, status, pendencia, completed_at, archived, archived_at, row_version, created_at, updated_at) "
                    "VALUES (:id, :numero_op, :cliente, :modelo, :quantidade, :voltagem, :data_inicio, :data_entrega, "
                    ":setor_id, :status, :pendencia, :completed_at, :archived, :archived_at, :row_version, :created_at, :updated_at)"
                ),
                {
                    "id": row["id"],
                    "numero_op": str(row.get("numero_op") or ""),
                    "cliente": str(row.get("cliente") or ""),
                    "modelo": str(row.get("modelo") or ""),
                    "quantidade": self._positive_int_or_none(row.get("quantidade")),
                    "voltagem": str(row.get("tensao") or ""),
                    "data_inicio": row.get("data_inicio"),
                    "data_entrega": row.get("data_entrega"),
                    "setor_id": sector_id,
                    "status": status,
                    "pendencia": pendencia,
                    "completed_at": completed_at,
                    "archived": 1 if row.get("archived") else 0,
                    "archived_at": row.get("archived_at"),
                    "row_version": max(1, int(row.get("row_version") or 1)),
                    "created_at": row.get("created_at") or utc_now(),
                    "updated_at": row.get("updated_at") or utc_now(),
                },
            )
            if sector_id:
                used_sector_ids.add(sector_id)
        return used_sector_ids

    @staticmethod
    def _map_legacy_status(row) -> str:
        if bool(row.get("prioridade")):
            return "PRIORIDADE"
        raw = str(row.get("status_geral") or "").strip().upper()
        if raw == "RESOLVIDA":
            return "CONCLUIDO"
        if raw in {"ATENCAO", "ATRASADA", "EM_ATRASO"}:
            return "EM_ATRASO"
        if raw in {"AGUARDANDO_ADM", "AGUARDANDO"}:
            return "AGUARDANDO"
        return "EM_DIA"

    @staticmethod
    def _positive_int_or_none(value) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _sector_key(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
        return "".join(char for char in normalized if char.isalnum() and not unicodedata.combining(char))

    def _repair_sector_catalog(self, connection: Connection) -> None:
        """Corrige duplicidades/aliases legados sem impedir futuras personalizações."""
        tables = set(inspect(connection).get_table_names())
        if "sectors" not in tables or "ops" not in tables:
            return

        rows = list(connection.execute(text("SELECT id, nome, ordem, cor, cor_texto, ativo FROM sectors ORDER BY ordem, nome")).mappings())
        if not rows:
            return

        canonical_ids = {self._sector_key(name): stable_sector_id(name) for name in DEFAULT_SECTOR_NAMES}
        aliases = {
            "projetos": "projeto",
            "desenho": "projeto",
            "ser": "serralheria",
            "mont": "montagem",
            "bicr": "bicromatizacao",
            "pint": "pintura",
            "qualidades": "qualidade",
            "exp": "expedicao",
            "concluido": "expedicao",
            "pronto": "expedicao",
            "resolvida": "expedicao",
        }

        by_id = {str(row["id"]): row for row in rows}

        def merge(source_id: str, target_id: str) -> None:
            if source_id == target_id or source_id not in by_id or target_id not in by_id:
                return
            connection.execute(text("UPDATE ops SET setor_id = :target WHERE setor_id = :source"), {"target": target_id, "source": source_id})
            connection.execute(text("DELETE FROM sectors WHERE id = :source"), {"source": source_id})
            by_id.pop(source_id, None)

        # Primeiro mescla nomes equivalentes (incluindo diferenças de acento/caixa).
        groups: dict[str, list[str]] = {}
        for sector_id, row in list(by_id.items()):
            groups.setdefault(self._sector_key(row["nome"]), []).append(sector_id)
        for key, ids in groups.items():
            if len(ids) < 2:
                continue
            preferred = canonical_ids.get(key)
            winner = preferred if preferred in ids else min(ids, key=lambda item: (int(by_id[item]["ordem"] or 9999), item))
            for source_id in list(ids):
                if source_id != winner:
                    merge(source_id, winner)

        repair_version = 0
        try:
            raw_version = connection.execute(
                text("SELECT meta_value FROM app_meta WHERE meta_key = 'sector_catalog_repaired'")
            ).scalar_one_or_none()
            repair_version = int(raw_version or 0)
        except (TypeError, ValueError):
            repair_version = 0

        # Nomes que eram itens/status só são tratados durante a atualização legada.
        # Depois disso o usuário continua livre para criar nomes personalizados.
        if repair_version < self.SCHEMA_VERSION:
            for source_id, row in list(by_id.items()):
                key = self._sector_key(row["nome"])
                target_key = aliases.get(key)
                if not target_key:
                    continue
                target_id = canonical_ids.get(target_key)
                if target_id in by_id and source_id != target_id:
                    merge(source_id, target_id)

        # Garante ordem compacta e previsível depois da limpeza, preservando a ordem relativa.
        remaining = list(connection.execute(text("SELECT id FROM sectors ORDER BY ordem, nome")).scalars())
        for position, sector_id in enumerate(remaining, start=1):
            connection.execute(text("UPDATE sectors SET ordem = :ordem WHERE id = :id"), {"ordem": position, "id": sector_id})
        self._set_meta(connection, "sector_catalog_repaired", str(self.SCHEMA_VERSION))

    def _migrate_legacy_history(self, connection: Connection) -> None:
        if "legacy_historico" not in inspect(connection).get_table_names():
            return
        valid_op_ids = {row[0] for row in connection.execute(text("SELECT id FROM ops"))}
        rows = connection.execute(text("SELECT * FROM legacy_historico ORDER BY id")).mappings().all()
        for row in rows:
            op_id = int(row.get("entidade_id") or 0)
            if str(row.get("entidade") or "").upper() != "OP" or op_id not in valid_op_ids:
                continue
            connection.execute(
                text(
                    "INSERT INTO op_history(op_id, event_type, field_name, old_value, new_value, station_id, occurred_at) "
                    "VALUES (:op_id, 'MIGRADO', :field_name, :old_value, :new_value, 'estacao_legada', :occurred_at)"
                ),
                {
                    "op_id": op_id,
                    "field_name": str(row.get("campo") or ""),
                    "old_value": str(row.get("valor_anterior") or ""),
                    "new_value": str(row.get("valor_novo") or ""),
                    "occurred_at": row.get("data_hora") or utc_now(),
                },
            )

    def _migrate_legacy_settings(self, connection: Connection) -> None:
        if "legacy_app_settings" not in inspect(connection).get_table_names():
            return
        rows = connection.execute(text("SELECT setting_key, setting_value, version, updated_at FROM legacy_app_settings")).mappings().all()
        for row in rows:
            key = str(row.get("setting_key") or "").strip()
            if not key or key.startswith(("telegram", "host", "summary", "auth", "kanban")):
                continue
            connection.execute(
                text(
                    "INSERT INTO app_settings(setting_key, setting_value, version, updated_station_id, updated_at) "
                    "VALUES (:key, :value, :version, 'estacao_legada', :updated_at) "
                    "ON CONFLICT(setting_key) DO NOTHING"
                ),
                {
                    "key": key,
                    "value": str(row.get("setting_value") or ""),
                    "version": max(1, int(row.get("version") or 1)),
                    "updated_at": row.get("updated_at") or utc_now(),
                },
            )


    @classmethod
    def _upgrade_incremental_schema(cls, connection: Connection) -> None:
        """Aplica alterações pequenas que o ``create_all`` não adiciona sozinho."""

        tables = set(inspect(connection).get_table_names())
        if "sectors" in tables:
            columns = {column["name"] for column in inspect(connection).get_columns("sectors")}
            added_text_color = "cor_texto" not in columns
            if added_text_color:
                connection.execute(
                    text("ALTER TABLE sectors ADD COLUMN cor_texto VARCHAR(16) NOT NULL DEFAULT '#ffffff'")
                )
            rows = connection.execute(text("SELECT id, cor, cor_texto FROM sectors")).mappings().all()
            for row in rows:
                current = str(row.get("cor_texto") or "").strip()
                if added_text_color or not cls._valid_hex_color(current):
                    suggested = cls._contrast_text_color(str(row.get("cor") or "#475569"))
                    connection.execute(
                        text("UPDATE sectors SET cor_texto = :color WHERE id = :id"),
                        {"color": suggested, "id": row["id"]},
                    )

    @staticmethod
    def _valid_hex_color(value: str) -> bool:
        value = str(value or "").strip()
        if len(value) != 7 or not value.startswith("#"):
            return False
        try:
            int(value[1:], 16)
        except ValueError:
            return False
        return True

    @staticmethod
    def _contrast_text_color(background: str) -> str:
        value = str(background or "#475569").lstrip("#")
        try:
            red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        except (ValueError, IndexError):
            return "#ffffff"
        luminance = (red * 299 + green * 587 + blue * 114) / 1000
        return "#111827" if luminance > 150 else "#ffffff"

    @staticmethod
    def _normalize_voltage_values(connection: Connection) -> None:
        if "ops" not in inspect(connection).get_table_names():
            return
        rows = connection.execute(text("SELECT id, voltagem FROM ops")).mappings().all()
        for row in rows:
            normalized = normalize_voltage_value(row.get("voltagem"))
            if normalized != str(row.get("voltagem") or ""):
                connection.execute(
                    text("UPDATE ops SET voltagem = :voltagem WHERE id = :id"),
                    {"voltagem": normalized, "id": row["id"]},
                )

    @staticmethod
    def _normalize_status_values(connection: Connection) -> None:
        """Converte valores legados para os cinco status atuais antes de qualquer edição."""
        mappings = {
            "ATENCAO": "EM_ATRASO",
            "ATRASADA": "EM_ATRASO",
            "ATRASADO": "EM_ATRASO",
            "EM_ATENCAO": "EM_ATRASO",
            "AGUARDANDO_ADM": "AGUARDANDO",
            "PRONTO": "CONCLUIDO",
            "RESOLVIDA": "CONCLUIDO",
            "RESOLVIDO": "CONCLUIDO",
        }
        for source, target in mappings.items():
            connection.execute(
                text("UPDATE ops SET status = :target WHERE UPPER(TRIM(status)) = :source"),
                {"source": source, "target": target},
            )
        connection.execute(
            text(
                "UPDATE ops SET status = 'EM_DIA' "
                "WHERE status IS NULL OR TRIM(status) = '' OR UPPER(TRIM(status)) NOT IN "
                "('PRIORIDADE', 'EM_ATRASO', 'EM_DIA', 'AGUARDANDO', 'CONCLUIDO')"
            )
        )

    @staticmethod
    def _validate_schema(connection: Connection) -> None:
        """Falha cedo com mensagem clara em vez de quebrar somente ao salvar uma OP."""
        required_columns = {
            "ops": {
                "id", "numero_op", "cliente", "modelo", "quantidade", "voltagem",
                "data_inicio", "data_entrega", "setor_id", "status", "pendencia",
                "completed_at", "archived", "archived_at", "row_version",
                "created_at", "updated_at",
            },
            "sectors": {"id", "nome", "ordem", "cor", "cor_texto", "ativo", "created_at", "updated_at"},
            "op_acompanhamento": {"id", "op_id", "field_key", "state", "station_id", "updated_at"},
            "op_history": {
                "id", "op_id", "event_type", "field_name", "old_value", "new_value",
                "station_id", "occurred_at",
            },
            "app_settings": {
                "setting_key", "setting_value", "version", "updated_station_id", "updated_at",
            },
            "app_meta": {"meta_key", "meta_value"},
            "deadline_alert_sends": {
                "id", "op_id", "milestone_date", "milestone_days", "status", "error", "sent_at",
            },
        }
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        missing_tables = sorted(set(required_columns) - existing_tables)
        if missing_tables:
            raise RuntimeError(f"Estrutura do banco incompleta. Tabelas ausentes: {', '.join(missing_tables)}")
        for table, required in required_columns.items():
            actual = {column["name"] for column in inspector.get_columns(table)}
            missing = sorted(required - actual)
            if missing:
                raise RuntimeError(
                    f"Estrutura do banco incompatível na tabela {table}. Colunas ausentes: {', '.join(missing)}"
                )
        result = connection.execute(text("PRAGMA quick_check")).fetchone()
        if result is None or str(result[0]).lower() != "ok":
            raise RuntimeError(f"O banco não passou na verificação de integridade: {result[0] if result else 'sem resultado'}")

    def _drop_obsolete_runtime_tables(self, connection: Connection) -> None:
        """Remove feeds/presenças antigos que não participam mais da sincronização atual."""
        existing = set(inspect(connection).get_table_names())
        for table in ("op_mutations", "station_presence"):
            if table in existing:
                connection.execute(text(f'DROP TABLE "{table}"'))

    def _drop_legacy_tables(self, connection: Connection) -> None:
        obsolete = (
            "attachments", "notificacoes", "op_items", "op_status_overrides", "op_edit_locks", "legacy_op_mutations",
            "legacy_ops", "legacy_historico", "legacy_app_settings", "legacy_app_station_presence",
            "app_mutation_registry", "app_runtime_locks", "app_station_presence", "app_users", "app_users_session",
            "csv_layout_profiles", "item_templates", "job_runs", "telegram_intake_requests",
        )
        existing = set(inspect(connection).get_table_names())
        for table in obsolete:
            if table in existing:
                connection.execute(text(f'DROP TABLE "{table}"'))

    @staticmethod
    def _drop_explicit_indexes(connection: Connection, table: str) -> None:
        """SQLite index names are global and survive ALTER TABLE RENAME."""
        for index in inspect(connection).get_indexes(table):
            name = str(index.get("name") or "")
            if name:
                connection.execute(text(f'DROP INDEX IF EXISTS "{name}"'))

    @staticmethod
    def _set_meta(connection: Connection, key: str, value: str) -> None:
        connection.execute(
            text(
                "INSERT INTO app_meta(meta_key, meta_value) VALUES (:key, :value) "
                "ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value"
            ),
            {"key": key, "value": value},
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def write_session(self) -> Iterator[Session]:
        if self.is_read_only():
            raise ReadOnlyModeError(self._read_only_reason or "Banco indisponível para alterações.")
        session = self._session_factory()
        try:
            session.execute(text("BEGIN IMMEDIATE"))
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def is_read_only(self) -> bool:
        return bool(self._read_only_reason)

    def set_read_only(self, reason: str = "", *, recoverable: bool = True) -> None:
        self._read_only_reason = str(reason or "Modo somente leitura.")
        self._read_only_recoverable = bool(recoverable)

    def clear_read_only(self, *, force: bool = False) -> bool:
        if self._read_only_reason and not self._read_only_recoverable and not force:
            return False
        self._read_only_reason = ""
        self._read_only_recoverable = True
        return True

    def read_only_reason(self) -> str:
        return self._read_only_reason

    def read_only_is_recoverable(self) -> bool:
        return self._read_only_recoverable

    def test_connection(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            self.clear_read_only()
            return not self.is_read_only()
        except Exception as exc:
            self.set_read_only(f"NAS indisponível: {exc}")
            return False

    def schema_version(self) -> int:
        with self.engine.connect() as connection:
            row = connection.execute(text("SELECT meta_value FROM app_meta WHERE meta_key = 'schema_version'")).fetchone()
        return int(row[0]) if row and str(row[0]).isdigit() else 0

    def close(self) -> None:
        """Libera os handles antes de uma restauração local do modo demonstração."""

        self.engine.dispose()
