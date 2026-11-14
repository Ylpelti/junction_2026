from enum import StrEnum


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    INTERSEX = "intersex"
    UNKNOWN = "unknown"


class ObservationType(StrEnum):
    CLINICAL_NOTE = "clinical_note"
    SYMPTOM = "symptom"
    LABORATORY = "laboratory"
    INVESTIGATION = "investigation"
    VITAL_SIGN = "vital_sign"
    DIAGNOSIS = "diagnosis"
    MEDICATION = "medication"


class FindingStatus(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    RESOLVED = "resolved"
    NEGATED = "negated"
    UNCERTAIN = "uncertain"


class ObservationStatus(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    RESOLVED = "resolved"
    NEGATED = "negated"
    UNCERTAIN = "uncertain"
    COMPLETED = "completed"
    PLANNED = "planned"


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
