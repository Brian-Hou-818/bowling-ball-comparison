import sys
import re
import urllib.parse
import numpy as np
import requests
from bs4 import BeautifulSoup

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QLineEdit, QFormLayout, QDialog, QSplitter, QTabWidget, QGroupBox,
    QCheckBox, QMessageBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

import matplotlib

matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# ----------------------------------------------------------------------
# Web Scraper Worker Thread (Keeps UI responsive while scraping)
# ----------------------------------------------------------------------
from duckduckgo_search import DDGS


class BallScraperThread(QThread):
    finished_signal = pyqtSignal(dict, str)  # Emits (ball_dict, error_message)

    def __init__(self, query_name):
        super().__init__()
        self.query_name = query_name

    def run(self):
        try:
            # Search DuckDuckGo using the DDGS client
            search_query = f"{self.query_name} bowling ball specs rg differential coverstock"
            snippets = []

            with DDGS() as ddgs:
                results = ddgs.text(search_query, max_results=5)
                for r in results:
                    snippets.append(r.get('body', '') + ' ' + r.get('title', ''))

            full_text = " ".join(snippets).lower()

            if not full_text.strip():
                self.finished_signal.emit({}, f"No specs found online for '{self.query_name}'.")
                return

            # Extract Technical Parameters via Regex
            rg_match = re.search(r'(?:rg|radius of gyration)[^\d]*([2]\.[4-6]\d)', full_text)
            rg_val = float(rg_match.group(1)) if rg_match else 2.50

            diff_match = re.search(r'(?:diff|differential)[^\d]*(0\.0[1-6]\d)', full_text)
            diff_val = float(diff_match.group(1)) if diff_match else 0.045

            int_diff_match = re.search(r'(?:int diff|intermediate differential|bias)[^\d]*(0\.0[0-3]\d)', full_text)
            int_diff_val = float(int_diff_match.group(1)) if int_diff_match else 0.000

            # Coverstock Detection
            cover_type = "Solid Reactive"
            if "pearl" in full_text:
                cover_type = "Pearl Reactive"
            elif "hybrid" in full_text:
                cover_type = "Hybrid Reactive"
            elif "urethane" in full_text:
                cover_type = "Urethane"
            elif "polyester" in full_text or "plastic" in full_text:
                cover_type = "Polyester / Spare"

            # Core Architecture Detection
            core_type = "Asymmetrical" if (
                        int_diff_val > 0.005 or "asymmetric" in full_text or "asym" in full_text) else "Symmetrical"

            # Brand Detection
            brands = ["Storm", "Hammer", "Motiv", "Roto Grip", "Brunswick", "900 Global", "Ebonite", "Track",
                      "Columbia 300", "Radical"]
            detected_brand = "Custom / Brand"
            for b in brands:
                if b.lower() in full_text or b.lower() in self.query_name.lower():
                    detected_brand = b
                    break

            # Estimate performance ratings
            hook_est = min(10.0, max(2.0, (diff_val * 120.0) + (10 - (rg_val - 2.40) * 30)))
            length_est = min(10.0, max(2.0, (rg_val - 2.40) * 40.0))
            angularity_est = 8.5 if "Pearl" in cover_type else (6.0 if "Solid" in cover_type else 4.0)
            oil_est = 9.0 if "Solid" in cover_type else (6.5 if "Pearl" in cover_type else 5.0)

            parsed_ball = {
                "id": str(np.random.randint(1000, 9999)),
                "brand": detected_brand,
                "name": self.query_name.title(),
                "cover": cover_type,
                "cover_name": f"{cover_type} (Scraped)",
                "core": core_type,
                "rg": rg_val,
                "diff": diff_val,
                "int_diff": int_diff_val,
                "finish": "Factory Finish",
                "hook": round(hook_est, 1),
                "length": round(length_est, 1),
                "angularity": round(angularity_est, 1),
                "oil": round(oil_est, 1),
                "color": "#" + "".join([np.random.choice(list('0123456789ABCDEF')) for _ in range(6)])
            }

            self.finished_signal.emit(parsed_ball, "")

        except Exception as e:
            self.finished_signal.emit({}, f"Search failed: {str(e)}")

# ----------------------------------------------------------------------
# Initial Ball Database
# ----------------------------------------------------------------------
DEFAULT_BALLS = [
    {
        "id": "1", "brand": "Storm", "name": "Phaze II", "cover": "Solid Reactive",
        "cover_name": "TX-16 Solid", "core": "Symmetrical", "rg": 2.48, "diff": 0.051,
        "int_diff": 0.000, "finish": "3000-grit Abralon", "hook": 8.5, "length": 5.5,
        "angularity": 6.5, "oil": 8.0, "color": "#00d2ff"
    },
    {
        "id": "2", "brand": "Hammer", "name": "Black Widow 3.0", "cover": "Solid Reactive",
        "cover_name": "HK22 - Cohesion Solid", "core": "Asymmetrical", "rg": 2.50, "diff": 0.058,
        "int_diff": 0.016, "finish": "2000-grit Siaair", "hook": 9.5, "length": 4.5,
        "angularity": 8.0, "oil": 9.5, "color": "#ff3366"
    },
    {
        "id": "3", "brand": "Motiv", "name": "Venom Shock", "cover": "Solid Reactive",
        "cover_name": "Turmoil MFK Solid", "core": "Symmetrical", "rg": 2.48, "diff": 0.034,
        "int_diff": 0.000, "finish": "4000-grit LSS", "hook": 6.5, "length": 6.0,
        "angularity": 5.5, "oil": 6.0, "color": "#00ff88"
    }
]

OIL_PATTERNS = {
    "Heavy Oil (44ft, High Volume)": {"skid_mult": 1.25, "hook_mult": 0.75, "oil_length": 44},
    "Medium Oil / House Pattern (40ft)": {"skid_mult": 1.00, "hook_mult": 1.00, "oil_length": 40},
    "Dry Oil / Transitioned (36ft, Low Vol)": {"skid_mult": 0.80, "hook_mult": 1.25, "oil_length": 36}
}


# ----------------------------------------------------------------------
# Matplotlib Plot Widgets
# ----------------------------------------------------------------------
class RadarChartCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 4), facecolor='#1e1e24')
        self.ax = self.fig.add_subplot(111, polar=True)
        self.ax.set_facecolor('#1e1e24')
        super().__init__(self.fig)

    def update_chart(self, selected_balls):
        self.ax.clear()
        categories = ['Hook Potential', 'Skid Length', 'Backend Angularity', 'Oil Traction', 'Versatility']
        N = len(categories)
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        angles += angles[:1]

        self.ax.set_theta_offset(np.pi / 2)
        self.ax.set_theta_direction(-1)
        self.ax.set_xticks(angles[:-1])
        self.ax.set_xticklabels(categories, color='#e0e0e0', fontsize=8, fontweight='bold')
        self.ax.set_rlabel_position(0)
        self.ax.set_yticks([2, 4, 6, 8, 10])
        self.ax.set_yticklabels(["2", "4", "6", "8", "10"], color='#888888', fontsize=7)
        self.ax.set_ylim(0, 10)
        self.ax.grid(True, color='#333340', linestyle='--')

        for ball in selected_balls:
            versatility = 10 - abs(ball['rg'] - 2.50) * 40 - abs(ball['diff'] - 0.045) * 50
            versatility = max(3.0, min(9.5, versatility))

            values = [ball['hook'], ball['length'], ball['angularity'], ball['oil'], versatility]
            values += values[:1]
            color = ball.get('color', '#00d2ff')

            self.ax.plot(angles, values, linewidth=2, linestyle='solid', label=f"{ball['brand']} {ball['name']}",
                         color=color)
            self.ax.fill(angles, values, color=color, alpha=0.15)

        if selected_balls:
            self.ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), facecolor='#2a2a36', edgecolor='none',
                           labelcolor='white', fontsize=7)
        self.fig.tight_layout()
        self.draw()


class QuadrantPlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 4), facecolor='#1e1e24')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e24')
        super().__init__(self.fig)

    def update_chart(self, all_balls, selected_ids):
        self.ax.clear()
        self.ax.set_title("RG vs. Differential Dynamics", color='#e0e0e0', fontsize=10, fontweight='bold')
        self.ax.set_xlabel("Radius of Gyration (RG) -> Higher Skid", color='#aaaaaa', fontsize=8)
        self.ax.set_ylabel("Differential -> Higher Flare", color='#aaaaaa', fontsize=8)

        self.ax.set_xlim(2.45, 2.60)
        self.ax.set_ylim(0.010, 0.065)
        self.ax.axvline(x=2.51, color='#444455', linestyle='--')
        self.ax.axhline(y=0.040, color='#444455', linestyle='--')

        self.ax.tick_params(colors='#888888', labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color('#333340')

        for ball in all_balls:
            is_selected = ball['id'] in selected_ids
            color = ball.get('color', '#00d2ff') if is_selected else '#444455'
            size = 120 if is_selected else 40
            alpha = 1.0 if is_selected else 0.4

            self.ax.scatter(ball['rg'], ball['diff'], color=color, s=size, alpha=alpha,
                            edgecolors='white' if is_selected else 'none', zorder=3 if is_selected else 2)
            if is_selected:
                self.ax.annotate(f"{ball['name']}", (ball['rg'], ball['diff']), xytext=(5, 5),
                                 textcoords='offset points', color='white', fontsize=8, fontweight='bold')

        self.fig.tight_layout()
        self.draw()


class LaneTrajectoryCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 2.8), facecolor='#1e1e24')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e24')
        super().__init__(self.fig)

    def update_chart(self, selected_balls, pattern_key):
        self.ax.clear()
        pattern = OIL_PATTERNS.get(pattern_key, OIL_PATTERNS["Medium Oil / House Pattern (40ft)"])

        self.ax.set_xlim(-2, 64)
        self.ax.set_ylim(0, 40)
        self.ax.set_facecolor('#1a1008')

        oil_len = pattern['oil_length']
        self.ax.add_patch(matplotlib.patches.Rectangle((0, 5), oil_len, 30, color='#0066cc', alpha=0.25,
                                                       label=f"Oil Pattern ({oil_len}ft)"))
        self.ax.axvline(x=oil_len, color='#0099ff', linestyle=':', alpha=0.6)

        self.ax.axvline(x=0, color='#cc0000', linewidth=2)
        self.ax.scatter([60] * 10, [20, 17, 23, 14, 20, 26, 11, 17, 23, 29], color='#e0e0e0', s=15, zorder=4)

        start_x, start_y = 0.0, 15.0
        arrow_x, arrow_y = 20.0, 10.0

        for ball in selected_balls:
            skid_dist = (ball['length'] * 4.5 + ball['rg'] * 5.0) * pattern['skid_mult']
            breakpoint_x = min(52.0, max(30.0, skid_dist))
            breakpoint_y = arrow_y - ((arrow_y - start_y) / arrow_x) * (breakpoint_x - arrow_x) - (
                1.5 if "Asymmetrical" in ball['core'] else 0.5)

            hook_power = (ball['hook'] * 1.1 + ball['diff'] * 60) * pattern['hook_mult']
            entry_y = breakpoint_y + (hook_power * 0.85)
            entry_y = min(20.5, max(12.0, entry_y))

            t = np.linspace(0, 1, 100)
            x_path = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * breakpoint_x + t ** 2 * 60.0
            y_path = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * breakpoint_y + t ** 2 * entry_y

            color = ball.get('color', '#00d2ff')
            self.ax.plot(x_path, y_path, linewidth=2.5, color=color, label=f"{ball['brand']} {ball['name']}")
            self.ax.scatter([breakpoint_x], [breakpoint_y], color=color, s=30, marker='x', zorder=5)

        self.ax.set_xticks([0, 15, 30, 45, 60])
        self.ax.set_xticklabels(
            ['Foul Line (0\')', 'Arrows (15\')', 'Mid-Lane (30\')', 'Breakpoint (45\')', 'Pins (60\')'],
            color='#888888', fontsize=8)
        self.ax.set_yticks([5, 10, 15, 20, 25, 30, 35])
        self.ax.set_yticklabels(['5', '10', '15', '20', '25', '30', '35'], color='#888888', fontsize=8)

        for spine in self.ax.spines.values():
            spine.set_color('#333340')

        if selected_balls:
            self.ax.legend(loc='upper left', facecolor='#2a2a36', edgecolor='none', labelcolor='white', fontsize=7)

        self.fig.tight_layout()
        self.draw()


# ----------------------------------------------------------------------
# Main Application Window
# ----------------------------------------------------------------------
class BowlingBallApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro-Track Bowling Ball Specs & Online Scraper")
        self.resize(1280, 850)

        self.balls = list(DEFAULT_BALLS)
        self.selected_ids = ["1", "2"]

        self.init_ui()
        self.apply_stylesheet()
        self.update_all_views()

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #121216; }
            QWidget { color: #e0e0e0; font-family: 'Segoe UI', Arial, sans-serif; }
            QGroupBox { font-weight: bold; border: 1px solid #2a2a36; border-radius: 6px; margin-top: 10px; padding-top: 10px; background-color: #1e1e24; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #00d2ff; }
            QTableWidget { background-color: #181820; gridline-color: #2a2a36; border: 1px solid #2a2a36; border-radius: 4px; }
            QHeaderView::section { background-color: #252530; color: #00d2ff; font-weight: bold; border: none; padding: 4px; }
            QLineEdit, QComboBox { background-color: #252530; color: white; border: 1px solid #3a3a4c; padding: 6px; border-radius: 4px; }
            QPushButton { background-color: #252530; color: #00d2ff; border: 1px solid #00d2ff; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #00d2ff; color: #101014; }
            QTabWidget::pane { border: 1px solid #2a2a36; background: #1e1e24; }
            QTabBar::tab { background: #181820; color: #aaa; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #252530; color: #00d2ff; font-weight: bold; border-bottom: 2px solid #00d2ff; }
        """)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Left Panel: Ball Database & Online Search
        left_panel = QGroupBox("Ball Database Catalog")
        left_layout = QVBoxLayout(left_panel)

        # Online Spec Lookup Section
        lookup_box = QGroupBox("Online Ball Lookup (Web Scraper)")
        lookup_layout = QVBoxLayout(lookup_box)

        self.web_search_in = QLineEdit()
        self.web_search_in.setPlaceholderText("Type ball name (e.g. Optimum Idol, Harsh Reality)...")
        self.web_search_in.returnPressed.connect(self.scrape_ball_online)
        lookup_layout.addWidget(self.web_search_in)

        btn_scrape = QPushButton("🔍 Search Online & Add Specs")
        btn_scrape.clicked.connect(self.scrape_ball_online)
        lookup_layout.addWidget(btn_scrape)

        left_layout.addWidget(lookup_box)

        # Table Filters
        filter_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter local catalog...")
        self.search_box.textChanged.connect(self.filter_database)
        filter_layout.addWidget(self.search_box)

        self.brand_filter = QComboBox()
        self.brand_filter.addItems(["All Brands", "Storm", "Hammer", "Motiv", "Roto Grip", "Brunswick"])
        self.brand_filter.currentTextChanged.connect(self.filter_database)
        filter_layout.addWidget(self.brand_filter)

        left_layout.addLayout(filter_layout)

        # Ball Table
        self.db_table = QTableWidget()
        self.db_table.setColumnCount(5)
        self.db_table.setHorizontalHeaderLabels(["Compare", "Brand", "Model", "Core", "Cover"])
        self.db_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.db_table)

        # Right Panel: Tabs
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.tabs = QTabWidget()

        # Tab 1: Comparison Matrix
        self.tab_matrix = QWidget()
        matrix_layout = QVBoxLayout(self.tab_matrix)
        self.matrix_table = QTableWidget()
        matrix_layout.addWidget(self.matrix_table)

        self.gap_box = QGroupBox("Arsenal Structure & Gap Analysis")
        gap_layout = QVBoxLayout(self.gap_box)
        self.gap_label = QLabel("Select balls to evaluate coverage...")
        self.gap_label.setWordWrap(True)
        gap_layout.addWidget(self.gap_label)
        matrix_layout.addWidget(self.gap_box)
        self.tabs.addTab(self.tab_matrix, "Spec Matrix & Gaps")

        # Tab 2: Visual Charts
        self.tab_charts = QWidget()
        charts_layout = QHBoxLayout(self.tab_charts)
        self.radar_canvas = RadarChartCanvas(self)
        self.quadrant_canvas = QuadrantPlotCanvas(self)
        charts_layout.addWidget(self.radar_canvas)
        charts_layout.addWidget(self.quadrant_canvas)
        self.tabs.addTab(self.tab_charts, "Radar & Core Dynamics")

        # Tab 3: Lane Simulator
        self.tab_lane = QWidget()
        lane_layout = QVBoxLayout(self.tab_lane)
        pattern_control_layout = QHBoxLayout()
        pattern_control_layout.addWidget(QLabel("Oil Pattern Profile:"))
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems(list(OIL_PATTERNS.keys()))
        self.pattern_combo.currentTextChanged.connect(self.update_lane_simulation)
        pattern_control_layout.addWidget(self.pattern_combo)
        pattern_control_layout.addStretch()
        lane_layout.addLayout(pattern_control_layout)
        self.lane_canvas = LaneTrajectoryCanvas(self)
        lane_layout.addWidget(self.lane_canvas)
        self.tabs.addTab(self.tab_lane, "Lane Motion Trajectory")

        right_layout.addWidget(self.tabs)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([450, 830])

        main_layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Online Web Scraper Slot
    # ------------------------------------------------------------------
    def scrape_ball_online(self):
        query = self.web_search_in.text().strip()
        if not query:
            QMessageBox.information(self, "Input Required", "Please type a bowling ball name to search online.")
            return

        # Show loading dialog
        self.progress = QProgressDialog(f"Searching online specs for '{query}'...", None, 0, 0, self)
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.show()

        # Start thread
        self.thread = BallScraperThread(query)
        self.thread.finished_signal.connect(self.handle_scrape_results)
        self.thread.start()

    def handle_scrape_results(self, ball_data, error_msg):
        self.progress.close()
        if error_msg:
            QMessageBox.warning(self, "Scrape Failed", error_msg)
            return

        # Add ball to list and auto-select
        self.balls.append(ball_data)
        if len(self.selected_ids) < 4:
            self.selected_ids.append(ball_data['id'])

        self.web_search_in.clear()
        QMessageBox.information(
            self,
            "Ball Scraped Successfully",
            f"Retrieved specs for {ball_data['brand']} {ball_data['name']}:\n"
            f"• RG: {ball_data['rg']}\n"
            f"• Differential: {ball_data['diff']}\n"
            f"• Cover: {ball_data['cover']}\n"
            f"• Core: {ball_data['core']}"
        )
        self.update_all_views()

    # ------------------------------------------------------------------
    # View Updates
    # ------------------------------------------------------------------
    def filter_database(self):
        query = self.search_box.text().lower()
        brand = self.brand_filter.currentText()

        self.db_table.setRowCount(0)
        filtered = [
            b for b in self.balls
            if (query in b['name'].lower() or query in b['brand'].lower())
               and (brand == "All Brands" or b['brand'] == brand)
        ]

        self.db_table.setRowCount(len(filtered))
        for row, ball in enumerate(filtered):
            chk = QCheckBox()
            chk.setChecked(ball['id'] in self.selected_ids)
            chk.stateChanged.connect(lambda state, b_id=ball['id']: self.toggle_selection(b_id, state))

            self.db_table.setCellWidget(row, 0, chk)
            self.db_table.setItem(row, 1, QTableWidgetItem(ball['brand']))
            self.db_table.setItem(row, 2, QTableWidgetItem(ball['name']))
            self.db_table.setItem(row, 3, QTableWidgetItem(ball['core']))
            self.db_table.setItem(row, 4, QTableWidgetItem(ball['cover']))

    def toggle_selection(self, ball_id, state):
        if state == 2:
            if len(self.selected_ids) >= 4:
                QMessageBox.warning(self, "Limit Reached", "You can compare up to 4 bowling balls simultaneously.")
                self.filter_database()
                return
            if ball_id not in self.selected_ids:
                self.selected_ids.append(ball_id)
        else:
            if ball_id in self.selected_ids:
                self.selected_ids.remove(ball_id)
        self.update_all_views()

    def update_all_views(self):
        selected_balls = [b for b in self.balls if b['id'] in self.selected_ids]
        self.filter_database()
        self.update_matrix_table(selected_balls)
        self.update_gap_analysis(selected_balls)
        self.radar_canvas.update_chart(selected_balls)
        self.quadrant_canvas.update_chart(self.balls, self.selected_ids)
        self.lane_canvas.update_chart(selected_balls, self.pattern_combo.currentText())

    def update_matrix_table(self, selected_balls):
        self.matrix_table.clear()
        if not selected_balls:
            self.matrix_table.setRowCount(0)
            self.matrix_table.setColumnCount(0)
            return

        specs = [
            ("Brand", "brand"),
            ("Coverstock Type", "cover"),
            ("Cover Name", "cover_name"),
            ("Core Architecture", "core"),
            ("Radius of Gyration (RG)", "rg"),
            ("Differential", "diff"),
            ("Intermediate Diff", "int_diff"),
            ("Hook Potential", "hook"),
            ("Length/Skid", "length"),
            ("Angularity", "angularity"),
            ("Oil Traction", "oil"),
        ]

        self.matrix_table.setRowCount(len(specs))
        self.matrix_table.setColumnCount(len(selected_balls))

        headers = [f"{b['brand']}\n{b['name']}" for b in selected_balls]
        self.matrix_table.setHorizontalHeaderLabels(headers)
        self.matrix_table.setVerticalHeaderLabels([s[0] for s in specs])
        self.matrix_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for col, ball in enumerate(selected_balls):
            for row, (_, key) in enumerate(specs):
                item = QTableWidgetItem(str(ball[key]))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.matrix_table.setItem(row, col, item)

    def update_gap_analysis(self, selected_balls):
        if not selected_balls:
            self.gap_label.setText("Select 1 to 4 balls to inspect arsenal gaps.")
            return

        has_heavy_solid = any("Solid" in b['cover'] and b['oil'] >= 8.0 for b in selected_balls)
        has_benchmark = any(
            "Solid" in b['cover'] and b['core'] == "Symmetrical" and 2.47 <= b['rg'] <= 2.51 for b in selected_balls)
        has_pearl_angular = any("Pearl" in b['cover'] and b['angularity'] >= 7.5 for b in selected_balls)

        insights = []
        insights.append(
            "<b style='color:#00ff88;'>✔ Heavy Oil Traction</b>" if has_heavy_solid else "<b style='color:#ff5555;'>⚠ Gap - Heavy Oil:</b> Missing strong solid coverstock.")
        insights.append(
            "<b style='color:#00ff88;'>✔ Benchmark Ball</b>" if has_benchmark else "<b style='color:#ffaa00;'>⚠ Gap - Benchmark:</b> Missing classic symmetrical benchmark ball.")
        insights.append(
            "<b style='color:#00ff88;'>✔ Late Skid/Flip</b>" if has_pearl_angular else "<b style='color:#ffaa00;'>⚠ Gap - Angularity:</b> Missing high-angularity pearl ball.")

        self.gap_label.setText("<br>".join(insights))

    def update_lane_simulation(self):
        selected_balls = [b for b in self.balls if b['id'] in self.selected_ids]
        self.lane_canvas.update_chart(selected_balls, self.pattern_combo.currentText())


# ----------------------------------------------------------------------
# Application Entry Point
# ----------------------------------------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = BowlingBallApp()
    window.show()
    sys.exit(app.exec())