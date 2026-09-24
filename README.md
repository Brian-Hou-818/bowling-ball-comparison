# Pro-Track Bowling Ball Comparison Engine

A PyQt6 desktop application designed to catalog, analyze, and compare bowling ball specifications using online data integration (via `bowwwl.com`), interactive visualizations, and a drag-and-drop arsenal manager.

---

## Features

- **Automated Web Scraping**: Search and import verified 15lb bowling ball specifications directly from `bowwwl.com` using `requests`, `BeautifulSoup4`, and `Playwright` fallbacks.
- **Local Database Management**: Store and filter your custom inventory locally (`~/.bowling_ball_inventory.json`).
- **Interactive Visualizations (Matplotlib)**:
  - **Spec Matrix**: Side-by-side technical specification breakdown.
  - **Core Dynamics Plot**: RG (Radius of Gyration) vs. Differential scatter quadrant map.
  - **Radar Performance Profiles**: Hook potential, length, angularity, oil traction, and versatility metrics.
  - **Coverstock Strength Ratings**: Bar charts estimating relative resin blend aggression.
  - **Oil Volume vs. Motion Map**: Motion shape mapped against oil capacity.
- **Drag-and-Drop Arsenal Manager**: Drag balls directly from your catalog into customizable arsenal slots (*Big Asym, Control, Clean Sym, etc.*).

---

## Installation & Requirements

### Prerequisites

Ensure you have Python **3.9+** installed. Install the required Python packages using `pip`:

```bash
pip install PyQt6 requests matplotlib numpy beautifulsoup4 playwright