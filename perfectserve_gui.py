import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTextEdit, QProgressBar, QFrame,
    QSizePolicy, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget,
    QGridLayout, QSpacerItem
)
from PySide6.QtCore import Qt, QProcess, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QTextCursor, QPainter

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import models

MODERN_STYLE = """
/* Global Settings */
QMainWindow {
    background-color: #F9FAFB;
}
QWidget {
    font-family: 'Inter', '-apple-system', 'Segoe UI', Arial, sans-serif;
    color: #101828;
}

/* Sidebar Styling */
QFrame#Sidebar {
    background-color: #FFFFFF;
    border-right: 1px solid #EAECF0;
}
QLabel#SidebarTitle {
    font-size: 16px;
    font-weight: 700;
    color: #101828;
    padding: 24px 16px 12px 16px;
}
QLabel#SectionLabel {
    font-size: 11px;
    font-weight: 600;
    color: #667085;
    padding: 16px 16px 4px 16px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Sidebar Navigation Items */
QListWidget {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    font-size: 14px;
    font-weight: 500;
    color: #344054;
    padding: 10px 12px;
    border-radius: 6px;
    margin: 2px 12px;
}
QListWidget::item:hover {
    background-color: #F9FAFB;
}
QListWidget::item:selected {
    background-color: #F2F4F7;
    color: #101828;
    font-weight: 600;
}

/* Profile Area */
QFrame#ProfileArea {
    border-top: 1px solid #EAECF0;
    background-color: #FFFFFF;
    padding: 16px;
}
QLabel#ProfileName {
    font-size: 14px;
    font-weight: 600;
    color: #101828;
}
QLabel#ProfileRole {
    font-size: 13px;
    font-weight: 400;
    color: #667085;
}

/* Main Content Area */
QWidget#MainContent {
    background-color: #F9FAFB;
}
QLabel#PageHeader {
    font-size: 30px;
    font-weight: 600;
    color: #101828;
}
QFrame#Card {
    background-color: #FFFFFF;
    border: 1px solid #EAECF0;
    border-radius: 12px;
}
QLabel#CardTitle {
    font-size: 18px;
    font-weight: 600;
    color: #101828;
}
QLabel#CardDesc {
    font-size: 14px;
    font-weight: 400;
    color: #667085;
}

/* Form Controls */
QLabel {
    font-size: 14px;
    font-weight: 500;
    color: #344054;
}
QComboBox, QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #D0D5DD;
    border-radius: 8px;
    padding: 10px 14px;
    color: #101828;
    font-size: 14px;
}
QComboBox:focus, QLineEdit:focus {
    border: 1px solid #1570EF;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #EAECF0;
    selection-background-color: #F9FAFB;
    selection-color: #101828;
    border-radius: 8px;
    outline: none;
}
QComboBox QAbstractItemView::item {
    padding: 8px;
}

/* Buttons */
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #D0D5DD;
    border-radius: 8px;
    color: #344054;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 16px;
}
QPushButton:hover {
    background-color: #F9FAFB;
    color: #101828;
}
QPushButton:pressed {
    background-color: #F2F4F7;
}
QPushButton:disabled {
    background-color: #F9FAFB;
    color: #D0D5DD;
    border: 1px solid #EAECF0;
}
QPushButton#PrimaryBtn {
    background-color: #1570EF;
    border: 1px solid #1570EF;
    color: #FFFFFF;
}
QPushButton#PrimaryBtn:hover {
    background-color: #175CD3;
    border: 1px solid #175CD3;
}
QPushButton#PrimaryBtn:pressed {
    background-color: #1849A9;
}
QPushButton#PrimaryBtn:disabled {
    background-color: #B3CCF5;
    border: 1px solid #B3CCF5;
}

/* Process Console */
QTextEdit#Console {
    background-color: #101828;
    color: #E5E7EB;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    border: 1px solid #EAECF0;
    border-radius: 8px;
    padding: 16px;
}

QProgressBar {
    background-color: #F2F4F7;
    border-radius: 4px;
    text-align: center;
    color: transparent;
    border: none;
    height: 6px;
}
QProgressBar::chunk {
    background-color: #1570EF;
    border-radius: 3px;
}
"""

class ModernGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PerfectServe Scraper & PDF Generator")
        self.resize(1100, 750)
        self.setStyleSheet(MODERN_STYLE)

        self.process = None

        self.setup_ui()
        self.load_teams()
        self.populate_months()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==========================================
        # LEFT SIDEBAR
        # ==========================================
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        title_label = QLabel("Calendar Tools")
        title_label.setObjectName("SidebarTitle")
        sidebar_layout.addWidget(title_label)

        section_general = QLabel("GENERAL")
        section_general.setObjectName("SectionLabel")
        sidebar_layout.addWidget(section_general)

        self.nav_list = QListWidget()
        self.nav_list.setFocusPolicy(Qt.NoFocus)
        self.nav_list.addItem("Dashboard")
        self.nav_list.addItem("Logs & Console")
        self.nav_list.addItem("Settings")
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self.switch_page)
        sidebar_layout.addWidget(self.nav_list)
        
        # Spacer
        sidebar_layout.addStretch()

        # Bottom Profile
        profile_area = QFrame()
        profile_area.setObjectName("ProfileArea")
        profile_layout = QHBoxLayout(profile_area)
        profile_layout.setContentsMargins(16, 16, 16, 16)
        
        profile_text_layout = QVBoxLayout()
        name_label = QLabel("Admin User")
        name_label.setObjectName("ProfileName")
        role_label = QLabel("Nephrology Associates")
        role_label.setObjectName("ProfileRole")
        profile_text_layout.addWidget(name_label)
        profile_text_layout.addWidget(role_label)
        
        profile_layout.addLayout(profile_text_layout)
        sidebar_layout.addWidget(profile_area)

        main_layout.addWidget(sidebar)

        # ==========================================
        # RIGHT CONTENT AREA
        # ==========================================
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("MainContent")
        main_layout.addWidget(self.content_stack)

        # Page 0: Dashboard
        page_dash = QWidget()
        page_dash.setObjectName("MainContent")
        dash_layout = QVBoxLayout(page_dash)
        dash_layout.setContentsMargins(40, 40, 40, 40)
        dash_layout.setSpacing(24)

        header_layout = QHBoxLayout()
        header_title = QLabel("Dashboard")
        header_title.setObjectName("PageHeader")
        header_layout.addWidget(header_title)
        
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("color: #667085; font-weight: 500;")
        header_layout.addWidget(self.status_label, alignment=Qt.AlignRight | Qt.AlignVCenter)
        
        dash_layout.addLayout(header_layout)

        # Card: Scraper Settings
        settings_card = QFrame()
        settings_card.setObjectName("Card")
        sc_layout = QVBoxLayout(settings_card)
        sc_layout.setContentsMargins(24, 24, 24, 24)
        sc_layout.setSpacing(16)

        sc_title = QLabel("Scraper Configuration")
        sc_title.setObjectName("CardTitle")
        sc_desc = QLabel("Select the team and month you want to generate the calendar for.")
        sc_desc.setObjectName("CardDesc")
        sc_layout.addWidget(sc_title)
        sc_layout.addWidget(sc_desc)

        sc_layout.addSpacing(8)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(20)

        # Team field
        team_layout = QVBoxLayout()
        team_layout.addWidget(QLabel("Target Team"))
        self.team_combo = QComboBox()
        self.team_combo.setFixedHeight(44)
        team_layout.addWidget(self.team_combo)
        form_layout.addLayout(team_layout)

        # Month field
        month_layout = QVBoxLayout()
        month_layout.addWidget(QLabel("Target Month"))
        self.month_combo = QComboBox()
        self.month_combo.setFixedHeight(44)
        month_layout.addWidget(self.month_combo)
        form_layout.addLayout(month_layout)

        sc_layout.addLayout(form_layout)
        dash_layout.addWidget(settings_card)

        # Card: Actions
        actions_card = QFrame()
        actions_card.setObjectName("Card")
        ac_layout = QVBoxLayout(actions_card)
        ac_layout.setContentsMargins(24, 24, 24, 24)
        ac_layout.setSpacing(16)

        ac_title = QLabel("Workflow Actions")
        ac_title.setObjectName("CardTitle")
        ac_desc = QLabel("Execute the PerfectServe automated pipeline in order.")
        ac_desc.setObjectName("CardDesc")
        ac_layout.addWidget(ac_title)
        ac_layout.addWidget(ac_desc)
        ac_layout.addSpacing(8)

        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(12)

        self.btn_auth = QPushButton("Authenticate Session")
        self.btn_auth.setToolTip("Log in to PerfectServe using the headless browser")
        self.btn_auth.clicked.connect(self.run_auth)
        self.btn_auth.setFixedHeight(44)

        self.btn_scrape = QPushButton("Scrape Shifts")
        self.btn_scrape.setObjectName("PrimaryBtn")  # Primary focus
        self.btn_scrape.setToolTip("Extract shifts for the selected configuration")
        self.btn_scrape.clicked.connect(self.run_scrape)
        self.btn_scrape.setFixedHeight(44)

        self.btn_pdf = QPushButton("Generate PDFs")
        self.btn_pdf.setToolTip("Process scraped JSON into final visual PDFs")
        self.btn_pdf.clicked.connect(self.run_pdf)
        self.btn_pdf.setFixedHeight(44)

        btns_layout.addWidget(self.btn_auth)
        btns_layout.addWidget(self.btn_scrape)
        btns_layout.addWidget(self.btn_pdf)
        ac_layout.addLayout(btns_layout)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        ac_layout.addWidget(self.progress)
        
        dash_layout.addWidget(actions_card)
        dash_layout.addStretch()

        self.content_stack.addWidget(page_dash)

        # Page 1: Logs
        page_logs = QWidget()
        page_logs.setObjectName("MainContent")
        logs_layout = QVBoxLayout(page_logs)
        logs_layout.setContentsMargins(40, 40, 40, 40)
        logs_layout.setSpacing(24)

        logs_header = QLabel("Execution Logs")
        logs_header.setObjectName("PageHeader")
        logs_layout.addWidget(logs_header)

        self.console = QTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        logs_layout.addWidget(self.console)

        self.content_stack.addWidget(page_logs)

        # Page 2: Settings (Placeholder)
        page_settings = QWidget()
        page_settings.setObjectName("MainContent")
        set_layout = QVBoxLayout(page_settings)
        set_layout.setContentsMargins(40, 40, 40, 40)
        set_header = QLabel("Settings")
        set_header.setObjectName("PageHeader")
        set_layout.addWidget(set_header)
        set_desc = QLabel("There are currently no additional settings for the standalone scraper.")
        set_desc.setObjectName("CardDesc")
        set_layout.addWidget(set_desc)
        set_layout.addStretch()
        self.content_stack.addWidget(page_settings)


    def switch_page(self, row):
        self.content_stack.setCurrentIndex(row)

    def load_teams(self):
        try:
            teams = models.get_team_names()
            self.team_combo.addItems(sorted(teams))
        except Exception as e:
            self.team_combo.addItems(["Team 1", "Team 4", "Team 6"])

    def populate_months(self):
        now = datetime.now()
        for i in range(-1, 12):
            dt = now + timedelta(days=30 * i)
            first_day = dt.replace(day=1)
            name = first_day.strftime("%B %Y")
            if self.month_combo.findText(name) == -1:
                self.month_combo.addItem(name, first_day)
        
        current_name = now.replace(day=1).strftime("%B %Y")
        idx = self.month_combo.findText(current_name)
        if idx >= 0:
            self.month_combo.setCurrentIndex(idx)

    def log(self, message, color="#D1D5DB"):
        # Auto-switch to logs page on first real log action (if idle)
        if self.status_label.text() != "Status: Idle" and self.content_stack.currentIndex() == 0:
            # We can optionally flip them to logs, but it might be annoying. Let's just update label.
            pass

        self.console.moveCursor(QTextCursor.End)
        self.console.insertHtml(f'<span style="color:{color};">{message}<br></span>')
        self.console.moveCursor(QTextCursor.End)

    def set_buttons_enabled(self, enabled):
        self.btn_auth.setEnabled(enabled)
        self.btn_scrape.setEnabled(enabled)
        self.btn_pdf.setEnabled(enabled)
        self.team_combo.setEnabled(enabled)
        self.month_combo.setEnabled(enabled)
        
        if not enabled:
            self.progress.show()
            self.status_label.setText("Status: Running...")
            self.status_label.setStyleSheet("color: #1570EF; font-weight: 600;")
        else:
            self.progress.hide()
            self.status_label.setText("Status: Ready")
            self.status_label.setStyleSheet("color: #12B76A; font-weight: 600;")

    def start_process(self, command, args, cwd=None):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.log("A process is already running!", color="#F04438")
            return

        # self.console.clear()
        self.set_buttons_enabled(False)
        self.log(f"<br><b>🚀 Starting: {command} {' '.join(args)}</b>", color="#6CE9A6")

        self.process = QProcess()
        if cwd:
            self.process.setWorkingDirectory(cwd)
            
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.start(command, args)
        
        # Optionally switch to logs view
        self.nav_list.setCurrentRow(1)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        lines = bytearray(data).decode("utf-8", errors="replace").splitlines()
        for line in lines:
            if line.strip():
                if "❌" in line or "Error" in line:
                    self.log(line, color="#F04438")
                elif "✅" in line or "Success" in line or "🎉" in line:
                    self.log(line, color="#12B76A")
                else:
                    self.log(line, color="#D1D5DB")

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        lines = bytearray(data).decode("utf-8", errors="replace").splitlines()
        for line in lines:
            if line.strip():
                self.log(line, color="#F79009")

    def process_finished(self, exitCode, exitStatus):
        self.set_buttons_enabled(True)
        if exitStatus == QProcess.CrashExit:
            self.log(f"💥 Process crashed (Exit Code: {exitCode})", color="#F04438")
        elif exitCode != 0:
            self.log(f"⚠️ Process finished with errors (Exit Code: {exitCode})", color="#F79009")
        else:
            self.log(f"✨ Process completed successfully!", color="#12B76A")
        self.process = None

    def run_auth(self):
        cwd = str(Path(__file__).parent)
        auth_script = str(Path(cwd) / "scraper" / "setup-auth.js")
        self.start_process("node", [auth_script], cwd=cwd)

    def run_scrape(self):
        cwd = str(Path(__file__).parent)
        scrape_script = str(Path(cwd) / "scraper" / "scrape-shifts.js")
        team_name = self.team_combo.currentText()
        team_prefix = team_name.replace(" ", "")
        if "-" in team_prefix:
            team_prefix = team_prefix.split("-")[0].strip()
        if team_prefix.lower().startswith("team"):
            num = team_prefix[4:]
            team_prefix = f"Team{num}"
        month_str = self.month_combo.currentText()
        self.start_process("node", [scrape_script, team_prefix, month_str], cwd=cwd)

    def run_pdf(self):
        cwd = str(Path(__file__).parent)
        pdf_script = str(Path(cwd) / "backend_pdf_generator.py")
        team_name = self.team_combo.currentText()
        
        # Script expects "team-1" format by default
        if team_name.lower().startswith("team"):
            team_arg = team_name.lower().replace(" ", "-") # Team 1 -> team-1
        else:
            team_arg = team_name.lower().replace(" ", "-")
            
        team_prefix = team_name.replace(" ", "")
        if "-" in team_prefix:
            team_prefix = team_prefix.split("-")[0].strip()
        if team_prefix.lower().startswith("team"):
            num = team_prefix[4:]
            team_prefix = f"Team{num}"
            
        # Extract year and month
        first_day = self.month_combo.currentData()
        year_str = str(first_day.year)
        month_str = str(first_day.month)

        raw_month_str = self.month_combo.currentText()
        clean_month = raw_month_str.replace(" ", "")
        json_file_name = f"{team_prefix}-{clean_month}-shifts.json"
        json_path = str(Path(cwd) / "scraper" / json_file_name)

        self.start_process("python", [pdf_script, "--team", team_arg, "--year", year_str, "--month", month_str, "--json-file", json_path], cwd=cwd)


def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    window = ModernGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
