#!/usr/bin/env python3
"""Generate ultra-high-resolution PNG infographics from powerlifting app data."""

import sys
sys.path.insert(0, "/opt/home/buckcenter.org/hcheng/powerlifting_app")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import numpy as np

from data import PROGRAMS, NUTRITION_PHASES, SUPPLEMENTS, ACTIVITY_MULTIPLIERS, FOOD_SOURCES

OUT = "/opt/home/buckcenter.org/hcheng/powerlifting_app"
DPI = 600  # Ultra-high resolution

# Consistent styling
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.titlesize": 16,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
    "figure.facecolor": "#FAFAFA",
    "axes.facecolor": "#FAFAFA",
    "savefig.facecolor": "#FAFAFA",
    "savefig.bbox": "tight",
    "savefig.dpi": DPI,
    "savefig.pad_inches": 0.3,
})

# Color palettes
BLUE = "#1565C0"
GREEN = "#2E7D32"
RED = "#C62828"
ORANGE = "#E65100"
TEAL = "#00796B"
PURPLE = "#6A1B9A"
GOLD = "#F9A825"
GRAY = "#616161"

LEVEL_COLORS = {"beginner": "#4CAF50", "intermediate": "#FF9800", "advanced": "#F44336", "all": "#2196F3"}
EVIDENCE_COLORS = {"strong": "#2E7D32", "moderate": "#F57F17"}


# ═══════════════════════════════════════════════════════════════════════
# 1. PROGRAMS COMPARISON CHART
# ═══════════════════════════════════════════════════════════════════════
def fig_programs():
    fig, ax = plt.subplots(figsize=(18, 10))

    programs = sorted(PROGRAMS, key=lambda p: (
        {"beginner": 0, "intermediate": 1, "all": 1.5, "advanced": 2}[p["level"]],
        p["frequency_days_per_week"]
    ))

    names = [p["name"] for p in programs]
    freq = [p["frequency_days_per_week"] for p in programs]
    levels = [p["level"] for p in programs]
    colors = [LEVEL_COLORS[l] for l in levels]

    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, freq, color=colors, edgecolor="white", linewidth=1.5, height=0.65)

    for i, (bar, prog) in enumerate(zip(bars, programs)):
        ax.text(bar.get_width() + 0.08, bar.get_y() + bar.get_height()/2,
                f'{prog["frequency_days_per_week"]}d/wk  |  {prog["sets_reps_scheme"][:50]}',
                va="center", ha="left", fontsize=8.5, color="#333")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=11, fontweight="bold")
    ax.set_xlabel("Training Days per Week", fontsize=13)
    ax.set_title("Powerlifting Programs — Frequency & Structure\n", fontsize=18, fontweight="bold", color="#1A237E")
    ax.set_xlim(0, 8.5)
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    legend_patches = [mpatches.Patch(color=c, label=l.title()) for l, c in LEVEL_COLORS.items()]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=10, framealpha=0.9, title="Experience Level")

    # Author annotations
    for i, prog in enumerate(programs):
        ax.text(-0.02, i, f'  by {prog["author"]}', transform=ax.get_yaxis_transform(),
                va="center", ha="right", fontsize=7, color="#888", style="italic")

    fig.savefig(f"{OUT}/png_programs_comparison.png", dpi=DPI)
    plt.close(fig)
    print("  [1/6] Programs comparison")


# ═══════════════════════════════════════════════════════════════════════
# 2. SUPPLEMENT EVIDENCE PYRAMID
# ═══════════════════════════════════════════════════════════════════════
def fig_supplements():
    fig, ax = plt.subplots(figsize=(16, 10))

    supps = sorted(SUPPLEMENTS, key=lambda s: s["priority_rank"])

    names = [s["name"] for s in supps]
    ranks = [s["priority_rank"] for s in supps]
    evidence = [s["evidence_level"] for s in supps]
    colors = [EVIDENCE_COLORS[e] for e in evidence]
    benefits = [s["primary_benefit"] for s in supps]

    y_pos = np.arange(len(names))
    bar_widths = [10 - r for r in ranks]  # Higher priority = wider bar (pyramid effect)

    bars = ax.barh(y_pos, bar_widths, color=colors, edgecolor="white", linewidth=1.5, height=0.65, alpha=0.85)

    for i, (bar, supp) in enumerate(zip(bars, supps)):
        # Name and rank inside bar
        ax.text(0.15, bar.get_y() + bar.get_height()/2,
                f'#{supp["priority_rank"]}  {supp["name"]}',
                va="center", ha="left", fontsize=10, fontweight="bold", color="white")
        # Benefit text outside bar
        ax.text(bar.get_width() + 0.15, bar.get_y() + bar.get_height()/2,
                f'{supp["primary_benefit"]}  [{supp["evidence_level"].upper()}]',
                va="center", ha="left", fontsize=8.5, color="#444")

    ax.set_yticks([])
    ax.set_xlabel("Priority Score (higher = more essential)", fontsize=12)
    ax.set_title("Supplement Priority Pyramid — Evidence-Based Rankings\n", fontsize=18, fontweight="bold", color="#1A237E")
    ax.set_xlim(0, 13)
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    legend_patches = [
        mpatches.Patch(color=EVIDENCE_COLORS["strong"], label="Strong Evidence"),
        mpatches.Patch(color=EVIDENCE_COLORS["moderate"], label="Moderate Evidence"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=11, framealpha=0.9)

    fig.savefig(f"{OUT}/png_supplement_pyramid.png", dpi=DPI)
    plt.close(fig)
    print("  [2/6] Supplement pyramid")


# ═══════════════════════════════════════════════════════════════════════
# 3. NUTRITION PHASES — MACRO COMPARISON
# ═══════════════════════════════════════════════════════════════════════
def fig_nutrition_phases():
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))

    phases = NUTRITION_PHASES
    labels = [p["label"] for p in phases]
    protein = [p["protein_g_per_kg"] for p in phases]
    carbs = [p["carbs_g_per_kg"] for p in phases]
    surplus = [p["calorie_surplus_deficit"] for p in phases]

    x = np.arange(len(labels))
    width = 0.32

    # Left panel: Macros g/kg
    ax1 = axes[0]
    b1 = ax1.bar(x - width/2, protein, width, label="Protein (g/kg)", color=RED, alpha=0.85, edgecolor="white")
    b2 = ax1.bar(x + width/2, carbs, width, label="Carbs (g/kg)", color=GOLD, alpha=0.85, edgecolor="white")

    for bar in b1:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f'{bar.get_height():.1f}', ha="center", va="bottom", fontsize=9, fontweight="bold")
    for bar in b2:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f'{bar.get_height():.1f}', ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=10, rotation=15, ha="right")
    ax1.set_ylabel("Grams per kg Body Weight", fontsize=12)
    ax1.set_title("Macronutrient Targets by Phase", fontsize=15, fontweight="bold", color="#1A237E")
    ax1.legend(fontsize=10)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.set_ylim(0, 8.5)

    # Right panel: Caloric surplus/deficit
    ax2 = axes[1]
    colors_cal = [GREEN if s > 0 else (RED if s < 0 else GRAY) for s in surplus]
    bars_cal = ax2.bar(x, surplus, width=0.55, color=colors_cal, edgecolor="white", linewidth=1.5, alpha=0.85)
    ax2.axhline(y=0, color="#333", linewidth=0.8, linestyle="-")

    for bar, val in zip(bars_cal, surplus):
        offset = 15 if val >= 0 else -20
        ax2.text(bar.get_x() + bar.get_width()/2, val + offset,
                f'{val:+d} kcal', ha="center", va="bottom" if val >= 0 else "top",
                fontsize=10, fontweight="bold")

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=10, rotation=15, ha="right")
    ax2.set_ylabel("kcal/day vs. TDEE", fontsize=12)
    ax2.set_title("Caloric Surplus / Deficit by Phase", fontsize=15, fontweight="bold", color="#1A237E")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    fig.suptitle("Nutrition Strategy for Powerlifters\n", fontsize=20, fontweight="bold", color="#0D47A1", y=1.02)
    fig.tight_layout()
    fig.savefig(f"{OUT}/png_nutrition_phases.png", dpi=DPI)
    plt.close(fig)
    print("  [3/6] Nutrition phases")


# ═══════════════════════════════════════════════════════════════════════
# 4. 5/3/1 WAVE STRUCTURE VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════
def fig_531():
    prog = next(p for p in PROGRAMS if p["id"] == "531")
    waves = prog["wave_structure"]

    fig, axes = plt.subplots(1, 4, figsize=(20, 6), sharey=True)
    week_colors = [BLUE, TEAL, RED, GRAY]

    for idx, (wave, ax) in enumerate(zip(waves, axes)):
        sets = np.arange(1, len(wave["percentages"]) + 1)
        pcts = wave["percentages"]
        reps = wave["reps"]

        bars = ax.bar(sets, pcts, color=week_colors[idx], edgecolor="white", linewidth=2, width=0.6, alpha=0.9)

        for bar, pct, rep in zip(bars, pcts, reps):
            # Percentage on bar
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() - 3,
                    f'{pct}%', ha="center", va="top", fontsize=13, fontweight="bold", color="white")
            # Reps below bar
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                    f'{rep} rep{"s" if rep > 1 else ""}', ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color="#333")

        # AMRAP marker
        if wave["week"] != 4:
            ax.text(3, pcts[2] + 6, "AMRAP", ha="center", fontsize=9, color=RED,
                    fontweight="bold", style="italic",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF3E0", edgecolor=RED, alpha=0.9))

        ax.set_title(f'Week {wave["week"]}: {wave["label"]}', fontsize=13, fontweight="bold",
                     color=week_colors[idx])
        ax.set_xticks(sets)
        ax.set_xticklabels([f"Set {s}" for s in sets], fontsize=9)
        ax.set_ylim(0, 110)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if idx == 0:
            ax.set_ylabel("% of Training Max", fontsize=12)

    fig.suptitle("Wendler 5/3/1 — Wave Loading Structure (4-Week Cycle)\n",
                 fontsize=19, fontweight="bold", color="#0D47A1", y=1.03)
    fig.tight_layout()
    fig.savefig(f"{OUT}/png_531_wave_structure.png", dpi=DPI)
    plt.close(fig)
    print("  [4/6] 5/3/1 wave structure")


# ═══════════════════════════════════════════════════════════════════════
# 5. SUPPLEMENT DOSING CHART
# ═══════════════════════════════════════════════════════════════════════
def fig_dosing():
    fig, ax = plt.subplots(figsize=(16, 9))

    # Extract dosing info for each supplement
    dosing_data = []
    for s in sorted(SUPPLEMENTS, key=lambda x: x["priority_rank"]):
        opt = s["dosing_options"][0]
        name = s["name"]
        dose_str = ""
        dose_val = 0
        unit = ""
        if "dose_g_per_day" in opt and opt["dose_g_per_day"]:
            dose_val = opt["dose_g_per_day"]
            unit = "g/day"
            dose_str = f"{dose_val} {unit}"
        elif "dose_mg_per_kg" in opt and opt["dose_mg_per_kg"]:
            dose_val = opt["dose_mg_per_kg"] * 80  # ~80 kg reference
            unit = f"mg (~80kg)"
            dose_str = f"{opt['dose_mg_per_kg']} mg/kg = ~{dose_val:.0f} mg"
        elif "dose_g_per_serving" in opt and opt["dose_g_per_serving"]:
            dose_val = opt["dose_g_per_serving"]
            unit = "g/serving"
            dose_str = f"{dose_val} {unit}"
        elif "dose_mg_per_day" in opt and opt["dose_mg_per_day"]:
            dose_val = opt["dose_mg_per_day"] / 1000  # Convert to g for scale
            unit = f"mg/day"
            dose_str = f"{opt['dose_mg_per_day']} {unit}"
        elif "dose_iu_per_day" in opt and opt["dose_iu_per_day"]:
            dose_val = opt["dose_iu_per_day"] / 1000
            unit = "IU/day"
            dose_str = f"{opt['dose_iu_per_day']} {unit}"

        dosing_data.append({
            "name": name,
            "dose_val": dose_val,
            "dose_str": dose_str,
            "timing": s.get("timing", "N/A"),
            "evidence": s["evidence_level"],
            "rank": s["priority_rank"],
        })

    names = [d["name"] for d in dosing_data]
    y_pos = np.arange(len(names))
    vals = [d["dose_val"] for d in dosing_data]
    colors = [EVIDENCE_COLORS[d["evidence"]] for d in dosing_data]

    bars = ax.barh(y_pos, vals, color=colors, edgecolor="white", linewidth=1.5, height=0.6, alpha=0.85)

    for i, (bar, d) in enumerate(zip(bars, dosing_data)):
        # Dose string
        ax.text(max(bar.get_width(), 0.3) + 0.2, bar.get_y() + bar.get_height()/2,
                f'{d["dose_str"]}   |   {d["timing"][:45]}',
                va="center", ha="left", fontsize=8.5, color="#333")
        # Rank badge
        ax.text(0.15, bar.get_y() + bar.get_height()/2,
                f'#{d["rank"]}', va="center", ha="left", fontsize=9, fontweight="bold", color="white")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=11, fontweight="bold")
    ax.set_title("Supplement Dosing Protocol & Timing Guide\n", fontsize=18, fontweight="bold", color="#1A237E")
    ax.set_xlabel("Dose (normalized scale)", fontsize=11)
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    legend_patches = [
        mpatches.Patch(color=EVIDENCE_COLORS["strong"], label="Strong Evidence"),
        mpatches.Patch(color=EVIDENCE_COLORS["moderate"], label="Moderate Evidence"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=11, framealpha=0.9)

    fig.savefig(f"{OUT}/png_supplement_dosing.png", dpi=DPI)
    plt.close(fig)
    print("  [5/6] Supplement dosing")


# ═══════════════════════════════════════════════════════════════════════
# 6. FOOD SOURCES INFOGRAPHIC
# ═══════════════════════════════════════════════════════════════════════
def fig_food_sources():
    fig = plt.figure(figsize=(20, 12))
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.25)

    categories = [
        ("Protein Sources", FOOD_SOURCES["protein"], RED, "protein"),
        ("Carbohydrate Sources", FOOD_SOURCES["carbohydrates"], GOLD, "carbs"),
        ("Fat Sources", FOOD_SOURCES["fats"], BLUE, "fats"),
        ("Micronutrient-Rich Foods", FOOD_SOURCES["micronutrients"], GREEN, "micros"),
    ]

    positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

    for (title, foods, color, _), (r, c) in zip(categories, positions):
        ax = fig.add_subplot(gs[r, c])
        ax.set_xlim(0, 10)
        ax.set_ylim(0, len(foods) + 1)
        ax.invert_yaxis()

        # Title bar
        ax.add_patch(mpatches.FancyBboxPatch(
            (0, 0), 10, 0.85, boxstyle="round,pad=0.1",
            facecolor=color, edgecolor="none", alpha=0.9
        ))
        ax.text(5, 0.42, title, ha="center", va="center", fontsize=14,
                fontweight="bold", color="white")

        for i, food in enumerate(foods):
            y = i + 1.2
            ax.add_patch(mpatches.FancyBboxPatch(
                (0.2, y - 0.3), 9.6, 0.6, boxstyle="round,pad=0.05",
                facecolor=color, edgecolor="none", alpha=0.08
            ))
            ax.text(0.5, y, f"\u25B8  {food}", va="center", fontsize=9.5, color="#333")

        ax.axis("off")

    fig.suptitle("Powerlifting Nutrition — Recommended Food Sources\n",
                 fontsize=22, fontweight="bold", color="#0D47A1", y=0.98)
    fig.savefig(f"{OUT}/png_food_sources.png", dpi=DPI)
    plt.close(fig)
    print("  [6/6] Food sources")


# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"Generating ultra-high-resolution PNGs at {DPI} DPI...\n")
    fig_programs()
    fig_supplements()
    fig_nutrition_phases()
    fig_531()
    fig_dosing()
    fig_food_sources()
    print(f"\nAll 6 PNGs saved to: {OUT}/")
    print(f"Resolution: {DPI} DPI (ultra-high)")
