"""
cli.py — Command-line interface for the powerlifting tracker.

Entry point: python cli.py [command] [options]

Commands:
    setup       — Set up or update athlete profile
    session     — Log a training session interactively
    nutrition   — Calculate and display nutrition targets
    supplements — Display supplement guide with evidence ratings
    programs    — List and explore powerlifting programs
    531         — Generate 5/3/1 workout for a specific week
    e1rm        — Estimate 1 rep max from a set
    wilks       — Calculate Wilks score
    summary     — Print athlete summary report
    history     — Show session history with volume
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from tracker import PowerliftingTracker
from data import ACTIVITY_MULTIPLIERS, PROGRAMS


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def _header(title: str) -> str:
    bar = "─" * 60
    return f"\n{bar}\n  {title}\n{bar}"


def _bold(text: str) -> str:
    """ANSI bold — degrades gracefully if terminal doesn't support it."""
    return f"\033[1m{text}\033[0m"


def _green(text: str) -> str:
    return f"\033[32m{text}\033[0m"


def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m"


def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m"


def _evidence_color(level: str) -> str:
    colors = {"strong": _green, "moderate": _yellow, "weak": _red}
    fn = colors.get(level.lower(), str)
    return fn(level.upper())


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

def cmd_setup(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Interactive athlete setup."""
    print(_header("ATHLETE SETUP"))

    name = input("Your name: ").strip()
    bw = float(input("Body weight (kg): "))
    height = float(input("Height (cm): "))
    age = int(input("Age: "))
    sex = input("Sex (male/female): ").strip().lower()
    if sex not in {"male", "female"}:
        print("Sex must be 'male' or 'female'. Defaulting to 'male'.")
        sex = "male"

    print("\nActivity Levels:")
    for key in ACTIVITY_MULTIPLIERS:
        print(f"  {key}")
    activity = input("Activity level: ").strip().lower()
    if activity not in ACTIVITY_MULTIPLIERS:
        print(f"Unknown level; defaulting to 'moderately_active'.")
        activity = "moderately_active"

    print("\nPrograms:")
    for p in PROGRAMS:
        print(f"  {p['id']:25s} ({p['level']}) — {p['name']}")
    program = input("Current program ID (or Enter to skip): ").strip() or None

    athlete = tracker.setup_athlete(name, bw, height, age, sex, activity, program)
    print(f"\nProfile saved for {athlete.name}.")

    # Optional: set training maxes
    if input("\nSet training maxes now? (y/n): ").strip().lower() == "y":
        for lift in ["squat", "bench", "deadlift", "ohp"]:
            val = input(f"  {lift.title()} 1RM or training max (kg, or Enter to skip): ").strip()
            if val:
                is_1rm = input(f"  Is {val} kg a true 1RM? (y/n): ").strip().lower() == "y"
                if is_1rm:
                    tracker.set_one_rep_max(lift, float(val))
                    print(f"  Training max set to {tracker.athlete.training_max[lift]:.1f} kg")
                else:
                    tracker.set_training_max(lift, float(val))


def cmd_session(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Interactive session logging."""
    print(_header("LOG TRAINING SESSION"))

    program_id = input(f"Program ID (or Enter for '{tracker.athlete.current_program_id}'): ").strip()
    program_id = program_id or tracker.athlete.current_program_id

    week = input("Week number (or Enter to skip): ").strip()
    week = int(week) if week else None

    day_label = input("Day label (e.g. 'Squat Day', 'Workout A'): ").strip()

    session = tracker.start_session(program_id=program_id, week_number=week, day_label=day_label)

    print(f"\nSession started: {session.date}")
    print("Add exercises (Enter empty name to finish).\n")

    while True:
        ex_name = input("Exercise name (or Enter to finish): ").strip()
        if not ex_name:
            break

        tier = input(f"  GZCL Tier (T1/T2/T3, or Enter to skip): ").strip().upper() or None

        sets_data = []
        print(f"  Enter sets for {ex_name} (Enter empty weight to finish):")
        set_num = 1
        while True:
            weight_str = input(f"    Set {set_num} — Weight (kg, or Enter to finish): ").strip()
            if not weight_str:
                break
            weight = float(weight_str)
            reps = int(input(f"    Set {set_num} — Reps: "))
            if reps <= 0:
                print("    Reps must be at least 1. Skipping this set.")
                continue
            rpe_str = input(f"    Set {set_num} — RPE (1–10, or Enter to skip): ").strip()
            rpe = float(rpe_str) if rpe_str else None
            is_amrap = input(f"    Was this an AMRAP set? (y/n): ").strip().lower() == "y"
            actual_reps = None
            if is_amrap:
                actual_str = input(f"    Actual reps achieved on AMRAP: ").strip()
                actual_reps = int(actual_str) if actual_str else None

            sets_data.append({
                "weight_kg": weight,
                "reps": reps,
                "rpe": rpe,
                "is_amrap": is_amrap,
                "actual_reps": actual_reps,
                "notes": "",
            })
            set_num += 1

        if sets_data:
            exercise = tracker.add_exercise_to_session(session, ex_name, sets_data, tier=tier)
            print(f"  -> {ex_name}: {len(sets_data)} sets, {exercise.total_volume_kg:.0f} kg total volume")

    duration_str = input("\nSession duration (minutes, or Enter to skip): ").strip()
    session.duration_minutes = int(duration_str) if duration_str else None

    rpe_str = input("Overall session RPE (1–10, or Enter to skip): ").strip()
    session.session_rpe = float(rpe_str) if rpe_str else None

    session.notes = input("Session notes (or Enter to skip): ").strip()

    new_prs = tracker.save_session(session)
    print(f"\nSession saved! ID: {session.session_id}")
    print(f"Total volume: {session.total_volume_kg:.0f} kg")

    if new_prs:
        print(f"\n{_bold(_green('NEW PERSONAL RECORDS!'))}")
        for pr in new_prs:
            print(f"  {_green('★')} {pr.lift_name}: {pr.weight_kg:.1f} kg × {pr.reps} = {pr.estimated_1rm_kg:.1f} kg e1RM")


def cmd_nutrition(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Display nutrition targets for all phases."""
    print(_header("NUTRITION CALCULATOR"))
    a = tracker.athlete
    print(f"Athlete: {a.name}  |  {a.bodyweight_kg:.1f} kg  |  Activity: {a.activity_level}")

    phase = getattr(args, "phase", None) or "maintenance"
    valid_phases = ["lean_bulk", "aggressive_bulk", "cut", "maintenance", "meet_peak"]
    if phase not in valid_phases:
        print(f"Invalid phase '{phase}'. Valid: {valid_phases}")
        sys.exit(1)

    n = tracker.calculate_nutrition(phase)
    print(f"\n{'─'*50}")
    print(f"  Phase          : {_bold(n['phase'])}")
    print(f"  BMR            : {n['bmr']} kcal/day")
    print(f"  TDEE           : {n['tdee']} kcal/day")
    print(f"  Target Calories: {_bold(str(n['target_calories']))} kcal/day")
    print(f"{'─'*50}")
    print(f"  Protein   : {n['protein_g']:>5} g  ({n['protein_pct']:>4.1f}%)")
    print(f"  Carbs     : {n['carbs_g']:>5} g  ({n['carbs_pct']:>4.1f}%)")
    print(f"  Fat       : {n['fat_g']:>5} g  ({n['fat_pct']:>4.1f}%)")
    print(f"{'─'*50}")
    print(f"  Notes: {n['notes']}")
    if n.get("overflow_warning"):
        print(f"\n  {_yellow('WARNING:')} {n['overflow_warning']}")

    if getattr(args, "all_phases", False):
        print(_header("ALL PHASES COMPARISON"))
        header = f"{'Phase':<22} {'Cals':>6} {'Prot':>6} {'Carbs':>6} {'Fat':>6}"
        print(header)
        print("─" * len(header))
        for p_key in valid_phases:
            p_data = tracker.calculate_nutrition(p_key)
            print(
                f"{p_data['phase']:<22} {p_data['target_calories']:>6} "
                f"{p_data['protein_g']:>6} {p_data['carbs_g']:>6} {p_data['fat_g']:>6}"
            )

    # Pre-workout meal suggestion
    print(_header("PRE-WORKOUT MEAL GUIDE"))
    pw = tracker.get_pre_workout_meal()
    print(f"  Protein  : {pw['protein_g']} g")
    print(f"  Carbs    : {pw['carbs_g']} g")
    print(f"  Fat      : {pw['fat_g']} g")
    print(f"  ~Calories: {pw['approx_kcal']} kcal")
    print(f"  Timing   : {pw['timing_note']}")

    # Meal timing
    print(_header("MEAL TIMING SUMMARY"))
    timing = tracker.get_meal_timing_guide()
    for key, value in timing.items():
        label = key.replace("_", " ").title()
        print(f"  {label:<35}: {value}")


def cmd_supplements(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Display supplement guide with evidence ratings."""
    print(_header("SUPPLEMENT GUIDE — EVIDENCE-BASED RECOMMENDATIONS"))

    priority = getattr(args, "priority", 9)
    supplements = tracker.get_supplement_guide(priority)
    doses = tracker.calculate_supplement_doses()

    print(f"Showing supplements at priority level 1–{priority}\n")

    for s in supplements:
        evidence_display = _evidence_color(s["evidence_level"])
        print(f"  #{s['priority_rank']} {_bold(s['name'])}  [{evidence_display}]")
        print(f"     Benefit  : {s['primary_benefit']}")

        # Personalized dose if available
        if s["id"] in doses:
            d = doses[s["id"]]
            if s["id"] == "creatine_monohydrate":
                print(f"     Your dose: Loading {d['loading_dose_g_per_day']} g/day, then {d['maintenance_dose_g_per_day']} g/day")
            elif s["id"] == "caffeine":
                print(f"     Your dose: {d['dose_mg']} mg — {d['note']}")
        else:
            # Show standard dose from supplement data
            if s.get("dosing_options"):
                opt = s["dosing_options"][0]
                dose_parts = []
                for key in ("dose_g_per_day", "dose_mg_per_kg", "dose_g_per_serving",
                            "dose_mg_per_day", "dose_iu_per_day"):
                    if key in opt and opt[key] is not None:
                        unit = key.replace("dose_", "").replace("_per_day", "/day").replace("_per_kg", "/kg").replace("_per_serving", "/serving")
                        dose_parts.append(f"{opt[key]} {unit}")
                if dose_parts:
                    print(f"     Dose     : {', '.join(dose_parts)}")

        print(f"     Timing   : {s.get('timing', 'N/A')}")
        print(f"     Safety   : {s.get('safety', 'N/A')}")
        print()


def cmd_programs(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """List programs and show details."""
    level = getattr(args, "level", None)
    program_id = getattr(args, "id", None)

    if program_id:
        prog = tracker.get_program(program_id)
        if prog is None:
            print(f"Program '{program_id}' not found.")
            sys.exit(1)
        print(_header(f"PROGRAM: {prog['name']}"))
        print(f"  Author      : {prog['author']}")
        print(f"  Level       : {prog['level'].title()}")
        print(f"  Frequency   : {prog['frequency_days_per_week']} days/week")
        print(f"  Progression : {prog['progression_type'].replace('_', ' ').title()}")
        print(f"  Lifts       : {', '.join(prog['primary_lifts'])}")
        print(f"  Sets/Reps   : {prog['sets_reps_scheme']}")
        print(f"  Best For    : {prog['best_for']}")
        print(f"\n  Description:")
        for line in prog["description"].split(". "):
            if line:
                print(f"    - {line.strip('.')}.")
        if prog.get("pros"):
            print(f"\n  Pros: {prog['pros']}")
        if prog.get("cons"):
            print(f"  Cons: {prog['cons']}")
    else:
        programs = tracker.list_programs(level)
        print(_header(f"POWERLIFTING PROGRAMS{' ('+level.title()+')' if level else ''}"))
        header = f"  {'ID':<22} {'Level':<14} {'Days/wk':<8} {'Progression':<22} {'Author'}"
        print(header)
        print("  " + "─" * (len(header) - 2))
        for p in programs:
            print(
                f"  {p['id']:<22} {p['level']:<14} "
                f"{p['frequency_days_per_week']:<8} "
                f"{p['progression_type'].replace('_',' ').title():<22} "
                f"{p['author']}"
            )
        print(f"\n  Use --id <program_id> for full details.")


def cmd_531(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Generate 5/3/1 workout for a specific lift and week."""
    lift = args.lift
    week = args.week

    print(_header(f"5/3/1 — {lift.title().upper()} — WEEK {week}"))

    try:
        sets = tracker.get_531_workout(lift, week)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    tm = tracker.athlete.training_max.get(lift.lower(), 0)
    print(f"  Lift          : {lift.title()}")
    print(f"  Training Max  : {tm:.1f} kg")
    print(f"  Week Type     : {sets[0]['label'].split(':')[0] if sets else '?'}")
    print()
    print(f"  {'Set':<6} {'%':<6} {'Target (kg)':<14} {'Reps':<8} {'Notes'}")
    print(f"  {'─'*50}")
    for s in sets:
        amrap_note = " AMRAP" if s["is_amrap"] else ""
        print(
            f"  {s['set_number']:<6} {s['percentage']:<6} "
            f"{s['target_weight_kg']:<14.1f} "
            f"{s['prescribed_reps']:<8} {amrap_note}"
        )

    print(f"\n  Reminder: Last set of Week 1/2/3 is AMRAP (as many reps as possible).")
    print(f"  After completing Week 4 (deload), advance your training max.")


def cmd_e1rm(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Estimate 1RM from a set."""
    weight = args.weight
    reps = args.reps

    print(_header(f"ESTIMATED 1RM — {weight} kg × {reps} reps"))

    result = tracker.estimate_1rm(weight, reps)
    print(f"  Epley e1RM    : {result['epley_e1rm_kg']:.1f} kg")
    if result["brzycki_e1rm_kg"] is not None:
        print(f"  Brzycki e1RM  : {result['brzycki_e1rm_kg']:.1f} kg")
    avg_str = f"{result['average_e1rm_kg']:.1f} kg"
    print(f"  Average e1RM  : {_bold(avg_str)}")
    print(f"  Training Max (90%) : {result['training_max_90pct']:.1f} kg")
    if result.get("reliability") == "low":
        print(f"\n  {_yellow('NOTE:')} {result['reliability_note']}")


def cmd_wilks(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Calculate Wilks score."""
    squat = args.squat
    bench = args.bench
    deadlift = args.deadlift

    print(_header("WILKS SCORE CALCULATOR"))

    result = tracker.calculate_wilks(squat, bench, deadlift)
    print(f"  Body Weight : {result['bodyweight_kg']:.1f} kg")
    print(f"  Squat       : {result['squat_kg']:.1f} kg")
    print(f"  Bench Press : {result['bench_kg']:.1f} kg")
    print(f"  Deadlift    : {result['deadlift_kg']:.1f} kg")
    print(f"  Total       : {result['total_kg']:.1f} kg")
    print(f"  Wilks Score : {_bold(str(result['wilks_score']))}")
    print(f"  Level       : {_bold(result['strength_level'])}")


def cmd_summary(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Print athlete summary report."""
    print(tracker.generate_summary_report())


def cmd_history(args: argparse.Namespace, tracker: PowerliftingTracker) -> None:
    """Show session history."""
    sessions = tracker.get_all_sessions()

    if not sessions:
        print("No sessions logged yet.")
        return

    limit = getattr(args, "last", 20)
    sessions = sessions[-limit:]

    print(_header(f"SESSION HISTORY (last {len(sessions)})"))
    header = f"  {'Date':<12} {'Session ID':<10} {'Program':<22} {'Day Label':<25} {'Volume (kg)':<12} {'Duration'}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    for s in sessions:
        prog = s.program_id or ""
        dur = f"{s.duration_minutes} min" if s.duration_minutes else "—"
        print(
            f"  {s.date:<12} {s.session_id:<10} "
            f"{prog:<22} {(s.day_label or '—'):<25} "
            f"{s.total_volume_kg:<12.0f} {dur}"
        )

    if getattr(args, "lift", None):
        lift = args.lift
        progression = tracker.get_volume_progression(lift)
        if progression:
            print(_header(f"VOLUME PROGRESSION — {lift.upper()}"))
            for entry in progression:
                print(
                    f"  {entry['date']:<12} Volume: {entry['volume_kg']:>8.0f} kg  "
                    f"Heaviest: {entry['heaviest_kg']:>7.1f} kg  "
                    f"Total reps: {entry['total_reps']}"
                )
        else:
            print(f"\nNo {lift} data found in session history.")


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="powerlifting-tracker",
        description="Powerlifting program tracker, nutrition calculator, and supplement guide.",
    )
    parser.add_argument(
        "--db", default="./workout_data",
        help="Path to the database directory (default: ./workout_data)"
    )

    subparsers = parser.add_subparsers(dest="command", title="Commands")
    subparsers.required = True

    # setup
    subparsers.add_parser("setup", help="Set up or update athlete profile")

    # session
    subparsers.add_parser("session", help="Log a training session interactively")

    # nutrition
    n_parser = subparsers.add_parser("nutrition", help="Calculate nutrition targets")
    n_parser.add_argument(
        "--phase", choices=["lean_bulk", "aggressive_bulk", "cut", "maintenance", "meet_peak"],
        default="maintenance",
        help="Nutrition phase (default: maintenance)"
    )
    n_parser.add_argument("--all-phases", action="store_true", help="Show all phases")

    # supplements
    s_parser = subparsers.add_parser("supplements", help="Supplement guide with evidence ratings")
    s_parser.add_argument("--priority", type=int, default=9, help="Max priority rank to show (1–9)")

    # programs
    p_parser = subparsers.add_parser("programs", help="Browse powerlifting programs")
    p_parser.add_argument("--level", choices=["beginner", "intermediate", "advanced"], help="Filter by level")
    p_parser.add_argument("--id", dest="id", help="Show details for a specific program ID")

    # 531
    five31_parser = subparsers.add_parser("531", help="Generate 5/3/1 workout")
    five31_parser.add_argument("lift", choices=["squat", "bench", "deadlift", "ohp"], help="Lift name")
    five31_parser.add_argument("week", type=int, choices=[1, 2, 3, 4], help="Week number (1–4)")

    # e1rm
    def _positive_float(value):
        fval = float(value)
        if fval <= 0:
            raise argparse.ArgumentTypeError(f"weight must be a positive number, got {value}")
        return fval

    def _positive_int(value):
        ival = int(value)
        if ival <= 0:
            raise argparse.ArgumentTypeError(f"reps must be a positive integer, got {value}")
        return ival

    e1rm_parser = subparsers.add_parser("e1rm", help="Estimate 1 rep max")
    e1rm_parser.add_argument("weight", type=_positive_float, help="Weight lifted (kg, must be > 0)")
    e1rm_parser.add_argument("reps", type=_positive_int, help="Reps completed (must be > 0)")

    # wilks
    w_parser = subparsers.add_parser("wilks", help="Calculate Wilks score")
    w_parser.add_argument("squat", type=float, help="Squat (kg)")
    w_parser.add_argument("bench", type=float, help="Bench press (kg)")
    w_parser.add_argument("deadlift", type=float, help="Deadlift (kg)")

    # summary
    subparsers.add_parser("summary", help="Print athlete summary report")

    # history
    h_parser = subparsers.add_parser("history", help="Show training session history")
    h_parser.add_argument("--last", type=int, default=20, help="Number of recent sessions to show")
    h_parser.add_argument("--lift", help="Show volume progression for a specific lift")

    return parser


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

COMMAND_MAP = {
    "setup": cmd_setup,
    "session": cmd_session,
    "nutrition": cmd_nutrition,
    "supplements": cmd_supplements,
    "programs": cmd_programs,
    "531": cmd_531,
    "e1rm": cmd_e1rm,
    "wilks": cmd_wilks,
    "summary": cmd_summary,
    "history": cmd_history,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    tracker = PowerliftingTracker(db_path=args.db)

    # Commands that don't need an existing profile
    if args.command not in {"setup", "programs", "e1rm"}:
        try:
            _ = tracker.athlete  # Will raise if no profile
        except RuntimeError:
            print("No athlete profile found. Run 'setup' first.")
            return 1

    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}")
        return 1

    try:
        handler(args, tracker)
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
