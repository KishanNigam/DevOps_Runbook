from urllib.parse import urlsplit
import logging
import re

from flask import Flask, jsonify, render_template, request, url_for

import runbook_store
from runbook_store import (
    DuplicateRunbookError,
    RunbookStorageError,
    RunbookValidationError,
)

app = Flask(__name__)
logger = logging.getLogger(__name__)
RUNBOOKS_DIR = runbook_store.RUNBOOKS_DIR
APP_VERSION = "0.1.0"
COMMON_CATEGORIES = ("CI/CD", "Monitoring")
COMMON_TECHNOLOGIES = ("AWS", "Linux", "Jenkins", "Docker", "Kubernetes")


def storage_error_message(action):
    return {
        "read": (
            "Runbook data could not be read. Check file permissions, JSON syntax, "
            "and record fields."
        ),
        "save": "Runbook could not be saved. Check write permissions and try again.",
        "update": (
            "Runbook could not be updated. Check write permissions and try again; "
            "the existing data was preserved."
        ),
        "delete": "Runbook could not be deleted. Check file permissions and try again.",
    }[action]


def load_runbooks():
    return runbook_store.search_runbooks(
        runbook_store.list_runbooks(RUNBOOKS_DIR),
    )


def build_browse_groups(runbooks, field, examples):
    names = {}
    counts = {}
    for runbook in runbooks:
        values = (
            [runbook.get(field) or "Uncategorized"]
            if field == "category"
            else runbook.get(field, [])
        )
        if not isinstance(values, (list, tuple, set)):
            values = []
        unique_values = {
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        }
        for value in unique_values:
            key = value.casefold()
            names.setdefault(key, value)
            counts[key] = counts.get(key, 0) + 1

    for example in examples:
        names.setdefault(example.casefold(), example)
        counts.setdefault(example.casefold(), 0)

    return [
        {"name": names[key], "count": counts[key]}
        for key in sorted(names, key=lambda item: (names[item].casefold(), names[item]))
    ]


def safe_return_to(value, default="/runbooks"):
    parsed = urlsplit(value or "")
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        return default

    if parsed.path not in {"/", "/runbooks"} and not re.fullmatch(
        r"/runbooks/[a-z0-9][a-z0-9-]{0,63}", parsed.path
    ):
        return default

    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


@app.route("/")
def home():
    data_error = None
    try:
        runbooks = load_runbooks()
    except RunbookStorageError:
        logger.exception("Could not read runbooks for the dashboard")
        runbooks = []
        data_error = storage_error_message("read")

    runbook_categories = sorted({
        runbook["category"]
        for runbook in runbooks
    }, key=str.casefold)
    runbook_technologies = sorted({
        technology
        for runbook in runbooks
        for technology in runbook["technologies"]
    }, key=str.casefold)
    technologies = {
        technology
        for runbook in runbooks
        for technology in runbook["technologies"]
        if technology
    }
    return render_template(
        "index.html",
        runbooks=runbooks[:5],
        runbook_count=len(runbooks) if data_error is None else "Unavailable",
        technology_count=len(technologies) if data_error is None else "Unavailable",
        runbook_categories=runbook_categories,
        runbook_technologies=runbook_technologies,
        data_error=data_error,
    )


@app.get("/runbooks")
def all_runbooks():
    return render_template("runbooks.html")


@app.get("/categories")
def browse_categories():
    try:
        runbooks = runbook_store.list_runbooks(RUNBOOKS_DIR)
    except RunbookStorageError:
        logger.exception("Could not load data for category and technology browsing")
        return render_template(
            "categories.html",
            categories=[],
            technologies=[],
            browse_error=storage_error_message("read"),
        ), 500

    return render_template(
        "categories.html",
        categories=build_browse_groups(
            runbooks,
            "category",
            COMMON_CATEGORIES,
        ),
        technologies=build_browse_groups(
            runbooks,
            "technologies",
            COMMON_TECHNOLOGIES,
        ),
        runbook_count=len(runbooks),
    )


@app.get("/settings-help")
def settings_help():
    return render_template("settings-help.html", app_version=APP_VERSION)


@app.get("/runbooks/new")
def new_runbook():
    return_to = safe_return_to(request.args.get("return_to"), url_for("all_runbooks"))
    results_url = safe_return_to(request.args.get("results_url"), return_to)
    return render_template(
        "runbook-form.html",
        mode="create",
        runbook=None,
        return_to=return_to,
        results_url=results_url,
    )


@app.get("/runbooks/<runbook_id>/edit")
def edit_runbook(runbook_id):
    return_to = safe_return_to(request.args.get("return_to"), url_for("runbook_detail", runbook_id=runbook_id))
    results_url = safe_return_to(request.args.get("results_url"), url_for("all_runbooks"))
    try:
        runbook = runbook_store.get_runbook(runbook_id, RUNBOOKS_DIR)
    except RunbookValidationError:
        runbook = None
    except RunbookStorageError:
        logger.exception("Could not load runbook for editing")
        return render_template(
            "runbook-form.html",
            mode="edit",
            runbook=None,
            return_to=return_to,
            results_url=results_url,
            form_error=storage_error_message("read"),
        ), 500

    if runbook is None:
        return render_template(
            "runbook-form.html",
            mode="edit",
            runbook=None,
            return_to=url_for("all_runbooks"),
            results_url=url_for("all_runbooks"),
            form_error="This runbook was not found.",
        ), 404

    return render_template(
        "runbook-form.html",
        mode="edit",
        runbook=runbook,
        return_to=return_to,
        results_url=results_url,
    )


@app.get("/runbooks/<runbook_id>")
def runbook_detail(runbook_id):
    try:
        runbook = runbook_store.get_runbook(runbook_id, RUNBOOKS_DIR)
    except RunbookValidationError:
        runbook = None
    except RunbookStorageError:
        logger.exception("Could not load runbook detail")
        return render_template(
            "runbook-detail.html",
            runbook=None,
            return_to=url_for("all_runbooks"),
            detail_error=storage_error_message("read"),
        ), 500

    if runbook is None:
        return render_template(
            "runbook-detail.html",
            runbook=None,
            return_to=url_for("all_runbooks"),
        ), 404

    return_to = safe_return_to(
        request.args.get("return_to"),
        url_for("all_runbooks"),
    )

    return render_template(
        "runbook-detail.html",
        runbook=runbook,
        return_to=return_to,
        notice={
            "created": "Runbook created successfully.",
            "updated": "Runbook updated successfully.",
        }.get(request.args.get("saved"), ""),
    )


@app.get("/api/runbooks")
def api_list_runbooks():
    try:
        runbooks = runbook_store.list_runbooks(RUNBOOKS_DIR)
    except RunbookStorageError:
        logger.exception("Could not list runbooks")
        return jsonify(error=storage_error_message("read")), 500

    sort = request.args.get("sort", "updated")
    if sort not in {"updated", "title"}:
        return jsonify(error="Sort must be 'updated' or 'title'."), 400

    filters = {
        "technology": request.args.get("technology", ""),
        "category": request.args.get("category", ""),
        "environment": request.args.get("environment", ""),
        "severity": request.args.get("severity", ""),
    }
    facets = {
        "technology": sorted({
            technology
            for runbook in runbooks
            for technology in runbook["technologies"]
        }, key=str.casefold),
        "category": sorted({runbook["category"] for runbook in runbooks}, key=str.casefold),
        "environment": sorted(
            {runbook["environment"] for runbook in runbooks},
            key=str.casefold,
        ),
        "severity": sorted({runbook["severity"] for runbook in runbooks}),
    }
    matches = runbook_store.search_runbooks(
        runbooks,
        query=request.args.get("q", ""),
        sort=sort,
        **filters,
    )
    return jsonify(
        count=len(matches),
        total=len(runbooks),
        filters=facets,
        runbooks=matches,
    )


@app.get("/api/runbooks/<runbook_id>")
def api_get_runbook(runbook_id):
    try:
        runbook = runbook_store.get_runbook(runbook_id, RUNBOOKS_DIR)
    except RunbookValidationError as error:
        return jsonify(error=str(error)), 400
    except RunbookStorageError:
        logger.exception("Could not retrieve runbook")
        return jsonify(error=storage_error_message("read")), 500

    if runbook is None:
        return jsonify(error=f"Runbook '{runbook_id}' was not found."), 404
    return jsonify(runbook=runbook)


@app.post("/api/runbooks")
def api_create_runbook():
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json."), 415
    data = request.get_json(silent=True)
    if data is None:
        return jsonify(error="Request body must contain valid JSON."), 400

    try:
        runbook = runbook_store.create_runbook(data, RUNBOOKS_DIR)
    except RunbookValidationError as error:
        return jsonify(error=str(error)), 400
    except DuplicateRunbookError as error:
        return jsonify(error=str(error)), 409
    except RunbookStorageError:
        logger.exception("Could not save runbook")
        return jsonify(error=storage_error_message("save")), 500

    response = jsonify(runbook=runbook)
    response.status_code = 201
    response.headers["Location"] = url_for(
        "api_get_runbook", runbook_id=runbook["id"]
    )
    return response


@app.put("/api/runbooks/<runbook_id>")
def api_update_runbook(runbook_id):
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json."), 415
    data = request.get_json(silent=True)
    if data is None:
        return jsonify(error="Request body must contain valid JSON."), 400

    try:
        runbook = runbook_store.update_runbook(runbook_id, data, RUNBOOKS_DIR)
    except RunbookValidationError as error:
        return jsonify(error=str(error)), 400
    except RunbookStorageError:
        logger.exception("Could not update runbook")
        return jsonify(error=storage_error_message("update")), 500

    if runbook is None:
        return jsonify(error=f"Runbook '{runbook_id}' was not found."), 404
    return jsonify(runbook=runbook)


@app.delete("/api/runbooks/<runbook_id>")
def api_delete_runbook(runbook_id):
    try:
        deleted = runbook_store.delete_runbook(runbook_id, RUNBOOKS_DIR)
    except RunbookValidationError as error:
        return jsonify(error=str(error)), 400
    except RunbookStorageError as error:
        logger.exception("Could not delete runbook")
        return jsonify(error=storage_error_message("delete")), 500

    if not deleted:
        return jsonify(error=f"Runbook '{runbook_id}' was not found."), 404
    return jsonify(message=f"Runbook '{runbook_id}' was deleted.")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
