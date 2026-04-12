"""
tracker.py — High-level API for the powerlifting tracker application.

Combines models, calculators, and data into a single coherent interface.
All user-facing operations go through the PowerliftingTracker class.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import calculators
from data import PROGRAMS, NUTRITION_PHASES, SUPPLEMENTS, FOOD_SOURCES, MEAL_TIMING
from models import (
    AthleteProfile,
    Exercise,
    PersonalRecord,
    ProgramProgress,
    Set,
    WorkoutDatabase,
    WorkoutSession,
)


class PowerliftingTracker:
    """
    Central coordinator for all tracker functionality.

    Usage:
        tracker = PowerliftingTracker(db_path="./my_data")
        tracker.setup_athlete("Alice", 72.0, 168.0, 28, "female", "moderately_active")
        session = tracker.start_session("531", week_number=1, day_label="Squat Day")
        session.exercises.append(...)
        tracker.save_session(session)
    """

    def __init__(self, db_path: str = "./workout_data") -> None:
        self.db = WorkoutDatabase(db_path)
        self._athlete: Optional[AthleteProfile] = self.db.load_athlete()
        self._personal_records: list[PersonalRecord] = self.db.load_personal_records()

    # -----------------------------------------------------------------------
    # Athlete Setup
    # -----------------------------------------------------------------------

    def setup_athlete(
        self,
        name: str,
        bodyweight_kg: float,
        height_cm: float,
        age: int,
        sex: str,
        activity_level: str,
        current_program_id: Optional[str] = None,
    ) -> AthleteProfile:
        """
        Create or overwrite the athlete profile.

        Args:
            name:               Athlete's name.
            bodyweight_kg:      Body weight in kg.
            height_cm:          Height in cm.
            age:                Age in years.
            sex:                "male" or "female".
            activity_level:     One of: sedentary, lightly_active, moderately_active,
                                very_active, extremely_active.
            current_program_id: Optional program ID to track.

        Returns:
            The created AthleteProfile.
        """
        self._athlete = AthleteProfile(
            name=name,
            bodyweight_kg=bodyweight_kg,
            height_cm=height_cm,
            age=age,
            sex=sex,
            activity_level=activity_level,
            current_program_id=current_program_id,
        )
        self.db.save_athlete(self._athlete)
        return self._athlete

    @property
    def athlete(self) -> AthleteProfile:
        if self._athlete is None:
            raise RuntimeError(
                "No athlete profile found. Call setup_athlete() first."
            )
        return self._athlete

    def update_bodyweight(self, bodyweight_kg: float) -> None:
        """Update athlete's current body weight and save."""
        self.athlete.bodyweight_kg = bodyweight_kg
        self.db.save_athlete(self.athlete)

    def set_training_max(self, lift: str, training_max_kg: float) -> None:
        """Set or update the training max for a specific lift."""
        self.athlete.training_max[lift.lower()] = training_max_kg
        self.db.save_athlete(self.athlete)

    def set_one_rep_max(self, lift: str, one_rm_kg: float) -> None:
        """Record a 1RM and auto-compute a 90% training max."""
        lift_lower = lift.lower()
        self.athlete.one_rep_maxes[lift_lower] = one_rm_kg
        self.athlete.training_max[lift_lower] = calculators.training_max_from_1rm(one_rm_kg)
        self.db.save_athlete(self.athlete)

    # -----------------------------------------------------------------------
    # Session Management
    # -----------------------------------------------------------------------

    def start_session(
        self,
        program_id: Optional[str] = None,
        week_number: Optional[int] = None,
        day_label: str = "",
        session_date: Optional[str] = None,
    ) -> WorkoutSession:
        """
        Create a new blank WorkoutSession (not yet saved).
        Call save_session() to persist it.
        """
        return WorkoutSession(
            date=session_date or date.today().isoformat(),
            program_id=program_id or self.athlete.current_program_id,
            week_number=week_number,
            day_label=day_label,
            bodyweight_kg=self.athlete.bodyweight_kg,
        )

    def save_session(self, session: WorkoutSession) -> list[PersonalRecord]:
        """Persist a session to disk, check for PR updates, and return new PRs."""
        self.db.save_session(session)
        return self._check_and_update_prs(session)

    def get_session(self, session_id: str) -> Optional[WorkoutSession]:
        return self.db.load_session(session_id)

    def get_all_sessions(self) -> list[WorkoutSession]:
        return self.db.load_all_sessions()

    def delete_session(self, session_id: str) -> bool:
        return self.db.delete_session(session_id)

    def add_exercise_to_session(
        self,
        session: WorkoutSession,
        exercise_name: str,
        sets_data: list[dict],
        tier: Optional[str] = None,
        notes: str = "",
    ) -> Exercise:
        """
        Add an exercise with multiple sets to a session.

        Args:
            session:       The session to add to.
            exercise_name: Name of the lift.
            sets_data:     List of dicts, each with keys: weight_kg, reps,
                           and optionally: rpe, is_amrap, actual_reps, notes.
            tier:          Optional GZCL tier ("T1", "T2", "T3").
            notes:         Exercise-level notes.

        Returns:
            The created Exercise object.
        """
        sets = [Set(**s) for s in sets_data]
        exercise = Exercise(name=exercise_name, sets=sets, tier=tier, notes=notes)
        session.exercises.append(exercise)
        return exercise

    # -----------------------------------------------------------------------
    # Personal Records
    # -----------------------------------------------------------------------

    @property
    def personal_records(self) -> list[PersonalRecord]:
        return self._personal_records

    def log_personal_record(
        self,
        lift_name: str,
        weight_kg: float,
        reps: int = 1,
        session_id: Optional[str] = None,
        notes: str = "",
    ) -> PersonalRecord:
        """Manually log a personal record."""
        pr = PersonalRecord(
            lift_name=lift_name,
            weight_kg=weight_kg,
            reps=reps,
            session_id=session_id,
            notes=notes,
        )
        self._personal_records.append(pr)
        self.db.save_personal_records(self._personal_records)
        return pr

    def get_best_pr(self, lift_name: str) -> Optional[PersonalRecord]:
        """Return the highest estimated 1RM PR for a given lift."""
        matching = [
            pr for pr in self._personal_records
            if pr.lift_name.lower() == lift_name.lower()
        ]
        if not matching:
            return None
        return max(matching, key=lambda pr: pr.estimated_1rm_kg)

    def _check_and_update_prs(self, session: WorkoutSession) -> list[PersonalRecord]:
        """
        After saving a session, check each exercise for a new PR
        based on estimated 1RM. Auto-logs if a new PR is found.

        Returns:
            List of newly detected PersonalRecord objects.
        """
        new_prs = []
        for exercise in session.exercises:
            for s in exercise.sets:
                reps = s.actual_reps if (s.is_amrap and s.actual_reps is not None) else s.reps
                try:
                    e1rm = calculators.epley_1rm(s.weight_kg, reps)
                except ValueError:
                    continue
                current_best = self.get_best_pr(exercise.name)
                if current_best is None or e1rm > current_best.estimated_1rm_kg:
                    pr = self.log_personal_record(
                        lift_name=exercise.name,
                        weight_kg=s.weight_kg,
                        reps=reps,
                        session_id=session.session_id,
                        notes="Auto-detected PR",
                    )
                    new_prs.append(pr)
        # Save all PRs once at the end instead of per-PR
        if new_prs:
            self.db.save_personal_records(self._personal_records)
        return new_prs

    # -----------------------------------------------------------------------
    # 5/3/1 Program Helpers
    # -----------------------------------------------------------------------

    def get_531_workout(
        self, lift: str, week: int, training_max_override: Optional[float] = None
    ) -> list[dict]:
        """
        Return the prescribed 5/3/1 sets for a given lift and week.

        Args:
            lift:                    Lift name (squat, bench, deadlift, ohp).
            week:                    Week number 1–4.
            training_max_override:   Use this TM instead of the stored one.

        Returns:
            List of set dicts from calculators.build_531_week().
        """
        tm = training_max_override or self.athlete.training_max.get(lift.lower())
        if tm is None:
            raise ValueError(
                f"No training max found for '{lift}'. "
                "Set it with set_training_max() or set_one_rep_max()."
            )
        return calculators.build_531_week(lift, tm, week)

    def advance_531_cycle(self, lift: str) -> float:
        """
        Increment the training max for a lift after completing a 5/3/1 cycle.

        Returns:
            New training max.
        """
        lift_lower = lift.lower()
        current_tm = self.athlete.training_max.get(lift_lower)
        if current_tm is None:
            raise ValueError(f"No training max found for '{lift}'")

        lift_type = "upper" if lift_lower in {"bench", "bench press", "ohp", "overhead press"} else "lower"
        new_tm = calculators.advance_531_training_max(current_tm, lift_type)
        self.athlete.training_max[lift_lower] = new_tm
        self.db.save_athlete(self.athlete)
        return new_tm

    # -----------------------------------------------------------------------
    # Nutrition
    # -----------------------------------------------------------------------

    def calculate_nutrition(self, phase: str = "maintenance") -> dict:
        """
        Calculate full nutrition targets for the current athlete.

        Args:
            phase: One of lean_bulk, aggressive_bulk, cut, maintenance, meet_peak.

        Returns:
            Dict with TDEE, target_calories, protein_g, carbs_g, fat_g,
            macros as percentages, and notes.
        """
        a = self.athlete
        tdee = calculators.calculate_tdee(
            a.bodyweight_kg, a.height_cm, a.age, a.sex, a.activity_level
        )
        macros = calculators.calculate_macros(tdee, a.bodyweight_kg, phase)
        macros["tdee"] = round(tdee)
        macros["bmr"] = round(calculators.mifflin_st_jeor_bmr(
            a.bodyweight_kg, a.height_cm, a.age, a.sex
        ))
        return macros

    def get_pre_workout_meal(self, hours_before: float = 2.5) -> dict:
        """Suggest a pre-workout meal for the current athlete."""
        a = self.athlete
        tdee = calculators.calculate_tdee(
            a.bodyweight_kg, a.height_cm, a.age, a.sex, a.activity_level
        )
        return calculators.calculate_pre_workout_meal(tdee, hours_before)

    def get_food_sources(self) -> dict:
        """Return the evidence-based food source recommendations."""
        return FOOD_SOURCES

    def get_meal_timing_guide(self) -> dict:
        """Return the meal timing recommendations."""
        return MEAL_TIMING

    # -----------------------------------------------------------------------
    # Supplement Guide
    # -----------------------------------------------------------------------

    def get_supplement_guide(self, priority_level: int = 9) -> list[dict]:
        """
        Return supplement recommendations up to the given priority tier.

        Args:
            priority_level: 1–9 (1 = creatine only; 9 = full stack).
        """
        return calculators.get_supplement_stack(priority_level)

    def calculate_supplement_doses(self) -> dict:
        """
        Calculate personalized supplement doses for the current athlete.

        Returns:
            Dict of supplement_id → dose with notes.
        """
        bw = self.athlete.bodyweight_kg
        loading_dose = calculators.creatine_loading_dose(bw)
        caffeine = calculators.caffeine_dose(bw)

        return {
            "creatine_monohydrate": {
                "loading_dose_g_per_day": round(loading_dose, 1),
                "maintenance_dose_g_per_day": 3.5,
                "loading_note": f"~{loading_dose:.1f} g/day for 5–7 days (0.3 g/kg), split into 4–5 doses.",
                "maintenance_note": "3–5 g/day ongoing. Timing not critical.",
            },
            "caffeine": {
                "dose_mg": round(caffeine),
                "note": f"{caffeine:.0f} mg (~{caffeine/bw:.1f} mg/kg). Take 30–60 min pre-training. Cap 400 mg.",
            },
        }

    # -----------------------------------------------------------------------
    # Strength Analytics
    # -----------------------------------------------------------------------

    def calculate_wilks(
        self,
        squat_kg: float,
        bench_kg: float,
        deadlift_kg: float,
    ) -> dict:
        """
        Compute Wilks score and strength level label.

        Args:
            squat_kg, bench_kg, deadlift_kg: Competition best lifts.

        Returns:
            Dict with total_kg, wilks_score, strength_level.
        """
        total = squat_kg + bench_kg + deadlift_kg
        wilks = calculators.calculate_wilks(self.athlete.bodyweight_kg, total, self.athlete.sex)
        return {
            "squat_kg": squat_kg,
            "bench_kg": bench_kg,
            "deadlift_kg": deadlift_kg,
            "total_kg": total,
            "bodyweight_kg": self.athlete.bodyweight_kg,
            "wilks_score": round(wilks, 1),
            "strength_level": calculators.strength_level_label(wilks),
        }

    def get_volume_progression(self, lift_name: str) -> list[dict]:
        """Return volume progression history for a specific lift."""
        sessions = self.get_all_sessions()
        return calculators.calculate_volume_progression(sessions, lift_name)

    def estimate_1rm(self, weight_kg: float, reps: int) -> dict:
        """
        Estimate 1RM using both Epley and Brzycki formulas.

        Returns:
            Dict with both estimates and an average.
        """
        epley = calculators.epley_1rm(weight_kg, reps)
        brzycki = None
        if reps < 37:
            try:
                brzycki = calculators.brzycki_1rm(weight_kg, reps)
            except ValueError:
                pass

        average = (epley + brzycki) / 2 if brzycki is not None else epley
        result = {
            "weight_kg": weight_kg,
            "reps": reps,
            "epley_e1rm_kg": round(epley, 1),
            "brzycki_e1rm_kg": round(brzycki, 1) if brzycki is not None else None,
            "average_e1rm_kg": round(average, 1),
            "training_max_90pct": round(calculators.training_max_from_1rm(average), 1),
        }
        if reps > 10:
            result["reliability"] = "low"
            result["reliability_note"] = (
                "Estimates from sets above 10 reps are less reliable. "
                "The Brzycki formula diverges significantly above 10 reps. "
                "Use a heavier set (1-10 reps) for a more accurate estimate."
            )
        else:
            result["reliability"] = "high"
        return result

    # -----------------------------------------------------------------------
    # Program Reference
    # -----------------------------------------------------------------------

    def list_programs(self, level_filter: Optional[str] = None) -> list[dict]:
        """
        Return all programs, optionally filtered by experience level.

        Args:
            level_filter: "beginner", "intermediate", "advanced", or "all".
        """
        if level_filter is None:
            return PROGRAMS
        return [p for p in PROGRAMS if p["level"] in {level_filter, "all"}]

    def get_program(self, program_id: str) -> Optional[dict]:
        """Return a program dict by ID."""
        return next((p for p in PROGRAMS if p["id"] == program_id), None)

    # -----------------------------------------------------------------------
    # Summary / Reporting
    # -----------------------------------------------------------------------

    def generate_summary_report(self) -> str:
        """
        Generate a plain-text summary of the athlete's current status.

        Returns:
            Multi-line string suitable for printing.
        """
        a = self.athlete
        lines = [
            "=" * 60,
            f"  POWERLIFTING TRACKER — {a.name.upper()}",
            "=" * 60,
            f"  Body weight : {a.bodyweight_kg:.1f} kg",
            f"  Height      : {a.height_cm:.0f} cm",
            f"  Age         : {a.age}",
            f"  Sex         : {a.sex.title()}",
            f"  Activity    : {a.activity_level.replace('_', ' ').title()}",
            "",
        ]

        # Training maxes
        if a.training_max:
            lines.append("  Training Maxes:")
            for lift, tm in sorted(a.training_max.items()):
                lines.append(f"    {lift.title():20s} {tm:.1f} kg")
            lines.append("")

        # Personal records
        pr_lifts = sorted({pr.lift_name for pr in self._personal_records})
        if pr_lifts:
            lines.append("  Personal Records (estimated 1RM):")
            for lift in pr_lifts:
                best = self.get_best_pr(lift)
                if best:
                    lines.append(
                        f"    {lift:20s} {best.estimated_1rm_kg:.1f} kg e1RM "
                        f"({best.weight_kg:.1f} kg × {best.reps})"
                    )
            lines.append("")

        # Nutrition
        try:
            nutrition = self.calculate_nutrition("maintenance")
            lines += [
                "  Nutrition (Maintenance):",
                f"    BMR          : {nutrition['bmr']} kcal/day",
                f"    TDEE         : {nutrition['tdee']} kcal/day",
                f"    Target cals  : {nutrition['target_calories']} kcal/day",
                f"    Protein      : {nutrition['protein_g']} g/day",
                f"    Carbohydrates: {nutrition['carbs_g']} g/day",
                f"    Fat          : {nutrition['fat_g']} g/day",
                "",
            ]
        except (ValueError, KeyError) as e:
            lines.append(f"    (Nutrition calculation error: {e})")

        # Recent sessions
        sessions = self.get_all_sessions()
        if sessions:
            recent = sessions[-5:]
            lines.append(f"  Recent Sessions (last {len(recent)}):")
            for s in recent:
                lines.append(
                    f"    {s.date}  {s.day_label or 'Session'}  "
                    f"Volume: {s.total_volume_kg:.0f} kg"
                )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
