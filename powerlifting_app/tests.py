"""
tests.py — Unit tests for the powerlifting tracker.

Run with: python -m pytest tests.py -v
Or:        python tests.py
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Calculator tests (pure functions — no I/O)
# ---------------------------------------------------------------------------

class TestOneRMCalculators(unittest.TestCase):

    def test_epley_1rm_single_rep(self):
        """1 rep should return the weight unchanged."""
        import calculators
        self.assertAlmostEqual(calculators.epley_1rm(100.0, 1), 100.0)

    def test_epley_1rm_five_reps(self):
        """100 kg × 5 reps → 100 × (1 + 5/30) = 116.67 kg"""
        import calculators
        self.assertAlmostEqual(calculators.epley_1rm(100.0, 5), 116.667, places=1)

    def test_brzycki_1rm_single_rep(self):
        import calculators
        self.assertAlmostEqual(calculators.brzycki_1rm(100.0, 1), 100.0)

    def test_brzycki_1rm_five_reps(self):
        """100 × 36 / (37 - 5) = 3600/32 = 112.5 kg"""
        import calculators
        self.assertAlmostEqual(calculators.brzycki_1rm(100.0, 5), 112.5)

    def test_epley_invalid_reps(self):
        import calculators
        with self.assertRaises(ValueError):
            calculators.epley_1rm(100.0, 0)

    def test_brzycki_invalid_reps(self):
        import calculators
        with self.assertRaises(ValueError):
            calculators.brzycki_1rm(100.0, 37)

    def test_percentage_of_1rm_rounds_to_2_5(self):
        """135.3 kg should round to 135.0 (nearest 2.5)."""
        import calculators
        result = calculators.percentage_of_1rm(160.0, 85)  # 136.0 → 135.0
        self.assertEqual(result % 2.5, 0.0)

    def test_training_max_from_1rm_default(self):
        """Default 90% TM of 200 kg → 180 kg."""
        import calculators
        # 200 * 0.9 = 180, rounds to nearest 2.5 = 180.0
        self.assertAlmostEqual(calculators.training_max_from_1rm(200.0), 180.0)


class Test531Builder(unittest.TestCase):

    def test_week1_structure(self):
        """Week 1 should have 3 sets at 65/75/85% with last set AMRAP."""
        import calculators
        sets = calculators.build_531_week("squat", 180.0, week=1)
        self.assertEqual(len(sets), 3)
        self.assertFalse(sets[0]["is_amrap"])
        self.assertFalse(sets[1]["is_amrap"])
        self.assertTrue(sets[2]["is_amrap"])
        self.assertEqual(sets[0]["percentage"], 65)
        self.assertEqual(sets[1]["percentage"], 75)
        self.assertEqual(sets[2]["percentage"], 85)

    def test_week4_no_amrap(self):
        """Deload week (4) should have no AMRAP sets."""
        import calculators
        sets = calculators.build_531_week("bench", 100.0, week=4)
        for s in sets:
            self.assertFalse(s["is_amrap"])

    def test_invalid_week(self):
        import calculators
        with self.assertRaises(ValueError):
            calculators.build_531_week("squat", 180.0, week=5)

    def test_target_weights_rounded(self):
        """All target weights should be multiples of 2.5."""
        import calculators
        for week in [1, 2, 3, 4]:
            sets = calculators.build_531_week("deadlift", 220.0, week=week)
            for s in sets:
                self.assertEqual(s["target_weight_kg"] % 2.5, 0.0,
                                 f"Week {week}: {s['target_weight_kg']} not a multiple of 2.5")

    def test_531_tm_advance_upper(self):
        import calculators
        new_tm = calculators.advance_531_training_max(100.0, "upper")
        self.assertAlmostEqual(new_tm, 102.5)

    def test_531_tm_advance_lower(self):
        import calculators
        new_tm = calculators.advance_531_training_max(180.0, "lower")
        self.assertAlmostEqual(new_tm, 185.0)


class TestNutritionCalculators(unittest.TestCase):

    def test_bmr_male(self):
        """Known value: 80 kg, 180 cm, 30 y, male"""
        import calculators
        bmr = calculators.mifflin_st_jeor_bmr(80.0, 180.0, 30, "male")
        # 10*80 + 6.25*180 - 5*30 + 5 = 800 + 1125 - 150 + 5 = 1780
        self.assertAlmostEqual(bmr, 1780.0)

    def test_bmr_female(self):
        """Known value: 60 kg, 165 cm, 25 y, female"""
        import calculators
        bmr = calculators.mifflin_st_jeor_bmr(60.0, 165.0, 25, "female")
        # 10*60 + 6.25*165 - 5*25 - 161 = 600 + 1031.25 - 125 - 161 = 1345.25
        self.assertAlmostEqual(bmr, 1345.25)

    def test_tdee_multiplier(self):
        """TDEE should be BMR × activity multiplier."""
        import calculators
        from data import ACTIVITY_MULTIPLIERS
        bmr = calculators.mifflin_st_jeor_bmr(80.0, 180.0, 30, "male")
        expected = bmr * ACTIVITY_MULTIPLIERS["moderately_active"]
        actual = calculators.calculate_tdee(80.0, 180.0, 30, "male", "moderately_active")
        self.assertAlmostEqual(actual, expected, places=1)

    def test_tdee_invalid_activity(self):
        import calculators
        with self.assertRaises(ValueError):
            calculators.calculate_tdee(80.0, 180.0, 30, "male", "ultra_active")

    def test_calculate_macros_maintenance(self):
        """Maintenance phase macros should sum near target calories."""
        import calculators
        result = calculators.calculate_macros(2500.0, 80.0, "maintenance")
        # Verify keys present
        for key in ("target_calories", "protein_g", "carbs_g", "fat_g"):
            self.assertIn(key, result)
        # Actual calories should be within 200 kcal of target
        self.assertAlmostEqual(result["actual_calories"], result["target_calories"], delta=200)

    def test_calculate_macros_invalid_phase(self):
        import calculators
        with self.assertRaises(ValueError):
            calculators.calculate_macros(2500.0, 80.0, "space_diet")

    def test_creatine_loading_dose(self):
        """80 kg × 0.3 = 24.0 g"""
        import calculators
        self.assertAlmostEqual(calculators.creatine_loading_dose(80.0), 24.0)

    def test_caffeine_dose_cap(self):
        """Very heavy athlete should be capped at 400 mg."""
        import calculators
        # 120 kg × 6 mg/kg = 720 mg → capped at 400
        self.assertAlmostEqual(calculators.caffeine_dose(120.0, 6.0), 400.0)

    def test_caffeine_dose_normal(self):
        """80 kg × 4.5 mg/kg = 360 mg"""
        import calculators
        self.assertAlmostEqual(calculators.caffeine_dose(80.0, 4.5), 360.0)

    def test_caffeine_dose_invalid_range(self):
        import calculators
        with self.assertRaises(ValueError):
            calculators.caffeine_dose(80.0, 7.0)


class TestWilks(unittest.TestCase):

    def test_wilks_male_reasonable_range(self):
        """A reasonable intermediate male should score 300–500."""
        import calculators
        # 90 kg male: squat 180, bench 120, DL 220 = 520 total
        wilks = calculators.calculate_wilks(90.0, 520.0, "male")
        self.assertGreater(wilks, 250)
        self.assertLess(wilks, 550)

    def test_wilks_female_reasonable_range(self):
        import calculators
        # 65 kg female: squat 120, bench 70, DL 150 = 340 total
        wilks = calculators.calculate_wilks(65.0, 340.0, "female")
        self.assertGreater(wilks, 250)
        self.assertLess(wilks, 500)

    def test_strength_level_labels(self):
        import calculators
        self.assertEqual(calculators.strength_level_label(150), "Beginner")
        self.assertEqual(calculators.strength_level_label(250), "Novice")
        self.assertEqual(calculators.strength_level_label(350), "Intermediate")
        self.assertEqual(calculators.strength_level_label(450), "Advanced")
        self.assertEqual(calculators.strength_level_label(550), "Elite")
        self.assertEqual(calculators.strength_level_label(650), "World-class")


class TestSupplementStack(unittest.TestCase):

    def test_priority_1_returns_only_creatine(self):
        import calculators
        stack = calculators.get_supplement_stack(1)
        self.assertEqual(len(stack), 1)
        self.assertEqual(stack[0]["id"], "creatine_monohydrate")

    def test_priority_3_returns_tier1(self):
        import calculators
        stack = calculators.get_supplement_stack(3)
        ids = [s["id"] for s in stack]
        self.assertIn("creatine_monohydrate", ids)
        self.assertIn("caffeine", ids)
        self.assertIn("whey_protein", ids)

    def test_stack_sorted_by_priority(self):
        import calculators
        stack = calculators.get_supplement_stack(9)
        ranks = [s["priority_rank"] for s in stack]
        self.assertEqual(ranks, sorted(ranks))


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestSetModel(unittest.TestCase):

    def test_volume_calculation(self):
        from models import Set
        s = Set(weight_kg=100.0, reps=5)
        self.assertAlmostEqual(s.volume, 500.0)

    def test_set_serialization_roundtrip(self):
        from models import Set
        s = Set(weight_kg=142.5, reps=3, rpe=8.5, is_amrap=True, actual_reps=5, notes="felt good")
        s2 = Set.from_dict(s.to_dict())
        self.assertAlmostEqual(s.weight_kg, s2.weight_kg)
        self.assertEqual(s.reps, s2.reps)
        self.assertEqual(s.is_amrap, s2.is_amrap)
        self.assertEqual(s.actual_reps, s2.actual_reps)


class TestExerciseModel(unittest.TestCase):

    def test_total_volume(self):
        from models import Set, Exercise
        ex = Exercise(
            name="Squat",
            sets=[Set(100.0, 5), Set(110.0, 3), Set(120.0, 1)],
        )
        expected = 100 * 5 + 110 * 3 + 120 * 1  # 500 + 330 + 120 = 950
        self.assertAlmostEqual(ex.total_volume_kg, 950.0)

    def test_heaviest_set(self):
        from models import Set, Exercise
        ex = Exercise(
            name="Deadlift",
            sets=[Set(200.0, 5), Set(220.0, 3), Set(240.0, 1)],
        )
        self.assertAlmostEqual(ex.heaviest_set_kg, 240.0)

    def test_exercise_serialization_roundtrip(self):
        from models import Set, Exercise
        ex = Exercise(name="Bench Press", sets=[Set(80.0, 5), Set(90.0, 3)], tier="T1")
        ex2 = Exercise.from_dict(ex.to_dict())
        self.assertEqual(ex.name, ex2.name)
        self.assertEqual(ex.tier, ex2.tier)
        self.assertEqual(len(ex.sets), len(ex2.sets))


class TestWorkoutSessionModel(unittest.TestCase):

    def test_total_volume(self):
        from models import Set, Exercise, WorkoutSession
        session = WorkoutSession(
            exercises=[
                Exercise("Squat", [Set(140.0, 5), Set(140.0, 5), Set(140.0, 5)]),
                Exercise("Bench", [Set(90.0, 5), Set(90.0, 5), Set(90.0, 5)]),
            ]
        )
        expected = (140 * 5 * 3) + (90 * 5 * 3)  # 2100 + 1350 = 3450
        self.assertAlmostEqual(session.total_volume_kg, 3450.0)

    def test_get_exercise_case_insensitive(self):
        from models import Set, Exercise, WorkoutSession
        session = WorkoutSession(
            exercises=[Exercise("Squat", [Set(140.0, 5)])],
        )
        self.assertIsNotNone(session.get_exercise("squat"))
        self.assertIsNotNone(session.get_exercise("SQUAT"))
        self.assertIsNone(session.get_exercise("Bench"))

    def test_session_serialization_roundtrip(self):
        from models import Set, Exercise, WorkoutSession
        session = WorkoutSession(
            date="2026-04-10",
            program_id="531",
            week_number=2,
            day_label="Squat Day",
            exercises=[Exercise("Squat", [Set(160.0, 3)])],
        )
        session2 = WorkoutSession.from_dict(session.to_dict())
        self.assertEqual(session.date, session2.date)
        self.assertEqual(session.program_id, session2.program_id)
        self.assertEqual(len(session.exercises), len(session2.exercises))


class TestPersonalRecord(unittest.TestCase):

    def test_e1rm_for_true_1rm(self):
        from models import PersonalRecord
        pr = PersonalRecord("Squat", weight_kg=200.0, reps=1)
        self.assertAlmostEqual(pr.estimated_1rm_kg, 200.0)

    def test_e1rm_for_multi_rep(self):
        from models import PersonalRecord
        pr = PersonalRecord("Squat", weight_kg=180.0, reps=3)
        # Epley: 180 × (1 + 3/30) = 180 × 1.1 = 198.0
        self.assertAlmostEqual(pr.estimated_1rm_kg, 198.0)


class TestAthleteProfile(unittest.TestCase):

    def test_bmr_male(self):
        from models import AthleteProfile
        athlete = AthleteProfile(
            name="Test", bodyweight_kg=80.0, height_cm=180.0, age=30,
            sex="male", activity_level="moderately_active"
        )
        # Matches mifflin formula: 10*80 + 6.25*180 - 5*30 + 5 = 1780
        self.assertAlmostEqual(athlete.bmr, 1780.0)

    def test_serialization_roundtrip(self):
        from models import AthleteProfile
        athlete = AthleteProfile(
            name="Alice", bodyweight_kg=65.0, height_cm=165.0, age=25,
            sex="female", activity_level="very_active",
            training_max={"squat": 120.0, "bench": 75.0},
        )
        athlete2 = AthleteProfile.from_dict(athlete.to_dict())
        self.assertEqual(athlete.name, athlete2.name)
        self.assertAlmostEqual(athlete.bodyweight_kg, athlete2.bodyweight_kg)
        self.assertEqual(athlete.training_max, athlete2.training_max)


# ---------------------------------------------------------------------------
# Database / Persistence tests
# ---------------------------------------------------------------------------

class TestWorkoutDatabase(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_athlete_save_and_load(self):
        from models import AthleteProfile, WorkoutDatabase
        db = WorkoutDatabase(self.tmpdir)
        athlete = AthleteProfile(
            name="Bob", bodyweight_kg=90.0, height_cm=178.0, age=35,
            sex="male", activity_level="very_active"
        )
        db.save_athlete(athlete)
        loaded = db.load_athlete()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "Bob")
        self.assertAlmostEqual(loaded.bodyweight_kg, 90.0)

    def test_athlete_not_found_returns_none(self):
        from models import WorkoutDatabase
        db = WorkoutDatabase(self.tmpdir)
        self.assertIsNone(db.load_athlete())

    def test_session_save_load_delete(self):
        from models import Set, Exercise, WorkoutSession, WorkoutDatabase
        db = WorkoutDatabase(self.tmpdir)
        session = WorkoutSession(
            date="2026-04-10",
            exercises=[Exercise("Squat", [Set(160.0, 5)])],
        )
        db.save_session(session)
        loaded = db.load_session(session.session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.exercises[0].name, "Squat")

        deleted = db.delete_session(session.session_id)
        self.assertTrue(deleted)
        self.assertIsNone(db.load_session(session.session_id))

    def test_load_all_sessions_sorted_by_date(self):
        from models import WorkoutSession, WorkoutDatabase
        db = WorkoutDatabase(self.tmpdir)
        db.save_session(WorkoutSession(date="2026-04-03"))
        db.save_session(WorkoutSession(date="2026-04-10"))
        db.save_session(WorkoutSession(date="2026-04-07"))
        sessions = db.load_all_sessions()
        dates = [s.date for s in sessions]
        self.assertEqual(dates, sorted(dates))

    def test_personal_records_roundtrip(self):
        from models import PersonalRecord, WorkoutDatabase
        db = WorkoutDatabase(self.tmpdir)
        prs = [
            PersonalRecord("Squat", 200.0, 1),
            PersonalRecord("Bench", 140.0, 1),
        ]
        db.save_personal_records(prs)
        loaded = db.load_personal_records()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].lift_name, "Squat")

    def test_program_progress_roundtrip(self):
        from models import ProgramProgress, WorkoutDatabase
        db = WorkoutDatabase(self.tmpdir)
        prog = ProgramProgress(
            program_id="531",
            current_week=2,
            current_cycle=1,
            training_maxes={"squat": 180.0},
        )
        db.save_program_progress(prog)
        loaded = db.load_program_progress("531")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.current_week, 2)
        self.assertAlmostEqual(loaded.training_maxes["squat"], 180.0)


# ---------------------------------------------------------------------------
# Tracker integration tests
# ---------------------------------------------------------------------------

class TestPowerliftingTracker(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        from tracker import PowerliftingTracker
        self.tracker = PowerliftingTracker(db_path=self.tmpdir)
        self.tracker.setup_athlete(
            "Test Athlete", 85.0, 178.0, 28, "male", "moderately_active", "531"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_athlete_profile_created(self):
        a = self.tracker.athlete
        self.assertEqual(a.name, "Test Athlete")
        self.assertAlmostEqual(a.bodyweight_kg, 85.0)

    def test_set_training_max(self):
        self.tracker.set_training_max("squat", 180.0)
        self.assertAlmostEqual(self.tracker.athlete.training_max["squat"], 180.0)

    def test_set_one_rep_max_computes_tm(self):
        self.tracker.set_one_rep_max("bench", 140.0)
        # 90% of 140 = 126 → rounds to 125.0 (nearest 2.5)
        expected_tm = round(140.0 * 0.9 / 2.5) * 2.5
        self.assertAlmostEqual(
            self.tracker.athlete.training_max["bench"], expected_tm
        )

    def test_calculate_nutrition_returns_expected_keys(self):
        result = self.tracker.calculate_nutrition("cut")
        for key in ("bmr", "tdee", "target_calories", "protein_g", "carbs_g", "fat_g"):
            self.assertIn(key, result)

    def test_calculate_wilks(self):
        result = self.tracker.calculate_wilks(180.0, 120.0, 220.0)
        self.assertIn("wilks_score", result)
        self.assertIn("strength_level", result)
        self.assertGreater(result["wilks_score"], 0)

    def test_estimate_1rm(self):
        result = self.tracker.estimate_1rm(160.0, 5)
        self.assertIn("epley_e1rm_kg", result)
        self.assertIn("average_e1rm_kg", result)
        self.assertGreater(result["average_e1rm_kg"], 160.0)

    def test_session_workflow(self):
        """Full session logging workflow."""
        from models import Set, Exercise
        session = self.tracker.start_session(
            program_id="531", week_number=1, day_label="Squat Day"
        )
        self.tracker.add_exercise_to_session(
            session, "Squat",
            [
                {"weight_kg": 120.0, "reps": 5, "rpe": None, "is_amrap": False, "actual_reps": None, "notes": ""},
                {"weight_kg": 135.0, "reps": 5, "rpe": None, "is_amrap": False, "actual_reps": None, "notes": ""},
                {"weight_kg": 152.5, "reps": 7, "rpe": 9.0, "is_amrap": True, "actual_reps": 7, "notes": "PR attempt"},
            ]
        )
        self.tracker.save_session(session)

        # Verify it was persisted
        loaded = self.tracker.get_session(session.session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.exercises[0].name, "Squat")
        self.assertEqual(len(loaded.exercises[0].sets), 3)

        # Verify PR was auto-detected
        pr = self.tracker.get_best_pr("Squat")
        self.assertIsNotNone(pr)

    def test_get_531_workout_requires_tm(self):
        """Should raise if no training max is set."""
        with self.assertRaises(ValueError):
            self.tracker.get_531_workout("squat", week=1)

    def test_get_531_workout_with_tm(self):
        self.tracker.set_training_max("squat", 180.0)
        sets = self.tracker.get_531_workout("squat", week=1)
        self.assertEqual(len(sets), 3)
        self.assertTrue(sets[2]["is_amrap"])

    def test_advance_531_cycle(self):
        self.tracker.set_training_max("squat", 180.0)
        new_tm = self.tracker.advance_531_cycle("squat")
        self.assertAlmostEqual(new_tm, 185.0)

    def test_supplement_guide_returns_list(self):
        guide = self.tracker.get_supplement_guide(5)
        self.assertIsInstance(guide, list)
        self.assertLessEqual(len(guide), 5)

    def test_supplement_doses_personalised(self):
        doses = self.tracker.calculate_supplement_doses()
        self.assertIn("creatine_monohydrate", doses)
        self.assertIn("caffeine", doses)
        # 85 kg × 0.3 = 25.5 g loading
        self.assertAlmostEqual(doses["creatine_monohydrate"]["loading_dose_g_per_day"], 25.5, places=1)

    def test_summary_report_not_empty(self):
        report = self.tracker.generate_summary_report()
        self.assertIsInstance(report, str)
        # Summary prints name in uppercase
        self.assertIn("TEST ATHLETE", report)


# ---------------------------------------------------------------------------
# Data Integrity Tests
# ---------------------------------------------------------------------------

class TestDataIntegrity(unittest.TestCase):

    def test_all_programs_have_required_fields(self):
        from data import PROGRAMS
        required = {"id", "name", "level", "frequency_days_per_week",
                    "progression_type", "primary_lifts", "description", "best_for"}
        for prog in PROGRAMS:
            for field in required:
                self.assertIn(field, prog, f"Program '{prog.get('id')}' missing field '{field}'")

    def test_all_supplements_have_required_fields(self):
        from data import SUPPLEMENTS
        required = {"id", "name", "evidence_level", "priority_rank", "primary_benefit"}
        for supp in SUPPLEMENTS:
            for field in required:
                self.assertIn(field, supp, f"Supplement '{supp.get('id')}' missing field '{field}'")

    def test_supplement_evidence_levels_valid(self):
        from data import SUPPLEMENTS
        valid = {"strong", "moderate", "weak"}
        for supp in SUPPLEMENTS:
            self.assertIn(supp["evidence_level"], valid,
                          f"Supplement '{supp['id']}' has invalid evidence_level '{supp['evidence_level']}'")

    def test_supplement_priority_ranks_unique(self):
        from data import SUPPLEMENTS
        ranks = [s["priority_rank"] for s in SUPPLEMENTS]
        self.assertEqual(len(ranks), len(set(ranks)), "Priority ranks must be unique")

    def test_nutrition_phases_have_required_fields(self):
        from data import NUTRITION_PHASES
        required = {"phase", "protein_g_per_kg", "carbs_g_per_kg", "fat_pct_of_calories"}
        for phase in NUTRITION_PHASES:
            for field in required:
                self.assertIn(field, phase, f"Phase '{phase.get('phase')}' missing field '{field}'")

    def test_activity_multipliers_range(self):
        from data import ACTIVITY_MULTIPLIERS
        for key, mult in ACTIVITY_MULTIPLIERS.items():
            self.assertGreaterEqual(mult, 1.0, f"Multiplier for {key} < 1.0")
            self.assertLessEqual(mult, 2.5, f"Multiplier for {key} > 2.5")

    def test_531_program_has_wave_structure(self):
        from data import PROGRAMS
        prog_531 = next((p for p in PROGRAMS if p["id"] == "531"), None)
        self.assertIsNotNone(prog_531)
        self.assertIn("wave_structure", prog_531)
        self.assertEqual(len(prog_531["wave_structure"]), 4)


if __name__ == "__main__":
    # Allow running from any directory by adding app directory to path
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    unittest.main(verbosity=2)
