"""Architecture and workflow diagrams (PNG) for the report."""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUT, exist_ok=True)
G1, G2, G3, OR, BL, GR = "#145a32", "#e3f2e8", "#7cb342", "#fff3e0", "#e3f2fd", "#eceff1"


def box(ax, x, y, w, h, text, fc=G2, ec=G1, fs=9, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc=fc, ec=ec, lw=1.3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, wrap=True,
            fontweight="bold" if bold else "normal", color="#1d2721")


def arrow(ax, x1, y1, x2, y2, text=None, color="#37474f"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, lw=1.2, color=color))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, ha="center", fontsize=7, color="#455a64")


def architecture():
    fig, ax = plt.subplots(figsize=(12, 7.2))
    ax.set_xlim(0, 12); ax.set_ylim(0, 7.2); ax.axis("off")
    # users
    ax.text(0.2, 6.85, "USERS (Chrome browser – desktop & mobile)", fontsize=10, fontweight="bold", color=G1)
    box(ax, 0.2, 5.7, 3.4, 0.95, "Farmer\nphoto scan · farms · traps\nalerts · follow-up", fc="#ffffff")
    box(ax, 4.3, 5.7, 3.4, 0.95, "Extension officer\nvalidation queue · referrals\nhotspot map", fc="#ffffff")
    box(ax, 8.4, 5.7, 3.4, 0.95, "Agriculture official\ndashboard · KPIs\nmodel management", fc="#ffffff")
    box(ax, 0.2, 4.7, 11.6, 0.6, "Presentation layer: HTML5 + CSS3 + JavaScript · Jinja2 templates · Leaflet.js maps · Chart.js · Web Speech (read-aloud) · 6 languages",
        fc=BL, ec="#1565c0", fs=9)
    # backend
    ax.text(0.2, 4.3, "FLASK APPLICATION SERVER (Python)", fontsize=10, fontweight="bold", color=G1)
    mods = [("AI diagnosis\nMobileNetV2 +\ndense head", 0.2), ("Risk forecasting\nweather × stage ×\nvariety × soil", 2.2),
            ("Pest-trap / IoT\nETL threshold\nengine", 4.2), ("Hotspot detection\nDBSCAN\n(haversine)", 6.2),
            ("IPM advisory\nmultilingual\ncomposer", 8.2), ("Validation &\ncontinual\nlearning", 10.2)]
    for t, x in mods:
        box(ax, x, 2.75, 1.65, 1.3, t, fc=G2, fs=8.5)
    box(ax, 0.2, 2.1, 11.6, 0.45, "Auth & roles · alerts engine · referral & follow-up scheduler · REST/JSON APIs (/api/sensor, /api/stats, /api/hotspots)",
        fc=GR, ec="#78909c", fs=8.5)
    # data
    ax.text(1.7, 1.7, "DATA & SERVICES", fontsize=10, fontweight="bold", color=G1)
    box(ax, 0.2, 0.3, 2.6, 1.2, "SQLite DB\nusers · farms · reports\ntraps · alerts · follow-ups", fc=OR, ec="#e65100", fs=8.5)
    box(ax, 3.1, 0.3, 2.6, 1.2, "Model store\nKeras model · heads v1..vN\nfeatures · feedback", fc=OR, ec="#e65100", fs=8.5)
    box(ax, 6.0, 0.3, 2.6, 1.2, "Knowledge base (JSON)\n39 diseases · 7 pests\nIPM actions × 6 languages", fc=OR, ec="#e65100", fs=8.5)
    box(ax, 8.9, 0.3, 2.9, 1.2, "Open-Meteo weather API\nOpenStreetMap tiles\nIoT stations / smart traps", fc=OR, ec="#e65100", fs=8.5)
    for x in (1.9, 6.0, 10.1):
        arrow(ax, x, 5.7, x, 5.3)
    arrow(ax, 6, 4.7, 6, 4.4)
    for x in (1.5, 4.4, 7.3, 10.35):
        arrow(ax, x, 2.1, x, 1.5)
    fig.savefig(os.path.join(OUT, "architecture.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def workflow():
    fig, ax = plt.subplots(figsize=(12, 4.6))
    ax.set_xlim(0, 12); ax.set_ylim(0, 4.6); ax.axis("off")
    steps = [("1. Capture", "Farmer photographs\nleaf in Chrome"), ("2. Quality check", "blur / exposure\ngate"),
             ("3. AI diagnosis", "MobileNetV2 →\ntop-3 + confidence"), ("4. Context", "weather risk, crop\nstage, nearby cases"),
             ("5. Advisory", "IPM steps in farmer's\nlanguage + audio"), ("6. Expert review", "officer confirms /\ncorrects / refers")]
    for i, (h, t) in enumerate(steps):
        x = 0.15 + i * 1.97
        box(ax, x, 2.75, 1.75, 1.5, f"{h}\n\n{t}", fc=G2 if i % 2 == 0 else "#f1f8e9", fs=8.5)
        if i < len(steps) - 1:
            arrow(ax, x + 1.75, 3.5, x + 1.97, 3.5)
    loops = [("7. Hotspot map", "DBSCAN clusters →\nalerts to nearby farms", 7.9), ("8. Follow-up", "3/7-day check:\nbetter / same / worse", 5.93),
             ("9. Continual learning", "confirmed images\nretrain classifier", 3.96), ("10. Dashboard", "KPIs for agriculture\nofficials", 1.99)]
    for h, t, x in loops:
        box(ax, x, 0.3, 1.75, 1.5, f"{h}\n\n{t}", fc=OR, ec="#e65100", fs=8.5)
    arrow(ax, 10.8, 2.75, 9.4, 1.8)
    for (_, _, x1), (_, _, x2) in zip(loops, loops[1:]):
        arrow(ax, x1, 1.05, x2 + 1.75, 1.05)
    arrow(ax, 4.8, 1.8, 4.9, 2.75, color="#e65100")
    ax.text(5.05, 2.2, "improved model", fontsize=7, color="#e65100")
    fig.savefig(os.path.join(OUT, "workflow.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    architecture()
    workflow()
    print("figures written to", OUT)
