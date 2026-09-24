import sys
import os
import re
import json
import requests
from bs4 import BeautifulSoup
import numpy as np

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QLineEdit,
    QGroupBox,
    QCheckBox,
    QMessageBox,
    QProgressDialog,
    QAbstractItemView,
    QMenu,
    QSplitter,
    QTabWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction

import matplotlib

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Playwright for fallback rendering if requests is blocked
try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# ----------------------------------------------------------------------
# Shortening & Formatting Helpers
# ----------------------------------------------------------------------
def simplify_cover(cover_text):
    cover_lower = str(cover_text).lower()
    if "urethane" in cover_lower:
        return "urethane"
    if "pearl" in cover_lower:
        return "pearl"
    if "hybrid" in cover_lower:
        return "hybrid"
    if "solid" in cover_lower:
        return "solid"
    if "plastic" in cover_lower or "polyester" in cover_lower:
        return "plastic"
    return cover_lower.split()[0] if cover_lower else "reactive"


def simplify_core(core_text, int_diff=0.0):
    core_lower = str(core_text).lower()
    if "asymmetrical" in core_lower or "asymmetric" in core_lower or "asym" in core_lower or int_diff > 0.005:
        return "asym"
    return "sym"


def simplify_oil(oil_text):
    return str(oil_text).replace(" Oil", "").replace(" oil", "").strip()


def estimate_resin_strength(cover_type):
    cover_lower = str(cover_type).lower()
    if "urethane" in cover_lower:
        return 2.5
    if "pearl" in cover_lower:
        return 4.5
    if "hybrid" in cover_lower:
        return 6.5
    if "solid" in cover_lower:
        return 9.0
    return 5.0


def determine_preferred_oil(cover_type, finish_text, core_type, int_diff):
    cover_lower = str(cover_type).lower()
    finish_lower = str(finish_text).lower()

    if "solid" in cover_lower or "urethane" in cover_lower:
        if any(g in finish_lower for g in ["500", "1000", "1500", "2000", "3000", "siaair", "lss", "abralon"]):
            if "polish" not in finish_lower and "compound" not in finish_lower:
                return "Heavy" if ("asym" in simplify_core(core_type, int_diff) or int_diff > 0.008) else "Medium-Heavy"
        return "Medium-Heavy"

    if "hybrid" in cover_lower:
        if "polish" in finish_lower or "compound" in finish_lower or "reacta" in finish_lower:
            return "Medium"
        return "Medium-Heavy"

    if "pearl" in cover_lower:
        if any(g in finish_lower for g in ["500", "1000", "2000"]) and "polish" not in finish_lower:
            return "Medium-Heavy"
        return "Medium"

    if "plastic" in cover_lower or "polyester" in cover_lower:
        return "Dry/Light"

    return "Medium"


# ----------------------------------------------------------------------
# Local Ground-Truth Verified Database Cache
# ----------------------------------------------------------------------
BOWWWL_VERIFIED_DB = {
    "bionic": {
        "brand": "Storm",
        "name": "Bionic",
        "rg": 2.47,
        "diff": 0.050,
        "int_diff": 0.000,
        "cover": "hybrid",
        "cover_name": "NRG Hybrid",
        "core": "sym",
        "finish": "4000 Abralon",
    },
    "storm bionic": {
        "brand": "Storm",
        "name": "Bionic",
        "rg": 2.47,
        "diff": 0.050,
        "int_diff": 0.000,
        "cover": "hybrid",
        "cover_name": "NRG Hybrid",
        "core": "sym",
        "finish": "4000 Abralon",
    },
    "phaze ii": {
        "brand": "Storm",
        "name": "Phaze II",
        "rg": 2.48,
        "diff": 0.051,
        "int_diff": 0.000,
        "cover": "solid",
        "cover_name": "TX-16 Solid Reactive",
        "core": "sym",
        "finish": "3000 Abralon",
    },
    "phaze 2": {
        "brand": "Storm",
        "name": "Phaze II",
        "rg": 2.48,
        "diff": 0.051,
        "int_diff": 0.000,
        "cover": "solid",
        "cover_name": "TX-16 Solid Reactive",
        "core": "sym",
        "finish": "3000 Abralon",
    },
    "black widow 3.0": {
        "brand": "Hammer",
        "name": "Black Widow 3.0",
        "rg": 2.50,
        "diff": 0.058,
        "int_diff": 0.016,
        "cover": "solid",
        "cover_name": "HK22 - Cohesion Solid",
        "core": "asym",
        "finish": "2000 Siaair",
    },
    "black widow 2.0": {
        "brand": "Hammer",
        "name": "Black Widow 2.0",
        "rg": 2.50,
        "diff": 0.058,
        "int_diff": 0.016,
        "cover": "solid",
        "cover_name": "Aggression Solid",
        "core": "asym",
        "finish": "2000 Siaair",
    },
    "venom shock": {
        "brand": "Motiv",
        "name": "Venom Shock",
        "rg": 2.48,
        "diff": 0.034,
        "int_diff": 0.000,
        "cover": "solid",
        "cover_name": "Turmoil MFK Solid",
        "core": "sym",
        "finish": "4000 LSS",
    },
    "iq tour": {
        "brand": "Storm",
        "name": "IQ Tour",
        "rg": 2.49,
        "diff": 0.029,
        "int_diff": 0.000,
        "cover": "solid",
        "cover_name": "C3 Centripetal Control",
        "core": "sym",
        "finish": "4000 Abralon",
    },
    "hy-road": {
        "brand": "Storm",
        "name": "Hy-Road",
        "rg": 2.57,
        "diff": 0.046,
        "int_diff": 0.000,
        "cover": "hybrid",
        "cover_name": "R2S Hybrid Reactive",
        "core": "sym",
        "finish": "1500 Polished",
    },
    "pitch black": {
        "brand": "Storm",
        "name": "Pitch Black",
        "rg": 2.57,
        "diff": 0.022,
        "int_diff": 0.000,
        "cover": "urethane",
        "cover_name": "Control Solid Urethane",
        "core": "sym",
        "finish": "1000 Abralon",
    },
    "ion max": {
        "brand": "Storm",
        "name": "Ion Max",
        "rg": 2.47,
        "diff": 0.055,
        "int_diff": 0.014,
        "cover": "solid",
        "cover_name": "Element Max Solid",
        "core": "asym",
        "finish": "2000 Abralon",
    },
    "optimum id": {
        "brand": "Roto Grip",
        "name": "Optimum ID",
        "rg": 2.47,
        "diff": 0.056,
        "int_diff": 0.018,
        "cover": "solid",
        "cover_name": "MicroTrax Solid Reactive",
        "core": "asym",
        "finish": "2000 Abralon",
    },
}


# ----------------------------------------------------------------------
# bowwwl.com Scraper Thread
# ----------------------------------------------------------------------
class BowwwlScraperThread(QThread):
    finished_signal = pyqtSignal(dict, str)

    def __init__(self, query_name, brand_name=""):
        super().__init__()
        self.query_name = query_name.strip()
        self.brand_name = brand_name.strip()

    def run(self):
        query_clean = self.query_name.lower()
        brand_clean = self.brand_name.lower()

        # 1. Fast Cache Lookup
        matches = [
            key for key in BOWWWL_VERIFIED_DB if re.search(r"\b" + re.escape(key) + r"\b", query_clean)
        ]
        if matches:
            best_key = max(matches, key=len)
            spec = BOWWWL_VERIFIED_DB[best_key]
            ball_dict = self.build_ball_dict(
                spec["brand"],
                spec["name"],
                spec["cover"],
                spec["core"],
                spec["rg"],
                spec["diff"],
                spec["int_diff"],
                spec["cover_name"],
                spec["finish"],
            )
            self.finished_signal.emit(ball_dict, "")
            return

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        ball_slug = query_clean.replace(" ", "-")
        brand_slug = brand_clean.replace(" ", "-")

        # 2. Direct Slug Lookup with Input Brand
        if brand_slug:
            try:
                direct_url = f"https://www.bowwwl.com/bowling-ball-database/{brand_slug}/{ball_slug}"
                res = requests.get(direct_url, headers=headers, timeout=6)
                if res.status_code == 200 and "404" not in res.url:
                    ball_data = self.parse_bowwwl_product_page(res.text, self.query_name, self.brand_name)
                    if ball_data:
                        self.finished_signal.emit(ball_data, "")
                        return
            except Exception:
                pass

        # 3. Fallback Brand Slug Search
        brands_to_try = [
            "radical",
            "storm",
            "hammer",
            "motiv",
            "roto-grip",
            "900-global",
            "brunswick",
            "ebonite",
            "track",
        ]
        for b in brands_to_try:
            if b == brand_slug:
                continue
            try:
                direct_url = f"https://www.bowwwl.com/bowling-ball-database/{b}/{ball_slug}"
                res = requests.get(direct_url, headers=headers, timeout=4)
                if res.status_code == 200 and "404" not in res.url:
                    ball_data = self.parse_bowwwl_product_page(res.text, self.query_name, b.title())
                    if ball_data:
                        self.finished_signal.emit(ball_data, "")
                        return
            except Exception:
                continue

        # 4. Search Query Fallback
        try:
            search_url = (
                f"https://www.bowwwl.com/bowling-ball-database?search={requests.utils.quote(self.query_name)}"
            )
            response = requests.get(search_url, headers=headers, timeout=8)
            if response.status_code == 200:
                ball_data = self.parse_bowwwl_table(response.text)
                if ball_data:
                    self.finished_signal.emit(ball_data, "")
                    return
        except Exception:
            pass

        # 5. Playwright Search Fallback
        if PLAYWRIGHT_AVAILABLE:
            try:
                ball_dict = self.scrape_bowwwl_playwright(self.query_name)
                if ball_dict:
                    self.finished_signal.emit(ball_dict, "")
                    return
            except Exception:
                pass

        self.finished_signal.emit(
            {},
            f"Could not find exact ball '{self.query_name}' on bowwwl.com.\nVerify the Brand and Ball Name inputs.",
        )

    def parse_bowwwl_table(self, html_text):
        soup = BeautifulSoup(html_text, "html.parser")
        table = soup.find("table")
        if not table:
            return None

        headers = [th.text.strip().lower() for th in table.find_all("th")]
        idx_name = next((i for i, h in enumerate(headers) if "ball" in h or "name" in h), 0)
        idx_brand = next((i for i, h in enumerate(headers) if "brand" in h), 1)
        idx_cover = next((i for i, h in enumerate(headers) if "cover" in h), 3)
        idx_finish = next((i for i, h in enumerate(headers) if "finish" in h), 4)
        idx_core = next((i for i, h in enumerate(headers) if "core" in h), 5)
        idx_rg = next((i for i, h in enumerate(headers) if "rg" in h), 6)
        idx_diff = next((i for i, h in enumerate(headers) if "diff" in h and "mb" not in h and "int" not in h), 7)
        idx_int = next((i for i, h in enumerate(headers) if "mb" in h or "int" in h or "asym" in h), 8)

        rows = table.find_all("tr")
        for row in rows[1:]:
            cols = [c.text.strip() for c in row.find_all("td")]
            if len(cols) > max(idx_rg, idx_diff):
                name = cols[idx_name]
                if any(word in name.lower() for word in self.query_name.lower().split()):
                    brand = cols[idx_brand] if len(cols) > idx_brand else (self.brand_name or "Unknown")
                    cover_raw = cols[idx_cover] if len(cols) > idx_cover else "Reactive"
                    finish = cols[idx_finish] if len(cols) > idx_finish else "Factory Finish"
                    core_raw = cols[idx_core] if len(cols) > idx_core else "Symmetric"

                    try:
                        rg = float(re.findall(r"2\.\d+", cols[idx_rg])[0])
                        diff = float(re.findall(r"0\.\d+", cols[idx_diff])[0])
                        int_diff = 0.000
                        if len(cols) > idx_int and cols[idx_int] and cols[idx_int] != "-":
                            int_matches = re.findall(r"0\.\d+", cols[idx_int])
                            if int_matches:
                                int_diff = float(int_matches[0])
                    except (ValueError, IndexError):
                        continue

                    core_type = simplify_core(core_raw, int_diff)
                    cover_type = simplify_cover(cover_raw)

                    return self.build_ball_dict(
                        brand, name, cover_type, core_type, rg, diff, int_diff, cover_raw, finish
                    )
        return None

    def parse_bowwwl_product_page(self, html_text, query, brand_hint="", target_weight=15):
        soup = BeautifulSoup(html_text, "html.parser")
        title_el = soup.find("h1")
        title = title_el.text.strip() if title_el else query.title()

        if not title or "page not found" in title.lower() or "not found" in title.lower():
            return None

        strings = [s.strip() for s in soup.stripped_strings if s.strip()]

        def value_after(label, start=0, stop=None):
            end = stop if stop is not None else len(strings)
            label = label.lower()
            for i in range(start, end):
                if strings[i].lower() == label and i + 1 < len(strings):
                    return strings[i + 1]
            return None

        weight_label = f"{target_weight} pound"
        block_start = -1
        cursor = 0
        while cursor < len(strings):
            idx = next(
                (i for i in range(cursor, len(strings)) if strings[i].lower().startswith(weight_label)), -1
            )
            if idx == -1:
                break
            if any(w.lower() == "rg" for w in strings[idx + 1: idx + 6]):
                block_start = idx
                break
            cursor = idx + 1

        if block_start == -1:
            return None

        block_end = len(strings)
        for i in range(block_start + 1, len(strings)):
            if re.match(r"^\d{1,2} pounds?$", strings[i].lower()):
                block_end = i
                break

        rg_str = value_after("RG", block_start, block_end)
        diff_str = value_after("Diff", block_start, block_end)
        int_diff_str = value_after("MB Diff", block_start, block_end) or value_after(
            "Intermediate Diff", block_start, block_end
        )

        rg_num = re.search(r"\d+\.\d+", rg_str) if rg_str else None
        diff_num = re.search(r"\d+\.\d+", diff_str) if diff_str else None
        if not rg_num or not diff_num:
            return None

        rg_val = float(rg_num.group())
        diff_val = float(diff_num.group())
        int_diff_match = re.search(r"\d+\.\d+", int_diff_str) if int_diff_str else None
        int_diff_val = float(int_diff_match.group()) if int_diff_match else 0.000

        brand = brand_hint.title() if brand_hint else None
        if not brand:
            for a in soup.find_all("a", href=True):
                if re.search(r"/bowling-ball-database/[a-z0-9-]+/?$", a["href"]):
                    text = a.get_text(strip=True)
                    if text:
                        brand = text
                        break
        brand = brand or "Unknown"

        core_raw = value_after("Core Type") or ""
        core_type = simplify_core(core_raw, int_diff_val)

        cover_raw = value_after("Type") or ""
        cover_type = simplify_cover(cover_raw)

        finish = value_after("Factory Finish") or "Factory Finish"

        return self.build_ball_dict(
            brand,
            title,
            cover_type,
            core_type,
            rg_val,
            diff_val,
            int_diff_val,
            cover_raw or cover_type,
            finish,
        )

    def scrape_bowwwl_playwright(self, query):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            url = f"https://www.bowwwl.com/bowling-ball-database?search={requests.utils.quote(query)}"
            page.goto(url, timeout=10000, wait_until="domcontentloaded")

            rows = page.query_selector_all("table tr")
            if len(rows) > 1:
                cols = [c.inner_text().strip() for c in rows[1].query_selector_all("td")]
                if len(cols) >= 8:
                    name = cols[0]
                    brand = cols[1]
                    cover_raw = cols[3]
                    finish = cols[4]
                    core_raw = cols[5]
                    rg = float(re.findall(r"2\.\d+", cols[6])[0])
                    diff = float(re.findall(r"0\.\d+", cols[7])[0])
                    int_diff = (
                        float(re.findall(r"0\.\d+", cols[8])[0])
                        if len(cols) > 8 and re.search(r"0\.\d+", cols[8])
                        else 0.000
                    )

                    core_type = simplify_core(core_raw, int_diff)
                    cover_type = simplify_cover(cover_raw)

                    browser.close()
                    return self.build_ball_dict(
                        brand, name, cover_type, core_type, rg, diff, int_diff, cover_raw, finish
                    )
            browser.close()
            return None

    def build_ball_dict(self, brand, name, cover, core, rg, diff, int_diff, cover_name, finish):
        cover_simple = simplify_cover(cover)
        core_simple = simplify_core(core, int_diff)

        hook_est = min(10.0, max(2.0, (diff * 120.0) + (10 - (rg - 2.40) * 30)))
        length_est = min(10.0, max(2.0, (rg - 2.40) * 40.0))

        angularity_base = (
            4.5 if "solid" in cover_simple else (
                7.0 if "pearl" in cover_simple else (5.5 if "hybrid" in cover_simple else 2.5))
        )
        angularity_est = angularity_base + (1.5 if "asym" in core_simple else 0.0) + (diff - 0.045) * 30.0
        angularity_est = min(10.0, max(1.0, angularity_est))

        oil_base = (
            8.0 if "solid" in cover_simple else (
                6.5 if "hybrid" in cover_simple else (5.5 if "pearl" in cover_simple else 3.0))
        )
        rg_bonus = max(0.0, (2.52 - rg) * 20.0)
        diff_bonus = (diff - 0.045) * 30.0
        asym_bonus = 1.0 if ("asym" in core_simple or int_diff > 0.010) else 0.0

        finish_lower = str(finish).lower()
        surface_bonus = 0.0
        if any(grit in finish_lower for grit in ["1000", "2000", "3000", "lss", "abralon", "siaair"]):
            if "polish" not in finish_lower:
                surface_bonus = 1.0

        oil_est = min(10.0, max(1.0, oil_base + rg_bonus + diff_bonus + asym_bonus + surface_bonus))
        pref_oil = simplify_oil(determine_preferred_oil(cover_simple, finish, core_simple, int_diff))

        return {
            "id": str(np.random.randint(1000, 9999)),
            "brand": brand,
            "name": name,
            "cover": cover_simple,
            "cover_name": cover_name,
            "core": core_simple,
            "rg": rg,
            "diff": diff,
            "int_diff": int_diff,
            "finish": finish,
            "hook": round(hook_est, 1),
            "length": round(length_est, 1),
            "angularity": round(angularity_est, 1),
            "oil": round(oil_est, 1),
            "preferred_oil": pref_oil,
            "resin_strength": round(estimate_resin_strength(cover_simple), 1),
            "color": "#" + "".join([np.random.choice(list("0123456789ABCDEF")) for _ in range(6)]),
        }


# ----------------------------------------------------------------------
# Defaults & Inventory Helpers
# ----------------------------------------------------------------------
DEFAULT_BALLS = [
    {
        "id": "1",
        "brand": "Storm",
        "name": "Bionic",
        "cover": "hybrid",
        "cover_name": "NRG Hybrid",
        "core": "sym",
        "rg": 2.47,
        "diff": 0.050,
        "int_diff": 0.000,
        "finish": "4000 Abralon",
        "hook": 8.5,
        "length": 5.5,
        "angularity": 7.0,
        "oil": 7.5,
        "preferred_oil": "Medium-Heavy",
        "resin_strength": 6.5,
        "color": "#00d2ff",
    },
    {
        "id": "2",
        "brand": "Hammer",
        "name": "Black Widow 3.0",
        "cover": "solid",
        "cover_name": "HK22 - Cohesion Solid",
        "core": "asym",
        "rg": 2.50,
        "diff": 0.058,
        "int_diff": 0.016,
        "finish": "2000 Siaair",
        "hook": 9.5,
        "length": 4.5,
        "angularity": 8.0,
        "oil": 9.5,
        "preferred_oil": "Heavy",
        "resin_strength": 9.0,
        "color": "#ff3366",
    },
    {
        "id": "3",
        "brand": "Motiv",
        "name": "Venom Shock",
        "cover": "solid",
        "cover_name": "Turmoil MFK Solid",
        "core": "sym",
        "rg": 2.48,
        "diff": 0.034,
        "int_diff": 0.000,
        "finish": "4000 LSS",
        "hook": 6.5,
        "length": 6.0,
        "angularity": 5.5,
        "oil": 6.0,
        "preferred_oil": "Medium-Heavy",
        "resin_strength": 9.0,
        "color": "#00ff88",
    },
]

KNOWN_BRANDS = [
    "Storm",
    "Hammer",
    "Motiv",
    "Roto Grip",
    "900 Global",
    "Brunswick",
    "Radical",
    "Ebonite",
    "Track",
    "Columbia 300",
]

INVENTORY_FILE = os.path.join(os.path.expanduser("~"), ".bowling_ball_inventory.json")


def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        try:
            with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                for b in data:
                    b["cover"] = simplify_cover(b.get("cover", ""))
                    b["core"] = simplify_core(b.get("core", ""), b.get("int_diff", 0.0))
                    b["preferred_oil"] = simplify_oil(b.get("preferred_oil", ""))
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return list(DEFAULT_BALLS)


def save_inventory(balls):
    try:
        with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(balls, f, indent=2)
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------
# Visualizations
# ----------------------------------------------------------------------
class RadarChartCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 4.5), facecolor="#1e1e24")
        self.ax = self.fig.add_subplot(111, polar=True)
        self.ax.set_facecolor("#1e1e24")
        super().__init__(self.fig)

    def update_chart(self, selected_balls):
        self.ax.clear()

        # Adding title with top padding to prevent text overlap
        self.ax.set_title("Performance Profile Comparison", color="#e0e0e0", fontsize=10, fontweight="bold", pad=20)

        categories = ["Hook\nPotential", "Skid\nLength", "Backend\nAngularity", "Oil\nTraction", "Versatility"]
        N = len(categories)
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        angles += angles[:1]

        self.ax.set_theta_offset(np.pi / 2)
        self.ax.set_theta_direction(-1)
        self.ax.set_xticks(angles[:-1])
        self.ax.set_xticklabels(categories, color="#e0e0e0", fontsize=8, fontweight="bold")

        # Increase padding for radar axis labels to prevent overlap
        self.ax.tick_params(pad=12)

        self.ax.set_rlabel_position(0)
        self.ax.set_yticks([2, 4, 6, 8, 10])
        self.ax.set_yticklabels(["2", "4", "6", "8", "10"], color="#888888", fontsize=7)
        self.ax.set_ylim(0, 10)
        self.ax.grid(True, color="#333340", linestyle="--")

        for ball in selected_balls:
            versatility = 10 - abs(ball["rg"] - 2.50) * 40 - abs(ball["diff"] - 0.045) * 50
            versatility = max(3.0, min(9.5, versatility))

            values = [ball["hook"], ball["length"], ball["angularity"], ball["oil"], versatility]
            values += values[:1]
            color = ball.get("color", "#00d2ff")

            self.ax.plot(
                angles,
                values,
                linewidth=2,
                linestyle="solid",
                label=f"{ball['brand']} {ball['name']}",
                color=color,
            )
            self.ax.fill(angles, values, color=color, alpha=0.15)

        if selected_balls:
            # Legend positioned below radar chart
            self.ax.legend(
                loc="upper center",
                bbox_to_anchor=(0.5, -0.15),
                ncol=2,
                facecolor="#2a2a36",
                edgecolor="none",
                labelcolor="white",
                fontsize=7,
            )

        self.fig.tight_layout()
        self.draw()


class QuadrantPlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 4), facecolor="#1e1e24")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#1e1e24")
        super().__init__(self.fig)

    def update_chart(self, all_balls, selected_ids):
        self.ax.clear()
        self.ax.set_title("RG vs. Differential Dynamics", color="#e0e0e0", fontsize=10, fontweight="bold", pad=12)
        self.ax.set_xlabel("Radius of Gyration (RG) -> Higher Skid", color="#aaaaaa", fontsize=8)
        self.ax.set_ylabel("Differential -> Higher Flare", color="#aaaaaa", fontsize=8)

        self.ax.set_xlim(2.45, 2.60)
        self.ax.set_ylim(0.010, 0.065)
        self.ax.axvline(x=2.51, color="#444455", linestyle="--")
        self.ax.axhline(y=0.040, color="#444455", linestyle="--")

        self.ax.tick_params(colors="#888888", labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color("#333340")

        for ball in all_balls:
            is_selected = ball["id"] in selected_ids
            color = ball.get("color", "#00d2ff") if is_selected else "#444455"
            size = 120 if is_selected else 40
            alpha = 1.0 if is_selected else 0.4

            self.ax.scatter(
                ball["rg"],
                ball["diff"],
                color=color,
                s=size,
                alpha=alpha,
                edgecolors="white" if is_selected else "none",
                zorder=3 if is_selected else 2,
            )
            if is_selected:
                self.ax.annotate(
                    f"{ball['name']}",
                    (ball["rg"], ball["diff"]),
                    xytext=(5, 5),
                    textcoords="offset points",
                    color="white",
                    fontsize=8,
                    fontweight="bold",
                )

        self.fig.tight_layout()
        self.draw()


class CoverstockStrengthCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 4), facecolor="#1e1e24")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#1e1e24")
        super().__init__(self.fig)

    def update_chart(self, selected_balls):
        self.ax.clear()
        self.ax.set_title(
            "Estimated Resin Blend Strength\n(Urethane weakest \u2192 Solid Reactive strongest)",
            color="#e0e0e0",
            fontsize=8,
            fontweight="bold",
            pad=12,
        )
        self.ax.set_ylabel("Resin Strength (est.)", color="#aaaaaa", fontsize=8)
        self.ax.set_ylim(0, 10)
        self.ax.tick_params(colors="#888888", labelsize=7)
        for spine in self.ax.spines.values():
            spine.set_color("#333340")

        if not selected_balls:
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            self.fig.tight_layout()
            self.draw()
            return

        labels = [f"{b['brand']} {b['name']}" for b in selected_balls]
        strengths = [
            b.get("resin_strength", estimate_resin_strength(b.get("cover", ""))) for b in selected_balls
        ]
        colors = [b.get("color", "#00d2ff") for b in selected_balls]

        self.ax.bar(range(len(labels)), strengths, color=colors)
        self.ax.set_xticks(range(len(labels)))

        # Vertical labels for high clarity
        self.ax.set_xticklabels(labels, color="#e0e0e0", fontsize=7, rotation=90, ha="center")

        self.fig.tight_layout()
        self.draw()


class MotionOilMapCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 4.5), facecolor="#1e1e24")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#1e1e24")
        super().__init__(self.fig)

    def update_chart(self, selected_balls):
        self.ax.clear()
        self.ax.set_title("Estimated Motion & Preferred Condition Map", color="#e0e0e0", fontsize=10, fontweight="bold",
                          pad=12)
        self.ax.set_xlabel(
            "Motion Shape: Smooth / Arcing \u2190\u2192 Angular / Sharp", color="#aaaaaa", fontsize=8
        )
        self.ax.set_ylabel("Best-Fit Volume: Light/Dry \u2192 Heavy", color="#aaaaaa", fontsize=8)

        self.ax.set_xlim(0, 10)
        self.ax.set_ylim(0, 10)
        self.ax.axvline(x=5, color="#444455", linestyle="--")
        self.ax.axhline(y=5, color="#444455", linestyle="--")

        self.ax.tick_params(colors="#888888", labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color("#333340")

        for ball in selected_balls:
            color = ball.get("color", "#00d2ff")
            x = ball.get("angularity", 5.0)
            y = ball.get("oil", 5.0)
            self.ax.scatter(x, y, color=color, s=140, edgecolors="white", zorder=3)
            self.ax.annotate(
                f"{ball['name']}",
                (x, y),
                xytext=(6, 6),
                textcoords="offset points",
                color="white",
                fontsize=8,
                fontweight="bold",
            )

        self.fig.tight_layout()
        self.draw()


# ----------------------------------------------------------------------
# Application Window
# ----------------------------------------------------------------------
class BowlingBallApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro-Track Bowling Ball Comparison Engine (bowwwl.com Database)")
        self.resize(1320, 850)

        self.balls = load_inventory()
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
            QTableWidget { background-color: #181820; gridline-color: #2a2a36; border: 1px solid #2a2a36; border-radius: 4px; selection-background-color: #333345; }
            QHeaderView::section { background-color: #252530; color: #00d2ff; font-weight: bold; border: none; padding: 4px; }
            QLineEdit, QComboBox { background-color: #252530; color: white; border: 1px solid #3a3a4c; padding: 6px; border-radius: 4px; }
            QPushButton { background-color: #252530; color: #00d2ff; border: 1px solid #00d2ff; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #00d2ff; color: #101014; }
            QPushButton#btnDelete { background-color: #2a1a1a; color: #ff5555; border: 1px solid #ff5555; }
            QPushButton#btnDelete:hover { background-color: #ff5555; color: #ffffff; }
            QTabWidget::pane { border: 1px solid #2a2a36; background: #1e1e24; }
            QTabBar::tab { background: #181820; color: #aaa; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #252530; color: #00d2ff; font-weight: bold; border-bottom: 2px solid #00d2ff; }
        """)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Left Panel
        left_panel = QGroupBox("Ball Database Catalog (bowwwl.com)")
        left_layout = QVBoxLayout(left_panel)

        # Lookup Box
        lookup_box = QGroupBox("Fetch Specs from bowwwl.com")
        lookup_layout = QVBoxLayout(lookup_box)

        input_fields_layout = QHBoxLayout()

        self.brand_search_in = QComboBox()
        self.brand_search_in.setEditable(True)
        self.brand_search_in.addItems(KNOWN_BRANDS)
        self.brand_search_in.setCurrentIndex(-1)
        self.brand_search_in.lineEdit().setPlaceholderText("Brand")
        self.brand_search_in.lineEdit().returnPressed.connect(self.scrape_ball_online)

        self.web_search_in = QLineEdit()
        self.web_search_in.setPlaceholderText("Ball Name (e.g. Evil Eye Pearl)")
        self.web_search_in.returnPressed.connect(self.scrape_ball_online)

        input_fields_layout.addWidget(self.brand_search_in, 1)
        input_fields_layout.addWidget(self.web_search_in, 2)
        lookup_layout.addLayout(input_fields_layout)

        btn_scrape = QPushButton("🔍 Fetch Specs from bowwwl.com")
        btn_scrape.clicked.connect(self.scrape_ball_online)
        lookup_layout.addWidget(btn_scrape)

        left_layout.addWidget(lookup_box)

        # Search Filters
        filter_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter local catalog...")
        self.search_box.textChanged.connect(self.filter_database)
        filter_layout.addWidget(self.search_box)

        self.brand_filter = QComboBox()
        self.brand_filter.addItems(["All Brands"] + KNOWN_BRANDS)
        self.brand_filter.currentTextChanged.connect(self.filter_database)
        filter_layout.addWidget(self.brand_filter)

        left_layout.addLayout(filter_layout)

        # Main Table
        self.db_table = QTableWidget()
        self.db_table.setColumnCount(6)
        self.db_table.setHorizontalHeaderLabels(["", "Brand", "Model", "Core", "Cover", "Preferred Oil"])
        self.db_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.db_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.db_table.setColumnWidth(0, 30)

        self.db_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.db_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.db_table.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.db_table)

        # Catalog Action Buttons
        catalog_btn_layout = QHBoxLayout()
        self.btn_delete_selected = QPushButton("🗑 Delete Selected Ball(s)")
        self.btn_delete_selected.setObjectName("btnDelete")
        self.btn_delete_selected.clicked.connect(self.delete_selected_balls)
        catalog_btn_layout.addWidget(self.btn_delete_selected)

        self.btn_save_inventory = QPushButton("💾 Save Inventory")
        self.btn_save_inventory.clicked.connect(self.save_inventory_now)
        catalog_btn_layout.addWidget(self.btn_save_inventory)

        self.btn_reset_inventory = QPushButton("↺ Reset")
        self.btn_reset_inventory.clicked.connect(self.reset_inventory)
        catalog_btn_layout.addWidget(self.btn_reset_inventory)

        left_layout.addLayout(catalog_btn_layout)

        # Right Panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.tabs = QTabWidget()

        # Tab 1: Spec Matrix & Gaps
        self.tab_matrix = QWidget()
        matrix_layout = QVBoxLayout(self.tab_matrix)
        self.matrix_table = QTableWidget()
        matrix_layout.addWidget(self.matrix_table)

        self.gap_box = QGroupBox("Arsenal Structure & Gap Analysis (6-Ball Slot Grid)")
        gap_layout = QVBoxLayout(self.gap_box)
        self.gap_label = QLabel("Select balls to evaluate coverage...")
        self.gap_label.setWordWrap(True)
        gap_layout.addWidget(self.gap_label)
        matrix_layout.addWidget(self.gap_box)
        self.tabs.addTab(self.tab_matrix, "Spec Matrix & Gaps")

        # Tab 2: Radar & Core Dynamics
        self.tab_charts = QWidget()
        charts_layout = QHBoxLayout(self.tab_charts)
        self.radar_canvas = RadarChartCanvas(self)
        self.quadrant_canvas = QuadrantPlotCanvas(self)
        charts_layout.addWidget(self.radar_canvas)
        charts_layout.addWidget(self.quadrant_canvas)
        self.tabs.addTab(self.tab_charts, "Radar & Core Dynamics")

        # Tab 3: Coverstock Comparison
        self.tab_cover = QWidget()
        cover_layout = QVBoxLayout(self.tab_cover)

        cover_note = QLabel("Coverstock families determine base strength and oil traction behavior.")
        cover_note.setWordWrap(True)
        cover_note.setStyleSheet("color: #999999; font-size: 11px; padding: 2px 4px 8px 4px;")
        cover_layout.addWidget(cover_note)

        cover_split = QHBoxLayout()
        self.cover_table = QTableWidget()
        self.cover_table.setColumnCount(4)
        self.cover_table.setHorizontalHeaderLabels(
            ["Ball", "Cover Category", "Cover Material", "Resin Strength (est.)"]
        )
        self.cover_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        cover_split.addWidget(self.cover_table, 3)

        self.cover_canvas = CoverstockStrengthCanvas(self)
        cover_split.addWidget(self.cover_canvas, 2)

        cover_layout.addLayout(cover_split)
        self.tabs.addTab(self.tab_cover, "Coverstock Comparison")

        # Tab 4: Oil Volume vs Motion Map
        self.tab_motion = QWidget()
        motion_layout = QVBoxLayout(self.tab_motion)

        self.motion_canvas = MotionOilMapCanvas(self)
        motion_layout.addWidget(self.motion_canvas)
        self.tabs.addTab(self.tab_motion, "Oil Volume vs Motion")

        right_layout.addWidget(self.tabs)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([480, 840])

        main_layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # bowwwl.com Scraper Slot
    # ------------------------------------------------------------------
    def scrape_ball_online(self):
        query = self.web_search_in.text().strip()
        brand = self.brand_search_in.currentText().strip()

        if not query:
            QMessageBox.information(self, "Input Required", "Please enter a bowling ball name to search.")
            return

        display_name = f"{brand} {query}".strip()
        self.progress = QProgressDialog(
            f"Fetching verified 15lb specs from bowwwl.com for '{display_name}'...", None, 0, 0, self
        )
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.show()

        self.thread = BowwwlScraperThread(query, brand)
        self.thread.finished_signal.connect(self.handle_scrape_results)
        self.thread.start()

    def handle_scrape_results(self, ball_data, error_msg):
        self.progress.close()
        if error_msg:
            QMessageBox.warning(self, "Lookup Error", error_msg)
            return

        self.balls.append(ball_data)
        self.selected_ids.append(ball_data["id"])
        save_inventory(self.balls)

        self.web_search_in.clear()
        self.brand_search_in.setCurrentIndex(-1)
        self.brand_search_in.clearEditText()
        QMessageBox.information(
            self,
            "Data Fetched Successfully (bowwwl.com)",
            f"Verified Specifications Added:\n\n"
            f"• Brand: {ball_data['brand']}\n"
            f"• Model: {ball_data['name']}\n"
            f"• RG (15lb): {ball_data['rg']:.2f}\n"
            f"• Differential (15lb): {ball_data['diff']:.3f}\n"
            f"• Intermediate Diff: {ball_data['int_diff']:.3f}\n"
            f"• Core Architecture: {ball_data['core']}\n"
            f"• Preferred Oil Condition: {ball_data.get('preferred_oil', 'Medium')}\n"
            f"• Factory Finish: {ball_data['finish']}",
        )
        self.update_all_views()

    # ------------------------------------------------------------------
    # Catalog Management
    # ------------------------------------------------------------------
    def save_inventory_now(self):
        if save_inventory(self.balls):
            QMessageBox.information(
                self, "Inventory Saved", f"Your {len(self.balls)}-ball inventory was saved to:\n{INVENTORY_FILE}"
            )
        else:
            QMessageBox.warning(self, "Save Failed", f"Could not write inventory to:\n{INVENTORY_FILE}")

    def reset_inventory(self):
        reply = QMessageBox.question(
            self,
            "Reset Inventory",
            "This replaces your saved inventory with the original default catalog. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.balls = list(DEFAULT_BALLS)
            self.selected_ids = ["1", "2"]
            save_inventory(self.balls)
            self.update_all_views()

    def closeEvent(self, event):
        save_inventory(self.balls)
        event.accept()

    def delete_selected_balls(self):
        selected_rows = list(set([item.row() for item in self.db_table.selectedItems()]))

        if not selected_rows:
            QMessageBox.information(
                self,
                "Selection Required",
                "Please click on a row in the catalog table to select a ball to delete.",
            )
            return

        balls_to_delete = []
        for row in selected_rows:
            ball_id = self.db_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            for b in self.balls:
                if b["id"] == ball_id:
                    balls_to_delete.append(b)

        names = ", ".join([f"{b['brand']} {b['name']}" for b in balls_to_delete])
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete the following ball(s) from your catalog?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            for b in balls_to_delete:
                if b in self.balls:
                    self.balls.remove(b)
                if b["id"] in self.selected_ids:
                    self.selected_ids.remove(b["id"])

            save_inventory(self.balls)
            self.update_all_views()

    def show_context_menu(self, position):
        row = self.db_table.rowAt(position.y())
        if row >= 0:
            menu = QMenu(self)
            delete_action = QAction("🗑 Delete Ball from Catalog", self)
            delete_action.triggered.connect(self.delete_selected_balls)
            menu.addAction(delete_action)
            menu.exec(self.db_table.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Data Updates & UI Sync
    # ------------------------------------------------------------------
    def filter_database(self):
        query = self.search_box.text().lower()
        brand = self.brand_filter.currentText()

        self.db_table.setRowCount(0)
        filtered = [
            b
            for b in self.balls
            if (query in b["name"].lower() or query in b["brand"].lower())
               and (brand == "All Brands" or b["brand"] == brand)
        ]

        self.db_table.setRowCount(len(filtered))
        for row, ball in enumerate(filtered):
            chk = QCheckBox()
            chk.setChecked(ball["id"] in self.selected_ids)
            chk.stateChanged.connect(lambda state, b_id=ball["id"]: self.toggle_selection(b_id, state))

            self.db_table.setCellWidget(row, 0, chk)

            brand_item = QTableWidgetItem(ball["brand"])
            brand_item.setData(Qt.ItemDataRole.UserRole, ball["id"])

            self.db_table.setItem(row, 1, brand_item)
            self.db_table.setItem(row, 2, QTableWidgetItem(ball["name"]))
            self.db_table.setItem(row, 3, QTableWidgetItem(simplify_core(ball["core"], ball.get("int_diff", 0.0))))
            self.db_table.setItem(row, 4, QTableWidgetItem(simplify_cover(ball["cover"])))
            pref_oil = ball.get(
                "preferred_oil",
                determine_preferred_oil(ball["cover"], ball["finish"], ball["core"], ball["int_diff"]),
            )
            self.db_table.setItem(row, 5, QTableWidgetItem(simplify_oil(pref_oil)))

    def toggle_selection(self, ball_id, state):
        if state == 2:
            if ball_id not in self.selected_ids:
                self.selected_ids.append(ball_id)
        else:
            if ball_id in self.selected_ids:
                self.selected_ids.remove(ball_id)
        self.update_all_views()

    def update_all_views(self):
        selected_balls = [b for b in self.balls if b["id"] in self.selected_ids]
        self.filter_database()
        self.update_matrix_table(selected_balls)
        self.update_gap_analysis(selected_balls)
        self.radar_canvas.update_chart(selected_balls)
        self.quadrant_canvas.update_chart(self.balls, self.selected_ids)
        self.update_coverstock_comparison(selected_balls)
        self.motion_canvas.update_chart(selected_balls)

    def update_matrix_table(self, selected_balls):
        self.matrix_table.clear()
        if not selected_balls:
            self.matrix_table.setRowCount(0)
            self.matrix_table.setColumnCount(0)
            return

        specs = [
            ("Brand", "brand"),
            ("Coverstock Type", "cover"),
            ("Cover Material", "cover_name"),
            ("Core Architecture", "core"),
            ("Radius of Gyration (RG)", "rg"),
            ("Differential", "diff"),
            ("Intermediate Diff", "int_diff"),
            ("Factory Finish", "finish"),
            ("Preferred Oil Condition", "preferred_oil"),
            ("Hook Potential", "hook"),
            ("Length/Skid", "length"),
            ("Angularity", "angularity"),
            ("Oil Traction Rating", "oil"),
        ]

        self.matrix_table.setRowCount(len(specs))
        self.matrix_table.setColumnCount(len(selected_balls))

        headers = [f"{b['brand']}\n{b['name']}" for b in selected_balls]
        self.matrix_table.setHorizontalHeaderLabels(headers)
        self.matrix_table.setVerticalHeaderLabels([s[0] for s in specs])
        self.matrix_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for col, ball in enumerate(selected_balls):
            for row, (_, key) in enumerate(specs):
                val = ball.get(
                    key,
                    determine_preferred_oil(
                        ball["cover"], ball["finish"], ball["core"], ball["int_diff"]
                    )
                    if key == "preferred_oil"
                    else "N/A",
                )
                if key == "cover":
                    val = simplify_cover(val)
                elif key == "core":
                    val = simplify_core(val, ball.get("int_diff", 0.0))
                elif key == "preferred_oil":
                    val = simplify_oil(val)

                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.matrix_table.setItem(row, col, item)

    def update_gap_analysis(self, selected_balls):
        if not selected_balls:
            self.gap_label.setText("Select balls to evaluate 6-slot coverage.")
            return

        slots = {
            "big asym": None,
            "big sym": None,
            "control": None,
            "clean asym": None,
            "clean sym": None,
            "specialty": None,
        }

        for b in selected_balls:
            cover = simplify_cover(b["cover"])
            core = simplify_core(b["core"], b.get("int_diff", 0.0))
            oil = b.get("oil", 5.0)
            ang = b.get("angularity", 5.0)

            # 1. Big Asym
            if core == "asym" and cover in ["solid", "hybrid"] and oil >= 7.5 and not slots["big asym"]:
                slots["big asym"] = b["name"]
            # 2. Big Sym
            elif core == "sym" and cover == "solid" and oil >= 6.5 and not slots["big sym"]:
                slots["big sym"] = b["name"]
            # 3. Control
            elif (cover == "urethane" or (b.get("diff", 0.0) <= 0.038 and oil <= 6.5)) and not slots["control"]:
                slots["control"] = b["name"]
            # 4. Clean Asym
            elif core == "asym" and cover in ["pearl", "hybrid"] and ang >= 6.5 and not slots["clean asym"]:
                slots["clean asym"] = b["name"]
            # 5. Clean Sym
            elif core == "sym" and cover in ["pearl", "hybrid"] and not slots["clean sym"]:
                slots["clean sym"] = b["name"]
            # 6. Specialty
            elif (cover in ["urethane", "plastic"] or b.get("diff", 0.0) < 0.025) and not slots["specialty"]:
                slots["specialty"] = b["name"]

        display_texts = []
        for slot_name, filled_ball in slots.items():
            slot_title = slot_name.upper()
            if filled_ball:
                display_texts.append(f"<b style='color:#00ff88;'>✔ {slot_title}:</b> {filled_ball}")
            else:
                display_texts.append(f"<b style='color:#ffaa00;'>⚠ {slot_title}:</b> [Empty Slot]")

        self.gap_label.setText("<br>".join(display_texts))

    def update_coverstock_comparison(self, selected_balls):
        self.cover_table.setRowCount(len(selected_balls))
        for row, ball in enumerate(selected_balls):
            self.cover_table.setItem(row, 0, QTableWidgetItem(f"{ball['brand']} {ball['name']}"))
            self.cover_table.setItem(row, 1, QTableWidgetItem(simplify_cover(ball.get("cover", ""))))
            self.cover_table.setItem(row, 2, QTableWidgetItem(ball.get("cover_name", "")))
            strength = ball.get("resin_strength", estimate_resin_strength(ball.get("cover", "")))
            self.cover_table.setItem(row, 3, QTableWidgetItem(f"{strength:.1f} / 10"))
        self.cover_canvas.update_chart(selected_balls)


# ----------------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BowlingBallApp()
    window.show()
    sys.exit(app.exec())