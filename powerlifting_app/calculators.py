"""
calculators.py — Core calculation logic for the powerlifting tracker.

All functions are pure (no side effects) and unit-testable.
"""

from __future__ import annotations

import math
from typing import Optional

from data import ACTIVITY_MULTIPLIERS, NUTRITION_PHASES, PROGRAMS, SUPPLEMENTS


# ===========================================================================
# 1. Strength / 1RM Calculators
# ===========================================================================

def epley_1rm(weight: float, reps: int) -> float:
    """
    Epley formula for estimated 1 rep max.
    e1RM = weight × (1 + reps / 30)

    Args:
        weight: lifted weight in any consistent unit (kg or lb).
        reps:   number of reps completed (must be ≥ 1).

    Returns:
        Estimated 1RM in the same unit as weight.
    """
    if reps <= 0:
        raise ValueError("reps must be ≥ 1")
    if reps == 1:
        return weight
    return weight * (1 + reps / 30)


def brzycki_1rm(weight: float, reps: int) -> float:
    """
    Brzycki formula for estimated 1RM.
    e1RM = weight × 36 / (37 − reps)
    Valid for 1–10 reps; accuracy degrades above 10.
    """
    if reps <= 0:
        raise ValueError("reps must be ≥ 1")
    if reps >= 37:
        raise ValueError("Brzycki formula undefined for reps ≥ 37")
    if reps == 1:
        return weight
    return weight * 36 / (37 - reps)


def percentage_of_1rm(one_rm: float, percentage: float) -> float:
    """
    Calculate a target weight as a percentage of 1RM.

    Args:
        one_rm:     1 rep max.
        percentage: percentage value (e.g., 85 for 85%).

    Returns:
        Target weight, rounded to nearest 2.5 kg for practical use.
    """
    raw = one_rm * percentage / 100
    # Round to nearest 2.5 for standard plate math
    return round(raw / 2.5) * 2.5


def training_max_from_1rm(one_rm: float, tm_percentage: float = 90.0) -> float:
    """
    Compute a training max (used in 5/3/1 and nSuns).

    Args:
        one_rm:         True 1RM.
        tm_percentage:  Percentage to use as training max (default 90%).

    Returns:
        Training max, rounded to nearest 2.5 kg.
    """
    return percentage_of_1rm(one_rm, tm_percentage)


def build_531_week(lift: str, training_max: float, week: int) -> list[dict]:
    """
    Generate the prescribed sets/reps/weights for a given 5/3/1 week.

    Args:
        lift:         Lift name (informational only).
        training_max: Training max in kg.
        week:         Week number 1–4 (4 = deload).

    Returns:
        List of dicts with keys: set_number, percentage, target_weight_kg,
        prescribed_reps, is_amrap.
    """
    program = next((p for p in PROGRAMS if p["id"] == "531"), None)
    if program is None:
        raise RuntimeError("5/3/1 program data not found in data.py")

    wave = next((w for w in program["wave_structure"] if w["week"] == week), None)
    if wave is None:
        raise ValueError(f"Week {week} not found in 5/3/1 wave structure (valid: 1–4)")

    sets = []
    for i, (pct, reps) in enumerate(zip(wave["percentages"], wave["reps"]), start=1):
        target = percentage_of_1rm(training_max, pct)
        is_amrap = (i == 3) and (week != 4)   # Last set is AMRAP except deload
        sets.append(
            {
                "set_number": i,
                "percentage": pct,
                "target_weight_kg": target,
                "prescribed_reps": reps,
                "is_amrap": is_amrap,
                "label": f"Set {i}: {pct}% × {reps}{'+ (AMRAP)' if is_amrap else ''}",
            }
        )
    return sets


def advance_531_training_max(
    training_max: float, lift_type: str = "lower"
) -> float:
    """
    Advance training max after completing one 5/3/1 cycle.

    Args:
        training_max: Current training max in kg.
        lift_type:    "upper" (bench/OHP) → +2.5 kg; "lower" (squat/DL) → +5 kg.

    Returns:
        New training max.
    """
    increments = {"upper": 2.5, "lower": 5.0}
    if lift_type not in increments:
        raise ValueError(f"lift_type must be 'upper' or 'lower', got {lift_type!r}")
    return training_max + increments[lift_type]


# ===========================================================================
# 2. Nutrition Calculators
# ===========================================================================

def mifflin_st_jeor_bmr(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: str,
) -> float:
    """
    Mifflin-St Jeor Basal Metabolic Rate.

    Male:   10W + 6.25H − 5A + 5
    Female: 10W + 6.25H − 5A − 161

    Args:
        weight_kg: Body weight in kg.
        height_cm: Height in cm.
        age:       Age in years.
        sex:       "male" or "female".

    Returns:
        BMR in kcal/day.
    """
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex.lower() == "male" else base - 161


def calculate_tdee(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: str,
    activity_level: str,
) -> float:
    """
    Total Daily Energy Expenditure = BMR × activity multiplier.

    Args:
        weight_kg:      Body weight in kg.
        height_cm:      Height in cm.
        age:            Age in years.
        sex:            "male" or "female".
        activity_level: Key from ACTIVITY_MULTIPLIERS dict.

    Returns:
        TDEE in kcal/day.
    """
    if activity_level not in ACTIVITY_MULTIPLIERS:
        valid = list(ACTIVITY_MULTIPLIERS.keys())
        raise ValueError(f"activity_level must be one of {valid}, got {activity_level!r}")

    bmr = mifflin_st_jeor_bmr(weight_kg, height_cm, age, sex)
    return bmr * ACTIVITY_MULTIPLIERS[activity_level]


def calculate_macros(
    tdee: float,
    weight_kg: float,
    phase: str,
) -> dict:
    """
    Calculate daily macro targets for a given nutrition phase.

    Args:
        tdee:       Maintenance TDEE in kcal/day.
        weight_kg:  Body weight in kg (used for protein/carb g/kg targets).
        phase:      Phase key: "lean_bulk", "aggressive_bulk", "cut",
                    "maintenance", or "meet_peak".

    Returns:
        Dict with keys: phase, target_calories, protein_g, carbs_g, fat_g,
        protein_pct, carbs_pct, fat_pct.
    """
    phase_data = next((p for p in NUTRITION_PHASES if p["phase"] == phase), None)
    if phase_data is None:
        valid = [p["phase"] for p in NUTRITION_PHASES]
        raise ValueError(f"phase must be one of {valid}, got {phase!r}")

    target_calories = tdee + phase_data["calorie_surplus_deficit"]

    protein_g = weight_kg * phase_data["protein_g_per_kg"]
    carbs_g = weight_kg * phase_data["carbs_g_per_kg"]

    # Fat: fill remaining calories up to the target fat_pct_of_calories
    # Prioritize hitting protein and carb g/kg targets first, then fill fat
    protein_kcal = protein_g * 4
    carbs_kcal = carbs_g * 4
    remaining_kcal = target_calories - protein_kcal - carbs_kcal
    fat_g = max(remaining_kcal / 9, weight_kg * 0.5)  # Minimum 0.5 g/kg fat

    # Recalculate calories with actual macros
    actual_calories = protein_kcal + carbs_kcal + fat_g * 9

    result = {
        "phase": phase_data["label"],
        "target_calories": round(target_calories),
        "actual_calories": round(actual_calories),
        "protein_g": round(protein_g),
        "carbs_g": round(carbs_g),
        "fat_g": round(fat_g),
        "protein_pct": round(protein_kcal / actual_calories * 100, 1),
        "carbs_pct": round(carbs_kcal / actual_calories * 100, 1),
        "fat_pct": round(fat_g * 9 / actual_calories * 100, 1),
        "notes": phase_data["notes"],
    }

    # Warn if macro g/kg targets produce calories that exceed the caloric target
    if actual_calories > target_calories * 1.1:
        result["overflow_warning"] = (
            f"Macro g/kg targets exceed your caloric target "
            f"({round(actual_calories)} vs {round(target_calories)} kcal). "
            "Consider reducing carb targets or increasing activity level."
        )

    return result


def calculate_pre_workout_meal(
    target_calories: float,
    timing_hours: float = 2.5,
) -> dict:
    """
    Suggest a pre-workout meal composition.

    Args:
        target_calories: Athlete's daily caloric target.
        timing_hours:    Hours before training (default 2–3 hours out).

    Returns:
        Dict with suggested protein_g, carbs_g, fat_g, and timing notes.
    """
    # Pre-workout meal is roughly 20–25% of daily calories for a full meal
    # Use conservative targets from research
    if timing_hours >= 2.0:
        protein_g = 25   # midpoint of 20–30 g
        carbs_g = 45     # midpoint of 30–60 g
        fat_g = 15       # moderate fat; avoid very high fat close to training
        timing_note = f"Eat {timing_hours:.0f}h before training for full digestion."
    else:
        # Close to training — lighter, easily digestible
        protein_g = 20
        carbs_g = 30
        fat_g = 5
        timing_note = "Close to training — keep this light and liquid/blended for faster emptying."

    return {
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "approx_kcal": protein_g * 4 + carbs_g * 4 + fat_g * 9,
        "timing_note": timing_note,
    }


# ===========================================================================
# 3. Supplement Calculators
# ===========================================================================

def creatine_loading_dose(weight_kg: float) -> float:
    """
    Calculate loading phase creatine dose.
    Protocol: 0.3 g/kg/day split into 4–5 doses for 5–7 days.
    """
    return weight_kg * 0.3


def caffeine_dose(weight_kg: float, mg_per_kg: float = 4.5) -> float:
    """
    Calculate caffeine dose from body weight.

    Args:
        weight_kg:  Body weight in kg.
        mg_per_kg:  Target dose in mg/kg. Effective range 3–6 mg/kg.
                    Default 4.5 mg/kg (midpoint).

    Returns:
        Total caffeine in mg, capped at 400 mg for safety.
    """
    if not 3.0 <= mg_per_kg <= 6.0:
        raise ValueError("mg_per_kg must be between 3.0 and 6.0 (evidence-based range)")
    dose = weight_kg * mg_per_kg
    return min(dose, 400.0)   # Hard cap for safety


def get_supplement_stack(priority_level: int = 3) -> list[dict]:
    """
    Return a recommended supplement stack up to the given priority tier.

    Args:
        priority_level: Include supplements with priority_rank ≤ this value.
                        1 = just creatine; 3 = Tier 1 (strong evidence) only;
                        5 = add Tier 2 volume/recovery; 9 = full stack.

    Returns:
        List of supplement dicts from SUPPLEMENTS, sorted by priority.
    """
    stack = [s for s in SUPPLEMENTS if s["priority_rank"] <= priority_level]
    return sorted(stack, key=lambda s: s["priority_rank"])


# ===========================================================================
# 4. Progress Analytics
# ===========================================================================

def calculate_wilks(
    bodyweight_kg: float,
    total_kg: float,
    sex: str,
) -> float:
    """
    Wilks score — a bodyweight-relative strength standard for powerlifting.

    Formula: Score = total × 500 / (a + bBW + cBW² + dBW³ + eBW⁴ + fBW⁵)

    Coefficients for male/female from Wilks (1998).

    Args:
        bodyweight_kg: Athlete body weight in kg.
        total_kg:      Competition total (squat + bench + deadlift) in kg.
        sex:           "male" or "female".

    Returns:
        Wilks score (unitless; higher = stronger relative to body weight).
    """
    if not (40.0 <= bodyweight_kg <= 200.0):
        raise ValueError(
            f"bodyweight_kg must be between 40 and 200 kg for reliable Wilks scores, "
            f"got {bodyweight_kg}"
        )
    if sex.lower() == "male":
        a = -216.0475144
        b = 16.2606339
        c = -0.002388645
        d = -0.00113732
        e = 7.01863e-06
        f = -1.291e-08
    else:  # female
        a = 594.31747775582
        b = -27.23842536447
        c = 0.82112226871
        d = -0.00930733913
        e = 4.731582e-05
        f = -9.054e-08

    denominator = (
        a
        + b * bodyweight_kg
        + c * bodyweight_kg ** 2
        + d * bodyweight_kg ** 3
        + e * bodyweight_kg ** 4
        + f * bodyweight_kg ** 5
    )
    if denominator <= 0:
        raise ValueError(f"Wilks denominator ≤ 0 for bodyweight={bodyweight_kg} kg (out of range?)")
    return total_kg * 500 / denominator


def strength_level_label(wilks: float) -> str:
    """
    Return a qualitative strength label based on Wilks score.

    Rough community standards (open category):
        < 200  — Beginner
        200–300 — Novice
        300–400 — Intermediate
        400–500 — Advanced
        500–600 — Elite
        > 600  — World-class
    """
    if wilks < 200:
        return "Beginner"
    elif wilks < 300:
        return "Novice"
    elif wilks < 400:
        return "Intermediate"
    elif wilks < 500:
        return "Advanced"
    elif wilks < 600:
        return "Elite"
    else:
        return "World-class"


def calculate_volume_progression(
    sessions: list,  # list[WorkoutSession]
    lift_name: str,
) -> list[dict]:
    """
    Extract weekly volume (kg) for a specific lift across sessions.

    Args:
        sessions:   Sorted list of WorkoutSession objects.
        lift_name:  Name of the lift to analyse (case-insensitive).

    Returns:
        List of dicts: {"date": str, "volume_kg": float, "heaviest_kg": float,
                        "total_reps": int}
    """
    results = []
    for session in sessions:
        exercise = session.get_exercise(lift_name)
        if exercise is None:
            continue
        results.append(
            {
                "date": session.date,
                "volume_kg": exercise.total_volume_kg,
                "heaviest_kg": exercise.heaviest_set_kg,
                "total_reps": exercise.total_reps,
                "session_id": session.session_id,
            }
        )
    return results


def estimate_program_duration_weeks(program_id: str) -> Optional[int]:
    """
    Return the fixed length of a program in weeks, or None if open-ended.
    """
    program = next((p for p in PROGRAMS if p["id"] == program_id), None)
    if program is None:
        raise ValueError(f"Program '{program_id}' not found")
    return program.get("program_length_weeks")
