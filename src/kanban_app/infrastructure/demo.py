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


DEMO_SEED_VERSION = 3
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
    """Cria uma base didática completa, realista e visualmente rica para Kanban, TV e Relatórios."""

    from datetime import datetime
    from sqlalchemy import select
    from kanban_app.infrastructure.db.models import OpModel

    current_seed_version = repository.get_setting("demo.seed_version", None)
    if current_seed_version == DEMO_SEED_VERSION:
        return

    # Garante que os setores industriais essenciais existam
    sectors = {sector.nome: sector.id for sector in repository.list_sectors(active_only=False)}
    if "FATURADO" not in sectors:
        sec = repository.add_sector("FATURADO", "#059669", station_id=station_id)
        sectors["FATURADO"] = sec.id

    today = date.today()
    y = today.year
    m = today.month

    prev_m = 12 if m == 1 else m - 1
    prev_y = y - 1 if m == 1 else y

    # Limpa registros didáticos prévios para recriação limpa
    with repository.database.write_session() as session:
        for op in session.execute(select(OpModel)).scalars().all():
            session.delete(op)

    # 1. Mês Anterior (8 OPs concluídas com 100% no prazo - demonstra histórico fechado)
    prev_samples = (
        ("90001", "Petrobras Distribuidora", "Ventilador Axial Pesado AX-900", 2, "380/660", "FATURADO", 3, 14, 12, OpStatus.CONCLUIDO),
        ("90002", "Energimax Eletromotores", "Exaustor Compacto EX-200", 6, "220", "Expedição", 4, 15, 15, OpStatus.CONCLUIDO),
        ("90003", "Termomecanica São Paulo", "Filtro de Manga FM-24", 1, "440", "FATURADO", 5, 18, 17, OpStatus.CONCLUIDO),
        ("90004", "Klabin Celulose e Papel", "Ventilador Centrífugo CF-800", 3, "380", "FATURADO", 6, 20, 19, OpStatus.CONCLUIDO),
        ("90005", "WEG Equipamentos", "Sistema de Exaustão Mod-4", 2, "220/380", "Expedição", 8, 22, 21, OpStatus.CONCLUIDO),
        ("90006", "Gerdau Aços Especiais", "Lavador de Gases LG-120", 1, "440", "FATURADO", 10, 24, 23, OpStatus.CONCLUIDO),
        ("90007", "Braskem Petroquímica", "Coletor de Pó Ciclônico CP-50", 4, "220", "FATURADO", 12, 26, 25, OpStatus.CONCLUIDO),
        ("90008", "Suzano Papel e Celulose", "Ventilador de Telhado VT-500", 8, "380", "FATURADO", 14, 28, 27, OpStatus.CONCLUIDO),
    )
    for num, cli, mod, qtd, volt, sec, d_ini, d_ent, d_conc, st in prev_samples:
        dt_ini = date(prev_y, prev_m, min(d_ini, 28))
        dt_ent = date(prev_y, prev_m, min(d_ent, 28))
        dt_conc_full = datetime(prev_y, prev_m, min(d_conc, 28), 15, 30)
        repository.create_op(
            OpFormDTO(
                numero_op=num,
                cliente=cli,
                modelo=mod,
                quantidade=qtd,
                voltagem=volt,
                data_inicio=dt_ini,
                data_entrega=dt_ent,
                setor_id=sectors[sec],
                status=st,
                pendencia="",
            ),
            station_id=station_id,
        )
        with repository.database.write_session() as session:
            op_db = session.execute(select(OpModel).where(OpModel.numero_op == num)).scalar_one()
            op_db.created_at = datetime(prev_y, prev_m, min(d_ini, 28), 8, 0)
            op_db.completed_at = dt_conc_full
            op_db.updated_at = dt_conc_full

    # 2. Mês Atual: 10 OPs Concluídas (9 no prazo + 1 com atraso = exatos 90,0% Entregue no Prazo!)
    cur_concluded = (
        ("92001", "Petrobras Distribuidora", "Ventilador Axial AX-700", 2, "380", "FATURADO", 1, 7, 6, OpStatus.CONCLUIDO),
        ("92002", "Energimax Linha Sul", "Exaustor Tubular TE-300", 4, "220/380", "Expedição", 2, 9, 8, OpStatus.CONCLUIDO),
        ("92003", "Termomecanica SP", "Filtro de Manga FM-12", 1, "440", "FATURADO", 3, 11, 10, OpStatus.CONCLUIDO),
        ("92004", "Klabin Papel Celulose", "Ventilador Centrífugo CF-500", 3, "380", "Expedição", 4, 14, 13, OpStatus.CONCLUIDO),
        ("92005", "WEG Motores Brasil", "Coletor Ciclônico CC-20", 2, "220/380", "FATURADO", 5, 16, 15, OpStatus.CONCLUIDO),
        ("92006", "Gerdau Usina Sul", "Lavador de Fumos LF-80", 1, "440", "Expedição", 6, 17, 17, OpStatus.CONCLUIDO),
        ("92007", "Braskem Alagoas", "Exaustor Centrífugo EC-400", 5, "220", "FATURADO", 7, 19, 18, OpStatus.CONCLUIDO),
        ("92008", "Suzano Bahia", "Ventilador de Telhado VT-400", 6, "380", "FATURADO", 8, 21, 20, OpStatus.CONCLUIDO),
        ("92009", "CSN Volta Redonda", "Cabine de Pintura CP-2", 1, "220/380", "Expedição", 10, 22, 22, OpStatus.CONCLUIDO),
        ("92010", "Anglo American Brasil", "Rotor Pesado Balanceado R-80", 2, "440", "FATURADO", 1, 12, 18, OpStatus.CONCLUIDO),
    )
    for num, cli, mod, qtd, volt, sec, d_ini, d_ent, d_conc, st in cur_concluded:
        day_ini = min(d_ini, today.day if today.day > 1 else 1)
        day_ent = min(d_ent, 28)
        day_conc = min(d_conc, today.day)
        dt_ini = date(y, m, day_ini)
        dt_ent = date(y, m, day_ent)
        dt_conc_full = datetime(y, m, day_conc, 14, 30)
        repository.create_op(
            OpFormDTO(
                numero_op=num,
                cliente=cli,
                modelo=mod,
                quantidade=qtd,
                voltagem=volt,
                data_inicio=dt_ini,
                data_entrega=dt_ent,
                setor_id=sectors[sec],
                status=st,
                pendencia="",
            ),
            station_id=station_id,
        )
        with repository.database.write_session() as session:
            op_db = session.execute(select(OpModel).where(OpModel.numero_op == num)).scalar_one()
            op_db.created_at = datetime(y, m, day_ini, 8, 0)
            op_db.completed_at = dt_conc_full
            op_db.updated_at = dt_conc_full

    # 3. Mês Atual: 12 OPs em Produção Ativa (todas no prazo -> 100% de conformidade de cronograma!)
    active_samples = (
        ("91001", "Cliente Alfa Metais", "Ventilador Industrial AX-450", 4, "220/380", "Projeto", -4, 4, OpStatus.EM_DIA, "Desenho técnico em fase final de validação."),
        ("91002", "Cliente Beta Mecânica", "Exaustor Compacto EX-150", 6, "220", "Serralheria", -3, 5, OpStatus.PRIORIDADE, "Chapas de aço carbono cortadas no laser."),
        ("91003", "Cliente Gama Equipamentos", "Coletor de Pó Série D", 2, "440", "Montagem", -3, 7, OpStatus.EM_DIA, "Conjunto motor alinhado."),
        ("91004", "Cliente Delta Engenharia", "Cabine de Pintura Mini", 1, "220/380", "Bicromatização", -2, 8, OpStatus.AGUARDANDO, "Aguardando retorno do tratamento superficial."),
        ("91005", "Cliente Épsilon Sistemas", "Ventilador Centrífugo CF-700", 3, "380", "Pintura", -2, 9, OpStatus.EM_DIA, "Aplicação de fundo epóxi anticorrosivo."),
        ("91006", "Cliente Zeta Automação", "Sistema de Exaustão Modular", 1, "440", "Testes", -1, 10, OpStatus.PRIORIDADE, "Bancada de teste de vibração e rotação liberada."),
        ("91007", "Cliente Eta Soluções", "Filtro de Manga FM-12", 2, "220", "Qualidade", -1, 12, OpStatus.EM_DIA, "Inspeção visual e dimensional em andamento."),
        ("91008", "Cliente Teta Ventilação", "Ventilador de Telhado VT-300", 5, "220", "Montagem", 0, 14, OpStatus.EM_DIA, "Hélices balanceadas dinamicamente."),
        ("91009", "Cliente Iota Indústria", "Exaustor Axial AX-800", 3, "380", "Projeto", 0, 15, OpStatus.EM_DIA, "Especificação técnica aprovada."),
        ("91010", "Cliente Kappa Mineração", "Ventilador Axial VP-100", 1, "440", "Serralheria", 0, 18, OpStatus.EM_DIA, "Caldeiraria pesada iniciada."),
    )
    for number, client, model, quantity, voltage, sector, start_offset, delivery_offset, status, pending in active_samples:
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
    """Preset de demonstração: mostra as OPs ativas com rotação de página fluida."""

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
