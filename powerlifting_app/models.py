"""
models.py — Pure-Python data classes for the powerlifting tracker.

No external dependencies. All state is stored in plain Python objects
and serialized to/from JSON for persistence.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Workout Logging
# ---------------------------------------------------------------------------

@dataclass
class Set:
    """A single working set within an exercise."""
    weight_kg: float
    reps: int
    rpe: Optional[float] = None   # Rate of Perceived Exertion 1–10, optional
    is_amrap: bool = False         # True if this was an AMRAP set
    actual_reps: Optional[int] = None  # For AMRAP: reps actually achieved
    notes: str = ""

    @property
    def volume(self) -> float:
        """Total volume for this set in kg."""
        return self.weight_kg * self.reps

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Set":
        return cls(**d)


@dataclass
class Exercise:
    """One exercise within a training session."""
    name: str
    sets: list[Set] = field(default_factory=list)
    tier: Optional[str] = None   # For GZCL: "T1", "T2", "T3"
    notes: str = ""

    @property
    def total_volume_kg(self) -> float:
        return sum(s.volume for s in self.sets)

    @property
    def heaviest_set_kg(self) -> float:
        if not self.sets:
            return 0.0
        return max(s.weight_kg for s in self.sets)

    @property
    def total_reps(self) -> int:
        return sum(s.reps for s in self.sets)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "sets": [s.to_dict() for s in self.sets],
            "tier": self.tier,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Exercise":
        sets = [Set.from_dict(s) for s in d.get("sets", [])]
        remaining = {k: v for k, v in d.items() if k != "sets"}
        return cls(sets=sets, **remaining)


@dataclass
class WorkoutSession:
    """A complete training session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    date: str = field(default_factory=lambda: date.today().isoformat())
    program_id: Optional[str] = None   # Which program this session belongs to
    week_number: Optional[int] = None  # For cycle-based programs
    day_label: str = ""                # e.g., "Workout A", "Lower Max Effort"
    exercises: list[Exercise] = field(default_factory=list)
    bodyweight_kg: Optional[float] = None
    session_rpe: Optional[float] = None   # Overall session RPE
    duration_minutes: Optional[int] = None
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total_volume_kg(self) -> float:
        return sum(e.total_volume_kg for e in self.exercises)

    @property
    def date_obj(self) -> date:
        return date.fromisoformat(self.date)

    def get_exercise(self, name: str) -> Optional[Exercise]:
        """Return the first exercise matching the given name (case-insensitive)."""
        name_lower = name.lower()
        for ex in self.exercises:
            if ex.name.lower() == name_lower:
                return ex
        return None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "date": self.date,
            "program_id": self.program_id,
            "week_number": self.week_number,
            "day_label": self.day_label,
            "exercises": [e.to_dict() for e in self.exercises],
            "bodyweight_kg": self.bodyweight_kg,
            "session_rpe": self.session_rpe,
            "duration_minutes": self.duration_minutes,
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkoutSession":
        exercises = [Exercise.from_dict(e) for e in d.get("exercises", [])]
        remaining = {k: v for k, v in d.items() if k != "exercises"}
        return cls(exercises=exercises, **remaining)


# ---------------------------------------------------------------------------
# Personal Records
# ---------------------------------------------------------------------------

@dataclass
class PersonalRecord:
    """A 1RM (or estimated 1RM) personal record for a lift."""
    lift_name: str
    weight_kg: float
    reps: int = 1        # If not a true 1RM, record actual reps for e1RM calc
    date: str = field(default_factory=lambda: date.today().isoformat())
    session_id: Optional[str] = None
    notes: str = ""

    @property
    def estimated_1rm_kg(self) -> float:
        """
        Epley formula: e1RM = weight × (1 + reps / 30)
        For reps == 1, returns the actual weight.
        """
        if self.reps == 1:
            return self.weight_kg
        return self.weight_kg * (1 + self.reps / 30)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PersonalRecord":
        return cls(**d)


# ---------------------------------------------------------------------------
# Athlete Profile
# ---------------------------------------------------------------------------

@dataclass
class AthleteProfile:
    """Core athlete settings used across all calculators."""
    name: str
    bodyweight_kg: float
    height_cm: float
    age: int
    sex: str                        # "male" or "female"
    activity_level: str             # key from ACTIVITY_MULTIPLIERS
    current_program_id: Optional[str] = None
    training_max: dict[str, float] = field(default_factory=dict)
    # e.g. {"squat": 140.0, "bench": 100.0, "deadlift": 180.0, "ohp": 70.0}
    one_rep_maxes: dict[str, float] = field(default_factory=dict)
    goals: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def bmr(self) -> float:
        """
        Mifflin-St Jeor BMR formula.
        Male:   10 × weight_kg + 6.25 × height_cm − 5 × age + 5
        Female: 10 × weight_kg + 6.25 × height_cm − 5 × age − 161
        """
        base = 10 * self.bodyweight_kg + 6.25 * self.height_cm - 5 * self.age
        return base + 5 if self.sex.lower() == "male" else base - 161

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AthleteProfile":
        return cls(**d)


# ---------------------------------------------------------------------------
# Program Progress Tracker
# ---------------------------------------------------------------------------

@dataclass
class ProgramProgress:
    """Tracks current position within a cycle-based program."""
    program_id: str
    start_date: str = field(default_factory=lambda: date.today().isoformat())
    current_week: int = 1
    current_cycle: int = 1
    training_maxes: dict[str, float] = field(default_factory=dict)
    # Lift name → current training max (kg)
    session_history: list[str] = field(default_factory=list)
    # List of session_ids in order completed
    notes: str = ""

    def advance_week(self, total_weeks_in_cycle: int) -> None:
        """Move to the next week; rolls over to a new cycle if needed."""
        if self.current_week >= total_weeks_in_cycle:
            self.current_week = 1
            self.current_cycle += 1
        else:
            self.current_week += 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProgramProgress":
        return cls(**d)


# ---------------------------------------------------------------------------
# Persistence Layer
# ---------------------------------------------------------------------------

class WorkoutDatabase:
    """
    Simple JSON-backed persistence layer.

    Directory layout:
        db_path/
            athlete.json          — AthleteProfile
            sessions/
                <session_id>.json — WorkoutSession
            personal_records.json — list[PersonalRecord]
            program_progress.json — dict[program_id, ProgramProgress]
    """

    def __init__(self, db_path: str | Path = "./workout_data") -> None:
        self.db_path = Path(db_path)
        self._sessions_dir = self.db_path / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    # ---- Athlete -----------------------------------------------------------

    def save_athlete(self, profile: AthleteProfile) -> None:
        self._write_json(self.db_path / "athlete.json", profile.to_dict())

    def load_athlete(self) -> Optional[AthleteProfile]:
        p = self.db_path / "athlete.json"
        if not p.exists():
            return None
        return AthleteProfile.from_dict(self._read_json(p))

    # ---- Sessions ----------------------------------------------------------

    def save_session(self, session: WorkoutSession) -> None:
        path = self._sessions_dir / f"{session.session_id}.json"
        self._write_json(path, session.to_dict())

    def load_session(self, session_id: str) -> Optional[WorkoutSession]:
        path = self._sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None
        return WorkoutSession.from_dict(self._read_json(path))

    def load_all_sessions(self) -> list[WorkoutSession]:
        sessions = []
        for p in sorted(self._sessions_dir.glob("*.json")):
            sessions.append(WorkoutSession.from_dict(self._read_json(p)))
        # Sort by date ascending
        return sorted(sessions, key=lambda s: s.date)

    def delete_session(self, session_id: str) -> bool:
        path = self._sessions_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # ---- Personal Records --------------------------------------------------

    def save_personal_records(self, records: list[PersonalRecord]) -> None:
        self._write_json(
            self.db_path / "personal_records.json",
            [r.to_dict() for r in records],
        )

    def load_personal_records(self) -> list[PersonalRecord]:
        p = self.db_path / "personal_records.json"
        if not p.exists():
            return []
        return [PersonalRecord.from_dict(d) for d in self._read_json(p)]

    # ---- Program Progress --------------------------------------------------

    def save_program_progress(self, progress: ProgramProgress) -> None:
        all_prog = self._load_all_progress_raw()
        all_prog[progress.program_id] = progress.to_dict()
        self._write_json(self.db_path / "program_progress.json", all_prog)

    def load_program_progress(self, program_id: str) -> Optional[ProgramProgress]:
        all_prog = self._load_all_progress_raw()
        if program_id not in all_prog:
            return None
        return ProgramProgress.from_dict(all_prog[program_id])

    def _load_all_progress_raw(self) -> dict:
        p = self.db_path / "program_progress.json"
        if not p.exists():
            return {}
        return self._read_json(p)

    # ---- Helpers -----------------------------------------------------------

    @staticmethod
    def _write_json(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))

    @staticmethod
    def _read_json(path: Path) -> object:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
