from __future__ import annotations

import sys
from enum import Enum

from PySide6.QtGui import QColor, QFont, QPalette


class ThemeMode(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


def resolve_theme_mode(value: str) -> ThemeMode:
    normalized = str(value or "system").casefold()
    if normalized == "light":
        return ThemeMode.LIGHT
    if normalized == "dark":
        return ThemeMode.DARK
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return ThemeMode.LIGHT if int(winreg.QueryValueEx(key, "AppsUseLightTheme")[0]) else ThemeMode.DARK
        except Exception:
            pass
    return ThemeMode.LIGHT


def apply_theme(app, theme_mode: str) -> ThemeMode:
    """Aplica um design system legível e consistente a toda a aplicação."""

    mode = resolve_theme_mode(theme_mode)
    dark = mode == ThemeMode.DARK
    colors = {
        "app": "#0f172a" if dark else "#f4f7fb",
        "surface": "#172033" if dark else "#ffffff",
        "surface_alt": "#1e2a40" if dark else "#f8fafc",
        "raised": "#263550" if dark else "#edf2f8",
        "border": "#42526b" if dark else "#cbd5e1",
        "border_soft": "#31415a" if dark else "#e2e8f0",
        "text": "#eff6ff" if dark else "#172033",
        "muted": "#aebcd0" if dark else "#64748b",
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "primary_pressed": "#1e40af",
        "accent": "#0f766e" if dark else "#0f766e",
        "accent_soft": "#174c50" if dark else "#ccfbf1",
        "danger": "#ef4444" if dark else "#dc2626",
        "warning": "#f59e0b" if dark else "#b45309",
        "success": "#22c55e" if dark else "#15803d",
        "selection": "#1d4ed8" if dark else "#dbeafe",
        "selection_text": "#ffffff" if dark else "#172033",
    }

    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["app"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["raised"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(colors["danger"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["muted"]))
    app.setPalette(palette)

    c = colors
    app.setStyleSheet(
        f"""
        * {{ outline: none; }}
        QMainWindow, QDialog, QWidget {{ color: {c['text']}; }}
        QMainWindow, QDialog {{ background: {c['app']}; }}

        QToolBar {{
            background: {c['surface']}; border: 0; border-bottom: 1px solid {c['border_soft']};
            spacing: 7px; padding: 9px 12px; min-height: 44px;
        }}
        QToolBar::separator {{ width: 1px; margin: 7px 5px; background: {c['border_soft']}; }}
        QToolButton, QPushButton {{
            min-height: 34px; padding: 0 14px; border: 1px solid {c['border']}; border-radius: 7px;
            background: {c['raised']}; color: {c['text']}; font-weight: 650;
        }}
        QToolButton:hover, QPushButton:hover {{ background: {c['surface_alt']}; border-color: {c['primary']}; }}
        QToolButton:pressed, QPushButton:pressed {{ background: {c['border_soft']}; border-color: {c['primary_hover']}; }}
        QToolButton:disabled, QPushButton:disabled {{ color: {c['muted']}; background: {c['surface_alt']}; border-color: {c['border_soft']}; }}
        QPushButton#primaryButton {{ background: {c['primary']}; border-color: {c['primary']}; color: #ffffff; font-weight: 750; }}
        QPushButton#primaryButton:hover {{ background: {c['primary_hover']}; border-color: {c['primary_hover']}; }}
        QPushButton#primaryButton:pressed {{ background: {c['primary_pressed']}; border-color: {c['primary_pressed']}; }}

        QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
            min-height: 34px; padding: 2px 9px; border: 1px solid {c['border']}; border-radius: 7px;
            background: {c['surface']}; color: {c['text']}; selection-background-color: {c['primary']};
            selection-color: #ffffff;
        }}
        QPlainTextEdit, QTextEdit {{ padding: 8px; }}
        QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTimeEdit:hover, QSpinBox:hover, QPlainTextEdit:hover {{ border-color: {c['muted']}; }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border: 2px solid {c['primary']}; padding: 1px 8px; }}
        QLineEdit[invalid="true"] {{ border: 2px solid {c['danger']}; }}
        QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled, QPlainTextEdit:disabled {{ color: {c['muted']}; background: {c['surface_alt']}; }}
        QComboBox::drop-down {{ width: 28px; border: 0; border-left: 1px solid {c['border_soft']}; }}
        QComboBox QAbstractItemView {{
            background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
            selection-background-color: {c['primary']}; selection-color: #ffffff; padding: 4px;
        }}

        QTableView, QTreeWidget, QListWidget, QTableWidget {{
            border: 1px solid {c['border']}; border-radius: 8px; background: {c['surface']};
            alternate-background-color: {c['surface_alt']}; gridline-color: {c['border_soft']};
            selection-background-color: {c['selection']}; selection-color: {c['selection_text']};
        }}
        QTreeWidget::item, QListWidget::item {{ padding: 6px; border: 0; }}
        QTreeWidget::item:hover, QListWidget::item:hover {{ background: {c['accent_soft']}; }}
        QListWidget#sectorList::item {{ margin: 2px 4px; padding: 0; background: transparent; }}
        QListWidget#sectorList::item:selected, QListWidget#sectorList::item:hover {{ background: transparent; color: inherit; }}
        QHeaderView::section {{
            min-height: 35px; padding: 6px 8px; background: {c['raised']}; color: {c['text']};
            font-weight: 750; border: 0; border-right: 1px solid {c['border_soft']};
            border-bottom: 1px solid {c['border']};
        }}
        QTableCornerButton::section {{ background: {c['raised']}; border: 0; border-bottom: 1px solid {c['border']}; }}

        QTabWidget::pane {{
            top: -1px; border: 1px solid {c['border']}; border-radius: 8px; background: {c['surface']};
        }}
        QTabBar::tab {{
            min-height: 34px; padding: 0 16px; margin-right: 3px; border: 1px solid {c['border']};
            border-bottom: 0; border-top-left-radius: 7px; border-top-right-radius: 7px;
            background: {c['raised']}; color: {c['muted']}; font-weight: 650;
        }}
        QTabBar::tab:hover {{ color: {c['text']}; border-color: {c['primary']}; }}
        QTabBar::tab:selected {{ background: {c['surface']}; color: {c['primary']}; border-top: 3px solid {c['primary']}; }}

        QGroupBox {{
            margin-top: 13px; padding: 15px 12px 10px 12px; border: 1px solid {c['border_soft']};
            border-radius: 8px; background: {c['surface_alt']}; font-weight: 700;
        }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 11px; padding: 0 6px; color: {c['text']}; }}
        QFrame#settingsPanel, QFrame#importDetails {{
            background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 9px;
        }}
        QFrame#importDetails {{ background: {c['surface_alt']}; }}
        QLabel#dialogTitle {{ font-size: 18px; font-weight: 800; color: {c['text']}; }}
        QLabel#detailTitle {{ font-size: 13px; font-weight: 750; color: {c['text']}; }}
        QLabel#helpText {{ color: {c['muted']}; }}
        QLabel#summaryBadge {{
            padding: 8px 12px; border: 1px solid {c['border']}; border-radius: 16px;
            background: {c['surface_alt']}; color: {c['text']}; font-weight: 750;
        }}
        QLabel#offlineNotice {{ background: {c['warning']}; color: #ffffff; padding: 8px 12px; font-weight: 750; }}
        QLabel#successLabel {{ color: {c['success']}; font-weight: 700; }}
        QLabel#errorLabel {{ color: {c['danger']}; font-weight: 700; }}

        QMenu {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px; }}
        QMenu::item {{ min-height: 30px; padding: 3px 24px 3px 10px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {c['primary']}; color: #ffffff; }}
        QMessageBox {{ background: {c['surface']}; }}
        QMessageBox QLabel {{ min-width: 300px; color: {c['text']}; }}
        QProgressBar {{ min-height: 18px; border: 1px solid {c['border']}; border-radius: 7px; background: {c['surface_alt']}; text-align: center; }}
        QProgressBar::chunk {{ background: {c['primary']}; border-radius: 6px; }}

        QScrollBar:vertical {{ width: 13px; margin: 2px; background: transparent; }}
        QScrollBar::handle:vertical {{ min-height: 34px; border-radius: 5px; background: {c['border']}; }}
        QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
        QScrollBar:horizontal {{ height: 13px; margin: 2px; background: transparent; }}
        QScrollBar::handle:horizontal {{ min-width: 34px; border-radius: 5px; background: {c['border']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

        QCheckBox {{ spacing: 7px; }}
        QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {c['border']}; border-radius: 4px; background: {c['surface']}; }}
        QCheckBox::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; }}
        QStatusBar {{ background: {c['surface']}; border-top: 1px solid {c['border_soft']}; color: {c['muted']}; }}
        QToolTip {{ color: #ffffff; background: #111827; border: 1px solid #64748b; padding: 6px; }}
        """
    )
    return mode
