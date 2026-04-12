"""
data.py — Static reference data for programs, nutrition, and supplements.

All values derived from the researcher's compiled findings (April 10, 2026).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Powerlifting Programs
# ---------------------------------------------------------------------------

PROGRAMS: list[dict] = [
    {
        "id": "starting_strength",
        "name": "Starting Strength",
        "author": "Mark Rippetoe",
        "level": "beginner",
        "frequency_days_per_week": 3,
        "progression_type": "linear_per_session",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift", "Overhead Press", "Power Clean"],
        "sets_reps_scheme": "3×5 (Deadlift: 1×5; Power Clean: 5×3)",
        "training_max_percentage": None,
        "program_length_weeks": None,  # Open-ended; novice runs it until stalling
        "description": (
            "Full-body 3 days/week, alternating Workout A and B. "
            "Squat every session. Add ~5 lb/session upper body, ~10 lb lower body. "
            "Focuses on mastery of a small set of compound barbell movements."
        ),
        "best_for": "Absolute beginners (0–6 months of training)",
        "pros": "Simple, highly effective for beginners, rapid strength gains.",
        "cons": "Limited variety; becomes inadequate after a few months; high squat frequency can fatigue.",
        "weekly_progression_lb": {"upper": 7.5, "lower": 10},
    },
    {
        "id": "stronglifts_5x5",
        "name": "StrongLifts 5×5",
        "author": "Mehdi Hadim",
        "level": "beginner",
        "frequency_days_per_week": 3,
        "progression_type": "linear_per_session",
        "primary_lifts": ["Squat", "Bench Press", "Barbell Row", "Overhead Press", "Deadlift"],
        "sets_reps_scheme": "5×5",
        "training_max_percentage": None,
        "program_length_weeks": None,
        "description": (
            "Alternating Workout A (Squat, Bench, Row) and B (Squat, OHP, Deadlift). "
            "5×5 sets/reps with linear progression each session."
        ),
        "best_for": "Beginners similar to Starting Strength.",
        "pros": "Simple, app-supported, beginner-friendly.",
        "cons": "Higher volume than SS can be harder to recover; limited variety.",
        "weekly_progression_lb": {"upper": 5, "lower": 10},
    },
    {
        "id": "gzclp",
        "name": "GZCLP",
        "author": "Cody Lefever",
        "level": "beginner",
        "frequency_days_per_week": 4,
        "progression_type": "linear_per_session",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift", "Overhead Press"],
        "sets_reps_scheme": "T1: 5×3 (last set AMRAP); T2: 3×10",
        "training_max_percentage": None,
        "program_length_weeks": None,
        "description": (
            "Beginner version of the GZCL method. Tier 1 (T1): competition lifts at 5×3 "
            "with last-set AMRAP; progress when AMRAP ≥ 5 reps. T2: secondary lifts at 3×10. "
            "Upper/Lower 4-day split."
        ),
        "best_for": "Beginners wanting more structure than Starting Strength.",
        "pros": "Flexible, intelligent volume structure, fail-state progressions built in.",
        "cons": "More complex setup than SS/SL; can confuse beginners.",
        "weekly_progression_lb": {"upper": 5, "lower": 10},
    },
    {
        "id": "531",
        "name": "Jim Wendler 5/3/1",
        "author": "Jim Wendler",
        "level": "intermediate",
        "frequency_days_per_week": 4,
        "progression_type": "linear_per_week",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift", "Overhead Press"],
        "sets_reps_scheme": "Wave: Week1=3×5 (65/75/85%), Week2=3×3 (70/80/90%), Week3=3×5-3-1 (75/85/95%), Week4=Deload",
        "training_max_percentage": 90,
        "program_length_weeks": 4,  # One cycle; repeats indefinitely
        "description": (
            "Percentage-based loading off a Training Max (90% of true 1RM). "
            "Each week has a progressive wave of sets; last set is AMRAP. "
            "Many accessory templates available (BBB, FSL, etc.). "
            "Cycle progression: +5 lb upper, +10 lb lower Training Max per cycle."
        ),
        "best_for": "Intermediate lifters (6+ months); sustainable long-term training.",
        "pros": "Sustainable, flexible, extremely popular, well-documented.",
        "cons": "Slow progression by design; not optimal for pure beginners; requires patience.",
        "cycle_tm_increase_lb": {"upper": 5, "lower": 10},
        "wave_structure": [
            {"week": 1, "label": "5s Week", "sets": 3, "reps": [5, 5, 5], "percentages": [65, 75, 85]},
            {"week": 2, "label": "3s Week", "sets": 3, "reps": [3, 3, 3], "percentages": [70, 80, 90]},
            {"week": 3, "label": "5/3/1 Week", "sets": 3, "reps": [5, 3, 1], "percentages": [75, 85, 95]},
            {"week": 4, "label": "Deload", "sets": 3, "reps": [5, 5, 5], "percentages": [40, 50, 60]},
        ],
    },
    {
        "id": "nsuns",
        "name": "nSuns 5/3/1 LP",
        "author": "nSuns (anonymous Reddit user)",
        "level": "intermediate",
        "frequency_days_per_week": 5,  # 4-, 5-, or 6-day variants; 5 is most common
        "progression_type": "linear_per_week",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift", "Overhead Press"],
        "sets_reps_scheme": "9 working sets on main lift; AMRAP autoregulates weekly TM increase",
        "training_max_percentage": 90,
        "program_length_weeks": None,
        "description": (
            "High-volume variant of 5/3/1. Weekly AMRAP autoregulation: 3+ reps → increase TM, "
            "1–2 reps → no change, <1 rep → decrease TM by 10 lb. "
            "Main lift paired with competition lift each day for extra volume."
        ),
        "best_for": "Late-stage novice to early intermediate wanting rapid progress through volume.",
        "pros": "Very high volume; rapid strength and size gains; autoregulated.",
        "cons": "High fatigue; not for beginners; no formal coaching pedigree.",
        "weekly_tm_change_lb": {"increase_3plus_reps": {"upper": 5, "lower": 10}, "decrease_fail": -10},
    },
    {
        "id": "texas_method",
        "name": "Texas Method",
        "author": "Mark Rippetoe / Glenn Pendlay",
        "level": "intermediate",
        "frequency_days_per_week": 3,
        "progression_type": "linear_per_week",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift", "Overhead Press"],
        "sets_reps_scheme": "Volume Day: 5×5 (~90% Friday); Recovery Day: 3×5 (~80%); Intensity Day: 1×5 PR",
        "training_max_percentage": None,
        "program_length_weeks": None,
        "description": (
            "3 days/week (Mon/Wed/Fri). Volume Day provides stimulus; Recovery Day promotes "
            "recovery with lighter work; Intensity Day achieves new PR. Increase Friday weight 5 lb/week."
        ),
        "best_for": "Intermediate lifters transitioning out of linear progression.",
        "pros": "Great bridge from LP to complex periodization; teaches weekly periodization.",
        "cons": "Stalls quickly without optimal nutrition/sleep; less volume than some intermediates need.",
        "weekly_progression_lb": 5,
    },
    {
        "id": "madcow_5x5",
        "name": "Madcow 5×5",
        "author": "Madcow (Bill Starr variant)",
        "level": "intermediate",
        "frequency_days_per_week": 3,
        "progression_type": "linear_per_week",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift", "Barbell Row", "Overhead Press"],
        "sets_reps_scheme": "Ramping sets of 5 (pyramid up to heavy 5); Heavy/Light/Medium weekly structure",
        "training_max_percentage": None,
        "program_length_weeks": None,
        "description": (
            "Full-body 3 days/week. Ramping sets up to a top set of 5. "
            "Heavy day Monday, Light day Wednesday, Medium day Friday. "
            "Weekly progression ~2.5–5% increase on top set."
        ),
        "best_for": "Intermediate lifters; emphasis on simultaneous size and strength.",
        "pros": "Good hypertrophy emphasis; structured template.",
        "cons": "Similar stall points to Texas Method.",
        "weekly_progression_pct": 3.0,
    },
    {
        "id": "gzcl_method",
        "name": "GZCL Method",
        "author": "Cody Lefever",
        "level": "all",
        "frequency_days_per_week": 4,
        "progression_type": "undulating",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift", "Overhead Press"],
        "sets_reps_scheme": (
            "T1 >85% 1RM: 5×3 AMRAP; T2 65–85%: 20–30 total reps (sets of 5–8); "
            "T3 <65%: 30+ total reps (3×10+)"
        ),
        "training_max_percentage": None,
        "program_length_weeks": None,
        "description": (
            "Tier-based system: T1 = main competition lifts at high intensity, "
            "T2 = secondary compounds for volume, T3 = accessories. "
            "1:2:3 rule — for every T1 rep, do 2× T2 reps and 3× T3 reps."
        ),
        "best_for": "All levels; highly adaptable to any goal.",
        "pros": "Extremely flexible; intelligent volume management; works across all levels.",
        "cons": "More complex to set up; can confuse beginners without guidance.",
    },
    {
        "id": "sheiko",
        "name": "Sheiko",
        "author": "Boris Sheiko",
        "level": "advanced",
        "frequency_days_per_week": 4,
        "progression_type": "block",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift"],
        "sets_reps_scheme": "Submaximal 70–85% 1RM; very high total volume; competition-lift frequency",
        "training_max_percentage": 85,
        "program_length_weeks": 12,
        "description": (
            "Russian powerlifting methodology. High frequency: Bench 3×/week, Squat 2–3×/week, "
            "Deadlift 1–2×/week. 12-week structure: Preparatory (wk 1–4) → Intensification (wk 5–8) "
            "→ Peaking (wk 9–12)."
        ),
        "best_for": "Intermediate-to-advanced; technical development focus.",
        "pros": "Excellent technique development; proven methodology.",
        "cons": "Very high volume; requires substantial recovery; not for beginners/early intermediates.",
    },
    {
        "id": "conjugate_westside",
        "name": "Conjugate / Westside Barbell",
        "author": "Louie Simmons",
        "level": "advanced",
        "frequency_days_per_week": 4,
        "progression_type": "conjugate",
        "primary_lifts": ["Squat", "Bench Press", "Deadlift"],
        "sets_reps_scheme": "ME: work to 1–3RM; DE: 9×3 @ 50–60% with maximal bar speed",
        "training_max_percentage": None,
        "program_length_weeks": None,
        "description": (
            "4 days/week: ME Upper, ME Lower, DE Upper, DE Lower. Max Effort (ME): "
            "work to a 1–3RM on a main lift variation, rotate every 1–3 weeks. "
            "Dynamic Effort (DE): 9×3 at 50–60% 1RM for speed; often uses bands/chains."
        ),
        "best_for": "Advanced powerlifters; equipped lifters; athletes with strong GPP base.",
        "pros": "Highly effective for advanced athletes; develops power and addresses weaknesses.",
        "cons": "Complex; not appropriate for beginners/intermediates; geared toward equipped lifting.",
    },
]


# ---------------------------------------------------------------------------
# Nutrition Reference Data
# ---------------------------------------------------------------------------

NUTRITION_PHASES: list[dict] = [
    {
        "phase": "lean_bulk",
        "label": "Lean Bulk",
        "calorie_surplus_deficit": 400,   # kcal/day above TDEE (midpoint of 300–500)
        "rate_of_change_pct_bw_per_month": 0.75,  # midpoint of 0.5–1%
        "protein_g_per_kg": 2.0,
        "carbs_g_per_kg": 6.0,            # midpoint of 4–8
        "fat_pct_of_calories": 22.5,      # midpoint of 20–25%
        "notes": "Minimize fat gain while building muscle. Sustainable approach.",
    },
    {
        "phase": "aggressive_bulk",
        "label": "Aggressive Bulk",
        "calorie_surplus_deficit": 625,   # midpoint of 500–750
        "rate_of_change_pct_bw_per_month": 1.25,
        "protein_g_per_kg": 2.0,
        "carbs_g_per_kg": 7.0,
        "fat_pct_of_calories": 22.5,
        "notes": "More muscle gain but more fat accumulation. Only recommended for very lean lifters.",
    },
    {
        "phase": "cut",
        "label": "Cut",
        "calorie_surplus_deficit": -400,  # deficit
        "rate_of_change_pct_bw_per_week": 0.75,   # 0.5–1% per week
        "protein_g_per_kg": 2.3,          # higher to preserve muscle
        "carbs_g_per_kg": 4.0,
        "fat_pct_of_calories": 22.5,
        "notes": "Higher protein (~2.2–2.4 g/kg) to preserve muscle mass during deficit.",
    },
    {
        "phase": "maintenance",
        "label": "Maintenance / Recomp",
        "calorie_surplus_deficit": 0,
        "protein_g_per_kg": 1.9,          # midpoint of 1.8–2.0
        "carbs_g_per_kg": 5.0,
        "fat_pct_of_calories": 22.5,
        "notes": "Slow body recomposition possible for beginners. Prioritize performance.",
    },
    {
        "phase": "meet_peak",
        "label": "Meet Peak",
        "calorie_surplus_deficit": 0,     # depends on weight class management
        "protein_g_per_kg": 2.0,
        "carbs_g_per_kg": 6.0,
        "fat_pct_of_calories": 22.5,
        "notes": "Adjust 4–8 weeks out for weight class. Carb timing around training is critical.",
    },
]

ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary":       1.2,   # desk job, little/no exercise
    "lightly_active":  1.4,   # light exercise 1–3 days/week
    "moderately_active": 1.55, # moderate exercise 3–5 days/week
    "very_active":     1.7,   # hard exercise 6–7 days/week
    "extremely_active": 1.9,  # very hard exercise + physical job
}

MEAL_TIMING: dict = {
    "pre_workout_timing_hours": "2–4 hours before training",
    "pre_workout_protein_g": "20–30 g",
    "pre_workout_carbs_g": "30–60 g",
    "intra_workout_note": (
        "Not required for sessions ≤90 min. "
        "For longer sessions: 30–60 g carbs/hour."
    ),
    "post_workout_protein_g": "20–40 g",
    "post_workout_window": "Within 2 hours of training (window is wide)",
    "meal_frequency": "3–6 meals/day; distribute protein evenly (~20–40 g per meal)",
    "max_protein_gap_hours": 5,
}

FOOD_SOURCES: dict[str, list[str]] = {
    "protein": [
        "Chicken breast / turkey (lean, versatile)",
        "Lean ground beef, sirloin steak (creatine, iron, zinc)",
        "Eggs and egg whites (complete amino acids)",
        "Salmon, tuna, tilapia (salmon adds omega-3s)",
        "Greek yogurt, cottage cheese (casein protein, calcium)",
        "Whey / casein protein powder (convenience)",
        "Beans, lentils (plant-based option)",
    ],
    "carbohydrates": [
        "White rice (easy to digest, quick energy)",
        "Oats (slow-digesting, good fiber)",
        "Sweet potatoes and white potatoes (micronutrient-dense)",
        "Bananas (quick carbs pre-workout)",
        "Whole grain bread and pasta",
        "Brown rice (fiber, micronutrients)",
    ],
    "fats": [
        "Avocado (monounsaturated fats, potassium)",
        "Olive oil (anti-inflammatory)",
        "Nuts and nut butters (energy-dense)",
        "Salmon, mackerel, sardines (omega-3 EPA/DHA)",
        "Whole eggs (nutrient-dense, supports testosterone)",
    ],
    "micronutrients": [
        "Spinach, leafy greens (iron, magnesium, nitrates)",
        "Broccoli, colorful vegetables (antioxidants, vitamins)",
        "Berries (antioxidants, recovery support)",
        "Milk / dairy (calcium, vitamin D, leucine)",
    ],
}


# ---------------------------------------------------------------------------
# Supplements
# ---------------------------------------------------------------------------

SUPPLEMENTS: list[dict] = [
    {
        "id": "creatine_monohydrate",
        "name": "Creatine Monohydrate",
        "evidence_level": "strong",
        "priority_rank": 1,
        "primary_benefit": "Strength, power output, muscle mass",
        "mechanism": (
            "Increases phosphocreatine stores → faster ATP regeneration → "
            "more reps at high intensity → greater training volume over time."
        ),
        "benefits": [
            "Increases 1RM strength (well-established)",
            "Increases power output",
            "Improves repeated sprint/rep performance",
            "May aid recovery (2026 loading study)",
            "Emerging cognitive benefits",
        ],
        "dosing_options": [
            {
                "protocol": "Loading phase",
                "dose_g_per_day": 20,
                "duration": "5–7 days",
                "notes": "Saturates muscles faster. ~0.3 g/kg body weight/day.",
            },
            {
                "protocol": "Maintenance (post-loading or no-load)",
                "dose_g_per_day": 3.5,
                "duration": "Ongoing",
                "notes": "Midpoint of 3–5 g/day. Full saturation in 3–4 weeks without loading.",
            },
        ],
        "timing": "Timing not critical; consistency matters most.",
        "form_note": "Monohydrate is gold standard. No evidence HCl or ethyl ester are superior.",
        "safety": "Extremely well-studied; safe for healthy individuals; stay well hydrated.",
        "cost_effectiveness": "Most cost-effective performance supplement available.",
    },
    {
        "id": "caffeine",
        "name": "Caffeine",
        "evidence_level": "strong",
        "priority_rank": 2,
        "primary_benefit": "Performance, focus, strength under fatigue",
        "mechanism": (
            "Adenosine receptor antagonist → increased alertness, reduced perceived effort, "
            "improved neuromuscular function."
        ),
        "benefits": [
            "Consistently improves power output",
            "Improves strength, particularly when fatigued",
            "Enhanced focus and training motivation",
        ],
        "dosing_options": [
            {
                "protocol": "Pre-workout",
                "dose_mg_per_kg": 4.5,   # midpoint of 3–6 mg/kg
                "duration": "As needed",
                "notes": "Effective range 3–6 mg/kg. ~200–400 mg for most adults.",
            },
        ],
        "timing": "30–60 minutes before training.",
        "form_note": "Coffee, pre-workout supplements, or caffeine pills.",
        "safety": (
            "Avoid within 6 hours of sleep (half-life ~5–6 hours). "
            "Cycle off 1–2 weeks periodically to restore sensitivity. "
            "May cause anxiety/jitteriness at high doses."
        ),
        "cost_effectiveness": "Very high — coffee is cheap and effective.",
    },
    {
        "id": "whey_protein",
        "name": "Whey Protein",
        "evidence_level": "strong",
        "priority_rank": 3,
        "primary_benefit": "Muscle protein synthesis, convenient protein source",
        "mechanism": (
            "Complete amino acid profile; high leucine triggers MPS. "
            "Rapidly absorbed (fast-digesting)."
        ),
        "benefits": [
            "Complete amino acid profile with high leucine",
            "Rapidly absorbed — ideal post-workout or any time",
            "Consistently superior to plant proteins for muscle growth",
        ],
        "dosing_options": [
            {
                "protocol": "Post-workout or any meal needing protein boost",
                "dose_g_per_serving": 30,   # midpoint of 20–40 g
                "duration": "As needed",
                "notes": "Food-based protein is equally effective. Supplement for convenience only.",
            },
        ],
        "timing": "Post-workout or any time dietary protein is insufficient.",
        "form_note": "Casein (slow-releasing) ideal before bed at 30–40 g.",
        "safety": "Safe for healthy individuals meeting daily protein targets.",
        "cost_effectiveness": "High — cheap per gram of protein.",
    },
    {
        "id": "beta_alanine",
        "name": "Beta-Alanine",
        "evidence_level": "moderate",
        "priority_rank": 4,
        "primary_benefit": "Buffering fatigue during high-rep/high-intensity sets",
        "mechanism": (
            "Increases muscle carnosine → buffers lactic acid → delays fatigue "
            "during high-rep or repeated high-intensity efforts."
        ),
        "benefits": [
            "Increases carnosine up to 64% after 4 weeks",
            "Effective for 8+ rep work and repeated bouts",
            "5-week RCT: improved 1RM, power, total sets completed",
        ],
        "dosing_options": [
            {
                "protocol": "Loading phase",
                "dose_g_per_day": 4.8,   # midpoint of 3.2–6.4
                "duration": "4–6 weeks",
                "notes": "Split into 2–4 doses to minimize paresthesia.",
            },
            {
                "protocol": "Maintenance",
                "dose_g_per_day": 1.8,   # midpoint of 1.2–2.4
                "duration": "Ongoing",
                "notes": "Once carnosine is elevated, lower maintenance dose sufficient.",
            },
        ],
        "timing": "Split doses throughout the day; sustained-release reduces tingling.",
        "form_note": "Standard beta-alanine powder or sustained-release capsules.",
        "safety": "Paresthesia (skin tingling) is harmless. No major side effects.",
        "powerlifting_note": "More relevant for higher-rep blocks than pure 1RM work.",
    },
    {
        "id": "citrulline_malate",
        "name": "Citrulline Malate",
        "evidence_level": "moderate",
        "priority_rank": 5,
        "primary_benefit": "Training volume, reduced soreness",
        "mechanism": (
            "Increases arginine → more nitric oxide → improved blood flow; "
            "supports ammonia clearance reducing fatigue."
        ),
        "benefits": [
            "52.9% more reps in well-cited placebo-controlled study",
            "40% reduction in DOMS at 24–48 hours post-training",
            "Supports recovery between sets",
            "May improve aerobic performance",
        ],
        "dosing_options": [
            {
                "protocol": "Pre-workout",
                "dose_g_per_day": 7,   # midpoint of 6–8 g citrulline malate
                "duration": "As needed",
                "notes": "6–8 g citrulline malate (2:1) or 3–6 g L-citrulline. Take 60 min before.",
            },
        ],
        "timing": "60 minutes before training.",
        "form_note": "Often found in pre-workout supplements.",
        "safety": "Well-tolerated; no major side effects reported.",
        "powerlifting_note": "More relevant for higher-volume training than pure strength work.",
    },
    {
        "id": "fish_oil",
        "name": "Fish Oil (Omega-3: EPA/DHA)",
        "evidence_level": "moderate",
        "priority_rank": 6,
        "primary_benefit": "Recovery, anti-inflammation, joint health",
        "mechanism": (
            "Anti-inflammatory eicosanoid production; "
            "membrane phospholipid incorporation supports muscle function."
        ),
        "benefits": [
            "Reduces post-exercise inflammation (IL-6, TNF-α, CK)",
            "Reduces DOMS",
            "May modestly improve strength gains (2 g/day × 13 weeks study)",
            "Cardiovascular and joint health support",
        ],
        "dosing_options": [
            {
                "protocol": "Daily supplementation",
                "dose_mg_per_day": 3000,   # midpoint of 2,000–4,000 mg EPA+DHA
                "duration": "Ongoing (minimum 4.5 weeks for effect)",
                "notes": "At least 2,400 mg/day EPA+DHA combined. Elite athletes up to 4 g/day.",
            },
        ],
        "timing": "With meals to reduce fish burps.",
        "form_note": "Triglyceride form has better absorption than ethyl ester.",
        "safety": "Generally safe; high doses may thin blood — consult physician if on anticoagulants.",
        "food_alternative": "Fatty fish (salmon, mackerel, sardines) 2–3×/week.",
    },
    {
        "id": "vitamin_d",
        "name": "Vitamin D3",
        "evidence_level": "moderate",
        "priority_rank": 7,
        "primary_benefit": "Bone health, muscle function, hormones",
        "mechanism": (
            "Steroid hormone precursor; affects gene expression for muscle function, "
            "immune health, bone density, and testosterone production."
        ),
        "benefits": [
            "Supports bone health — reduces stress fracture risk",
            "Muscle function — deficiency causes weakness",
            "Immune function — reduces illness disruptions",
            "Testosterone production support",
        ],
        "dosing_options": [
            {
                "protocol": "Maintenance (sufficient levels)",
                "dose_iu_per_day": 1500,   # midpoint 1,000–2,000
                "duration": "Ongoing",
                "notes": "Take with fat-containing meal (fat-soluble).",
            },
            {
                "protocol": "Correction of deficiency",
                "dose_iu_per_day": 3500,   # midpoint 2,000–5,000
                "duration": "Until levels normalize",
                "notes": "Confirm with blood test first. Target 40–60 ng/mL.",
            },
        ],
        "timing": "With a fat-containing meal for best absorption.",
        "form_note": "D3 (cholecalciferol) preferred over D2.",
        "safety": "Toxicity possible at >10,000 IU/day chronic. Test blood levels before high-dose use.",
        "target_blood_level": "40–60 ng/mL (100–150 nmol/L)",
    },
    {
        "id": "magnesium",
        "name": "Magnesium",
        "evidence_level": "moderate",
        "priority_rank": 8,
        "primary_benefit": "Sleep quality, muscle function, testosterone",
        "mechanism": (
            "Involved in 300+ enzymatic reactions including ATP production, "
            "muscle contraction, protein synthesis, and testosterone regulation."
        ),
        "benefits": [
            "Improved sleep quality (especially glycinate form)",
            "Supports testosterone levels",
            "Reduces muscle cramps",
            "Muscle contraction and function support",
        ],
        "dosing_options": [
            {
                "protocol": "Daily supplementation",
                "dose_mg_per_day": 350,   # midpoint of 300–400 mg elemental
                "duration": "Ongoing",
                "notes": "Preferred forms: glycinate (best absorbed, least GI upset) or citrate.",
            },
        ],
        "timing": "Before bed — enhances sleep quality.",
        "form_note": "Magnesium glycinate preferred; avoid oxide (poor absorption).",
        "safety": "Generally safe. High doses may cause GI distress.",
    },
    {
        "id": "zinc",
        "name": "Zinc",
        "evidence_level": "moderate",
        "priority_rank": 9,
        "primary_benefit": "Testosterone production, immune function",
        "mechanism": (
            "Involved in testosterone synthesis, immune function, "
            "protein synthesis, and enzyme function."
        ),
        "benefits": [
            "Supports testosterone production (especially when depleted by sweating)",
            "Immune system support",
            "Recovery support",
        ],
        "dosing_options": [
            {
                "protocol": "Daily supplementation",
                "dose_mg_per_day": 35,   # midpoint of 25–45 mg elemental
                "duration": "Ongoing",
                "notes": "Often combined with magnesium as ZMA. ZMA studies are mixed.",
            },
        ],
        "timing": "With or without food; avoid taking with calcium (competes for absorption).",
        "form_note": "Zinc picolinate or citrate are well-absorbed.",
        "safety": (
            "Caution: >40 mg/day chronic can interfere with copper absorption. "
            "Direct deficiency correction has clearer benefit than ZMA complex."
        ),
    },
]
