import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from threading import Lock

RUNBOOKS_DIR = Path(__file__).parent / "data" / "runbooks"
RUNBOOK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REQUIRED_FIELDS = {
    "id",
    "title",
    "category",
    "technologies",
    "environment",
    "severity",
    "symptoms",
    "error_messages",
    "root_cause",
    "prerequisites",
    "investigation_steps",
    "resolution_steps",
    "verification_steps",
    "rollback_steps",
    "prevention",
    "tags",
    "created_at",
    "updated_at",
}
STRING_FIELDS = {"title", "category", "environment"}
LIST_FIELDS = {
    "technologies",
    "symptoms",
    "error_messages",
    "prerequisites",
    "verification_steps",
    "rollback_steps",
    "prevention",
    "tags",
}
STEP_FIELDS = {"investigation_steps", "resolution_steps"}
STEP_DETAIL_FIELDS = {"description", "command", "expected_result", "notes"}
SEARCH_LIST_FIELDS = (
    "symptoms",
    "error_messages",
    "commands",
    "tags",
)
SEVERITIES = {"critical", "high", "medium", "low"}
ROOT_CAUSE_STATUSES = {"unknown", "suspected", "confirmed"}
_WRITE_LOCK = Lock()


class RunbookValidationError(ValueError):
    pass


class RunbookStorageError(Exception):
    pass


class DuplicateRunbookError(Exception):
    pass


def _validate_steps(value, field):
    if not isinstance(value, list):
        raise RunbookValidationError(
            f"Field '{field}' must be a list of steps."
        )

    for index, step in enumerate(value):
        if isinstance(step, str) and step.strip():
            continue
        if not isinstance(step, dict):
            raise RunbookValidationError(
                f"Each item in '{field}' must be a non-empty string or step object."
            )
        if not STEP_DETAIL_FIELDS.issuperset(step):
            raise RunbookValidationError(
                f"Step objects in '{field}' may contain only "
                "description, command, expected_result, and notes."
            )
        description = step.get("description")
        if not isinstance(description, str) or not description.strip():
            raise RunbookValidationError(
                f"Step {index + 1} in '{field}' needs a non-empty description."
            )
        for detail in STEP_DETAIL_FIELDS - {"description"}:
            if detail in step and not isinstance(step[detail], str):
                raise RunbookValidationError(
                    f"Step field '{detail}' in '{field}' must be a string."
                )


def validate_runbook(data):
    if not isinstance(data, dict):
        raise RunbookValidationError("Runbook must be a JSON object.")

    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        raise RunbookValidationError(
            "Missing required fields: " + ", ".join(missing) + "."
        )

    runbook_id = data["id"]
    if not isinstance(runbook_id, str) or not RUNBOOK_ID_PATTERN.fullmatch(runbook_id):
        raise RunbookValidationError(
            "Field 'id' must use 1-64 lowercase letters, digits, or hyphens "
            "and start with a letter or digit."
        )

    for field in STRING_FIELDS:
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            raise RunbookValidationError(f"Field '{field}' must be a non-empty string.")

    if not isinstance(data["severity"], str) or data["severity"] not in SEVERITIES:
        raise RunbookValidationError(
            "Field 'severity' must be critical, high, medium, or low."
        )

    for field in LIST_FIELDS:
        value = data[field]
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise RunbookValidationError(
                f"Field '{field}' must be a list of non-empty strings."
            )

    for field in STEP_FIELDS:
        _validate_steps(data[field], field)

    root_cause = data["root_cause"]
    if not isinstance(root_cause, dict):
        raise RunbookValidationError("Field 'root_cause' must be an object.")
    if set(root_cause) != {"status", "details"}:
        raise RunbookValidationError(
            "Field 'root_cause' must contain only 'status' and 'details'."
        )
    if (
        not isinstance(root_cause["status"], str)
        or root_cause["status"] not in ROOT_CAUSE_STATUSES
    ):
        raise RunbookValidationError(
            "Field 'root_cause.status' must be unknown, suspected, or confirmed."
        )
    if not isinstance(root_cause["details"], str):
        raise RunbookValidationError("Field 'root_cause.details' must be a string.")

    timestamps = {}
    for field in ("created_at", "updated_at"):
        value = data[field]
        if not isinstance(value, str):
            raise RunbookValidationError(
                f"Field '{field}' must be an ISO 8601 datetime string."
            )
        try:
            timestamps[field] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise RunbookValidationError(
                f"Field '{field}' must be an ISO 8601 datetime string."
            ) from error
        if timestamps[field].utcoffset() is None:
            raise RunbookValidationError(
                f"Field '{field}' must include a timezone offset."
            )

    if timestamps["updated_at"] < timestamps["created_at"]:
        raise RunbookValidationError(
            "Field 'updated_at' cannot be earlier than 'created_at'."
        )

    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise RunbookValidationError("Field 'summary' must be a string.")

    for field in SEARCH_LIST_FIELDS:
        value = data.get(field, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise RunbookValidationError(
                f"Optional field '{field}' must be a list of non-empty strings."
            )

    return data


def runbook_path(runbook_id, runbooks_dir=None):
    if not isinstance(runbook_id, str) or not RUNBOOK_ID_PATTERN.fullmatch(runbook_id):
        raise RunbookValidationError("Invalid runbook ID.")

    root = Path(runbooks_dir or RUNBOOKS_DIR).resolve()
    path = root / f"{runbook_id}.json"
    if path.parent.resolve() != root:
        raise RunbookValidationError("Invalid runbook ID.")
    return path


def _read_runbook(path):
    if path.is_symlink():
        raise RunbookStorageError("Runbook data contains an unsafe file.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RunbookStorageError(
            f"Runbook data file '{path.name}' could not be read as valid JSON."
        ) from error

    try:
        validate_runbook(data)
    except RunbookValidationError as error:
        raise RunbookStorageError(
            f"Runbook data file '{path.name}' is invalid: {error}"
        ) from error

    if data["id"] != path.stem:
        raise RunbookStorageError(
            f"Runbook data file '{path.name}' does not match its runbook ID."
        )
    data.setdefault("summary", " ".join(data["symptoms"]))
    return data


def list_runbooks(runbooks_dir=None):
    directory = Path(runbooks_dir or RUNBOOKS_DIR)
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError as error:
        raise RunbookStorageError("Runbook storage could not be accessed.") from error
    return sorted(
        (_read_runbook(path) for path in paths),
        key=lambda runbook: runbook["id"],
    )


def search_runbooks(
    runbooks,
    query="",
    technology="",
    category="",
    environment="",
    severity="",
    sort="updated",
):
    normalized_query = query.strip().casefold()
    if normalized_query:
        def searchable_text(runbook):
            fields = [
                runbook["title"],
                *runbook["symptoms"],
                *runbook["error_messages"],
                *runbook.get("commands", []),
                *runbook["tags"],
            ]
            for field in STEP_FIELDS:
                for step in runbook[field]:
                    if isinstance(step, str):
                        fields.append(step)
                    else:
                        fields.extend(
                            step.get(detail, "")
                            for detail in STEP_DETAIL_FIELDS
                        )
            return " ".join(fields).casefold()

        runbooks = [
            runbook for runbook in runbooks
            if normalized_query in searchable_text(runbook)
        ]

    filters = {
        "technology": technology,
        "category": category,
        "environment": environment,
        "severity": severity,
    }
    for field, value in filters.items():
        if value:
            runbooks = [
                runbook
                for runbook in runbooks
                if (
                    any(
                        technology.casefold() == value.casefold()
                        for technology in runbook["technologies"]
                    )
                    if field == "technology"
                    else runbook[field].casefold() == value.casefold()
                )
            ]

    if sort == "title":
        return sorted(runbooks, key=lambda item: (item["title"].casefold(), item["id"]))
    return sorted(
        runbooks,
        key=lambda item: (
            datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00")).timestamp(),
            item["id"],
        ),
        reverse=True,
    )


def get_runbook(runbook_id, runbooks_dir=None):
    path = runbook_path(runbook_id, runbooks_dir)
    if not path.exists() and not path.is_symlink():
        return None
    return _read_runbook(path)


def create_runbook(data, runbooks_dir=None):
    runbook = validate_runbook(data)
    directory = Path(runbooks_dir or RUNBOOKS_DIR)
    path = runbook_path(runbook["id"], directory)
    temporary_path = None

    try:
        with _WRITE_LOCK:
            directory.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink():
                raise DuplicateRunbookError(
                    f"Runbook ID '{runbook['id']}' already exists."
                )

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{runbook['id']}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(runbook, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            try:
                os.link(temporary_path, path)
            except FileExistsError as error:
                raise DuplicateRunbookError(
                    f"Runbook ID '{runbook['id']}' already exists."
                ) from error
    except DuplicateRunbookError:
        raise
    except (OSError, UnicodeError, TypeError) as error:
        raise RunbookStorageError("Runbook could not be saved safely.") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    return runbook


def update_runbook(runbook_id, data, runbooks_dir=None):
    runbook = validate_runbook(data)
    if runbook["id"] != runbook_id:
        raise RunbookValidationError(
            "Field 'id' must match the runbook being updated."
        )

    directory = Path(runbooks_dir or RUNBOOKS_DIR)
    path = runbook_path(runbook_id, directory)
    temporary_path = None

    try:
        with _WRITE_LOCK:
            if not path.exists() and not path.is_symlink():
                return None
            _read_runbook(path)
            created_at = datetime.fromisoformat(
                runbook["created_at"].replace("Z", "+00:00")
            )
            updated_at = datetime.fromisoformat(
                runbook["updated_at"].replace("Z", "+00:00")
            )
            modified_at = datetime.now().astimezone()
            runbook["updated_at"] = max(
                created_at,
                updated_at,
                modified_at,
            ).isoformat()
            validate_runbook(runbook)

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{runbook_id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(runbook, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, path)
            temporary_path = None
    except RunbookStorageError:
        raise
    except (OSError, UnicodeError, TypeError) as error:
        raise RunbookStorageError("Runbook could not be updated safely.") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    return runbook


def delete_runbook(runbook_id, runbooks_dir=None):
    path = runbook_path(runbook_id, runbooks_dir)
    try:
        with _WRITE_LOCK:
            if not path.exists() and not path.is_symlink():
                return False
            _read_runbook(path)
            path.unlink()
    except RunbookStorageError:
        raise
    except OSError as error:
        raise RunbookStorageError("Runbook could not be deleted safely.") from error

    return True
