import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import app
import runbook_store


def valid_runbook(runbook_id="test-runbook"):
    return {
        "id": runbook_id,
        "title": "Test runbook",
        "category": "Testing",
        "technologies": ["Python"],
        "environment": "Local test environment",
        "severity": "medium",
        "symptoms": ["A test condition occurs."],
        "error_messages": [],
        "root_cause": {
            "status": "suspected",
            "details": "A test cause.",
        },
        "prerequisites": [],
        "investigation_steps": ["Inspect the test condition."],
        "resolution_steps": ["Apply a test resolution."],
        "verification_steps": ["Confirm the test resolution."],
        "rollback_steps": [],
        "prevention": [],
        "tags": ["test"],
        "created_at": "2026-10-11T10:00:00Z",
        "updated_at": "2026-10-11T10:00:00Z",
    }


class RunbookApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.runbooks_directory = Path(self.temporary_directory.name) / "runbooks"
        self.original_directory = app.RUNBOOKS_DIR
        app.RUNBOOKS_DIR = self.runbooks_directory
        self.client = app.app.test_client()

    def tearDown(self):
        app.RUNBOOKS_DIR = self.original_directory
        self.temporary_directory.cleanup()

    def write_runbook(self, data, filename=None):
        self.runbooks_directory.mkdir(parents=True, exist_ok=True)
        path = self.runbooks_directory / (filename or f"{data['id']}.json")
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_list_and_retrieve_runbooks(self):
        record = valid_runbook()
        self.write_runbook(record)

        response = self.client.get("/api/runbooks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)
        self.assertEqual(response.get_json()["runbooks"][0]["id"], record["id"])

        detail = self.client.get(f"/api/runbooks/{record['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["runbook"]["title"], record["title"])

    def test_search_matches_exact_partial_and_case_insensitive_title(self):
        record = valid_runbook()
        record["title"] = "Kubernetes Node Recovery"
        self.write_runbook(record)

        exact = self.client.get("/api/runbooks?q=Kubernetes%20Node%20Recovery")
        partial = self.client.get("/api/runbooks?q=node")
        mixed_case = self.client.get("/api/runbooks?q=kUbErNeTeS")
        self.assertEqual(exact.get_json()["count"], 1)
        self.assertEqual(partial.get_json()["count"], 1)
        self.assertEqual(mixed_case.get_json()["count"], 1)

    def test_search_covers_symptoms_errors_investigation_commands_resolution_and_tags(self):
        record = valid_runbook()
        record.update({
            "symptoms": ["symptomneedle"],
            "error_messages": ["errorneedle"],
            "investigation_steps": ["investigationneedle"],
            "commands": ["kubectl get pods --selector=commandneedle"],
            "resolution_steps": ["resolutionneedle"],
            "tags": ["tagneedle"],
        })
        self.write_runbook(record)

        for keyword in (
            "symptomneedle",
            "errorneedle",
            "investigationneedle",
            "commandneedle",
            "resolutionneedle",
            "tagneedle",
        ):
            with self.subTest(keyword=keyword):
                response = self.client.get(f"/api/runbooks?q={keyword}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["count"], 1)

    def test_search_covers_structured_step_details(self):
        record = valid_runbook()
        record["investigation_steps"] = [{
            "description": "Inspect the affected pod.",
            "command": "kubectl describe pod target",
            "expected_result": "Events identify the cause.",
            "notes": "Run from the intended namespace.",
        }]
        record["resolution_steps"] = [{
            "description": "Restart the workload.",
            "command": "kubectl rollout restart deployment/example",
            "expected_result": "A replacement pod becomes ready.",
            "notes": "Observe the rollout.",
        }]
        self.write_runbook(record)

        for keyword in ("target", "identify the cause", "intended namespace", "replacement pod"):
            with self.subTest(keyword=keyword):
                response = self.client.get(f"/api/runbooks?q={keyword.replace(' ', '%20')}")
                self.assertEqual(response.get_json()["count"], 1)

    def test_filters_combine_across_all_facets(self):
        selected = valid_runbook("selected")
        selected.update({
            "technologies": ["Python", "Flask"],
            "category": "Platform",
            "environment": "Staging",
            "severity": "high",
        })
        self.write_runbook(selected)

        other = valid_runbook("other")
        other.update({
            "technologies": ["Python"],
            "category": "Platform",
            "environment": "Staging",
            "severity": "low",
        })
        self.write_runbook(other)

        response = self.client.get(
            "/api/runbooks?technology=flask&category=platform"
            "&environment=STAGING&severity=HIGH"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)
        self.assertEqual(response.get_json()["runbooks"][0]["id"], "selected")

        for field, value, expected_count in (
            ("technology", "Flask", 1),
            ("category", "Platform", 2),
            ("environment", "Staging", 2),
            ("severity", "high", 1),
        ):
            with self.subTest(field=field):
                filtered = self.client.get(
                    f"/api/runbooks?{field}={value}"
                )
                self.assertEqual(filtered.get_json()["count"], expected_count)

    def test_sorting_by_updated_date_and_title(self):
        older = valid_runbook("older")
        older.update({
            "title": "Zulu",
            "created_at": "2026-10-09T10:00:00Z",
            "updated_at": "2026-10-10T10:00:00Z",
        })
        newer = valid_runbook("newer")
        newer.update({"title": "Alpha", "updated_at": "2026-10-11T10:00:00Z"})
        self.write_runbook(older)
        self.write_runbook(newer)

        recently_updated = self.client.get("/api/runbooks?sort=updated")
        by_title = self.client.get("/api/runbooks?sort=title")
        self.assertEqual(
            [item["id"] for item in recently_updated.get_json()["runbooks"]],
            ["newer", "older"],
        )
        self.assertEqual(
            [item["title"] for item in by_title.get_json()["runbooks"]],
            ["Alpha", "Zulu"],
        )

    def test_recent_sort_compares_instants_across_timezones(self):
        earlier = valid_runbook("earlier")
        earlier.update({
            "created_at": "2026-10-10T10:00:00Z",
            "updated_at": "2026-10-11T09:00:00+02:00",
        })
        later = valid_runbook("later")
        later.update({
            "created_at": "2026-10-10T10:00:00Z",
            "updated_at": "2026-10-11T08:00:00Z",
        })
        self.write_runbook(earlier)
        self.write_runbook(later)

        response = self.client.get("/api/runbooks?sort=updated")
        self.assertEqual(
            [item["id"] for item in response.get_json()["runbooks"]],
            ["later", "earlier"],
        )

    def test_empty_search_results_and_invalid_sort(self):
        self.write_runbook(valid_runbook())
        empty = self.client.get("/api/runbooks?q=no-such-runbook")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.get_json()["count"], 0)
        self.assertEqual(empty.get_json()["total"], 1)
        self.assertEqual(
            self.client.get("/api/runbooks?sort=unsupported").status_code,
            400,
        )

    def test_listing_and_detail_pages_render_and_link_to_api_detail(self):
        record = valid_runbook()
        self.write_runbook(record)

        listing = self.client.get("/runbooks")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"/api/runbooks", listing.data)
        self.assertIn(b"filter-technology", listing.data)

        detail = self.client.get(f"/runbooks/{record['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(f"/api/runbooks/{record['id']}".encode(), detail.data)
        self.assertIn(b"Symptoms", detail.data)
        self.assertIn(b"Investigation steps", detail.data)
        dashboard = self.client.get("/")
        self.assertIn(f"/runbooks/{record['id']}".encode(), dashboard.data)

    def test_all_pages_and_static_assets_are_reachable(self):
        self.write_runbook(valid_runbook())

        for route in (
            "/",
            "/runbooks",
            "/categories",
            "/settings-help",
            "/runbooks/new",
            "/runbooks/test-runbook",
            "/runbooks/test-runbook/edit",
        ):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)

        for asset in (
            "/static/css/style.css",
            "/static/js/app.js",
            "/static/js/runbooks.js",
            "/static/js/runbook-detail.js",
            "/static/js/runbook-form.js",
        ):
            with self.subTest(asset=asset):
                response = self.client.get(asset)
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 0)

    def test_category_and_technology_browsing_counts_groups_and_links_to_filters(self):
        cicd_one = valid_runbook("cicd-one")
        cicd_one.update({
            "category": "CI/CD",
            "technologies": ["Jenkins", "Docker", "Jenkins"],
        })
        cicd_two = valid_runbook("cicd-two")
        cicd_two.update({
            "category": "CI/CD",
            "technologies": ["Jenkins", "Kubernetes"],
        })
        no_technology = valid_runbook("no-technology")
        no_technology.update({
            "category": "Platform",
            "technologies": [],
        })
        for record in (cicd_one, cicd_two, no_technology):
            self.write_runbook(record)

        response = self.client.get("/categories")
        page = " ".join(response.get_data(as_text=True).split())

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/runbooks?category=CI/CD"', page)
        self.assertIn('href="/runbooks?technology=Jenkins"', page)
        self.assertIn(
            'data-browse-group="category" data-browse-name="CI/CD" '
            'data-runbook-count="2"',
            page,
        )
        self.assertIn(
            'data-browse-group="technology" data-browse-name="Jenkins" '
            'data-runbook-count="2"',
            page,
        )
        self.assertIn(
            'data-browse-group="technology" data-browse-name="Docker" '
            'data-runbook-count="1"',
            page,
        )
        self.assertIn(
            'data-browse-group="technology" data-browse-name="AWS" '
            'data-runbook-count="0"',
            page,
        )
        self.assertIn(
            'data-browse-group="category" data-browse-name="Monitoring" '
            'data-runbook-count="0"',
            page,
        )

        category_filter = self.client.get(
            "/api/runbooks",
            query_string={"category": "CI/CD"},
        )
        technology_filter = self.client.get(
            "/api/runbooks",
            query_string={"technology": "Jenkins"},
        )
        self.assertEqual(category_filter.get_json()["count"], 2)
        self.assertEqual(technology_filter.get_json()["count"], 2)

    def test_category_and_technology_browsing_shows_examples_for_empty_library(self):
        response = self.client.get("/categories")
        page = " ".join(response.get_data(as_text=True).split())

        self.assertEqual(response.status_code, 200)
        self.assertIn("0 runbooks in your library", page)
        self.assertIn("Your library is empty", page)
        self.assertIn(
            'data-browse-group="technology" data-browse-name="AWS" '
            'data-runbook-count="0"',
            page,
        )
        self.assertIn(
            'data-browse-group="category" data-browse-name="Monitoring" '
            'data-runbook-count="0"',
            page,
        )

    def test_category_and_technology_browsing_reports_storage_errors_safely(self):
        self.runbooks_directory.mkdir(parents=True)
        (self.runbooks_directory / "broken.json").write_text("{", encoding="utf-8")

        response = self.client.get("/categories")

        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Browse data unavailable", response.data)
        self.assertNotIn(str(self.runbooks_directory).encode(), response.data)

    def test_settings_help_page_documents_app_data_workflow_git_backup_and_troubleshooting(self):
        response = self.client.get("/settings-help")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for expected in (
            "DevOps Runbook",
            "0.1.0",
            "data/runbooks/",
            "one JSON file per runbook",
            "runbook files and schema",
            "/runbooks/new",
            "git clone",
            "git pull",
            "git diff",
            "git commit",
            "git push",
            "Copy-Item",
            "py -m venv .venv",
            "python -m pip install -r requirements.txt",
            "python app.py",
            "http://127.0.0.1:5000/",
            "Flask is not installed",
            "Port 5000 is occupied",
            "Malformed JSON",
            "Git reports a conflict",
            "A save fails",
            "does not sync data automatically",
            "no built-in bulk import",
            "id=\"settings\"",
            "id=\"help\"",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected.casefold(), page.casefold())

        for target in (
            'href="/runbooks"',
            'href="/categories"',
            'href="/runbooks/new"',
            'href="/settings-help#settings"',
            'href="/settings-help#help"',
        ):
            with self.subTest(target=target):
                self.assertIn(target, page)

    def test_settings_and_help_navigation_links_are_available_on_app_pages(self):
        record = valid_runbook("settings-navigation")
        self.write_runbook(record)
        pages = (
            self.client.get("/"),
            self.client.get("/runbooks"),
            self.client.get("/categories"),
            self.client.get("/runbooks/new"),
            self.client.get("/runbooks/settings-navigation"),
        )

        for response in pages:
            with self.subTest(path=response.request.path):
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'href="/settings-help#settings"', response.data)
                self.assertIn(b'href="/settings-help#help"', response.data)

    def test_create_form_renders_fields_dynamic_steps_and_optional_sections(self):
        response = self.client.get(
            "/runbooks/new?return_to=%2F&results_url=%2Frunbooks%3Fq%3Ddisk"
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for field in (
            'id="title"',
            'id="category"',
            'id="technologies"',
            'id="environment"',
            'id="severity"',
            'id="symptoms"',
            'id="error-messages"',
            'id="root-cause-status"',
            'id="root-cause-details"',
            'data-step-list="investigation_steps"',
            'data-step-list="resolution_steps"',
            'id="verification-steps"',
            'id="rollback-steps"',
            'id="prevention"',
            'id="tags"',
            "Preview before saving",
            "Save runbook",
            "Cancel",
        ):
            with self.subTest(field=field):
                self.assertIn(field, page)
        self.assertIn('data-results-url="/runbooks?q=disk"', page)
        self.assertEqual(self.client.get("/runbooks/new?return_to=https%3A%2F%2Fevil.invalid").status_code, 200)
        self.assertIn(b'href="/runbooks"', self.client.get("/runbooks/new?return_to=https%3A%2F%2Fevil.invalid").data)
        self.assertFalse(self.runbooks_directory.exists())

    def test_edit_form_loads_existing_runbook_and_keeps_cancel_context(self):
        record = valid_runbook("form-edit")
        record["summary"] = "Preserve the saved summary."
        record["commands"] = ["inspect --safe"]
        record["investigation_steps"] = [{
            "description": "Inspect status.",
            "command": "status",
            "expected_result": "Healthy.",
            "notes": "No changes.",
        }]
        self.write_runbook(record)

        response = self.client.get(
            "/runbooks/form-edit/edit?return_to=%2Frunbooks%2Fform-edit"
            "%3Freturn_to%3D%252Frunbooks%253Fq%253Dtest"
            "&results_url=%2Frunbooks%3Fq%3Dtest"
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="initial-runbook"', page)
        self.assertIn("Preserve the saved summary.", page)
        self.assertIn("inspect --safe", page)
        self.assertIn("form-edit", page)
        self.assertIn('data-results-url="/runbooks?q=test"', page)

    def test_edit_form_missing_runbook_returns_not_found(self):
        response = self.client.get("/runbooks/missing/edit")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Runbook unavailable", response.data)
        self.assertIn(b"not found", response.data)

    def test_detail_page_renders_all_sections_structured_steps_and_multiline_commands(self):
        record = valid_runbook()
        record.update({
            "symptoms": ["Disk pressure symptom"],
            "error_messages": ["No space left on device"],
            "prerequisites": ["Confirm the affected mount."],
            "investigation_steps": [{
                "description": "Inspect filesystem usage.",
                "command": "df -h\nfind /var/log -type f",
                "expected_result": "The pressured mount is identified.",
                "notes": "Do not delete files before reviewing ownership.",
            }],
            "commands": ["printf 'line one\\nline two'"],
            "resolution_steps": [{
                "description": "Rotate the verified log.",
                "command": "logrotate -f /etc/logrotate.conf",
                "expected_result": "Free space is recovered.",
                "notes": "Use the approved retention policy.",
            }],
            "verification_steps": ["Confirm the service is healthy."],
            "rollback_steps": ["Restore retained data from backup."],
            "prevention": ["Alert on filesystem capacity."],
            "tags": ["disk"],
        })
        self.write_runbook(record)

        response = self.client.get(f"/runbooks/{record['id']}")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        for content in (
            "Test runbook",
            "Testing",
            "Python",
            "Local test environment",
            "medium",
            "Disk pressure symptom",
            "No space left on device",
            "Root cause",
            "suspected",
            "A test cause.",
            "Confirm the affected mount.",
            "Investigation steps",
            "Inspect filesystem usage.",
            "df -h\nfind /var/log -type f",
            "The pressured mount is identified.",
            "Do not delete files before reviewing ownership.",
            "Commands",
            "Resolution steps",
            "Rotate the verified log.",
            "Verification steps",
            "Rollback steps",
            "Prevention",
            "#disk",
            "Copy command",
            "Edit",
            "Delete",
            "Back to results",
        ):
            with self.subTest(content=content):
                self.assertIn(content, page)
        self.assertIn(b"line one\\nline two", response.data)

    def test_detail_page_escapes_runbook_content_and_keeps_safe_return_context(self):
        record = valid_runbook()
        record.update({
            "title": "<script>alert('title')</script>",
            "symptoms": ["<img src=x onerror=alert(1)>"],
            "investigation_steps": [{
                "description": "<b>inspect</b>",
                "command": "echo '<script>alert(1)</script>'",
                "expected_result": "<svg onload=alert(1)>",
                "notes": "<iframe src=javascript:alert(1)>",
            }],
        })
        self.write_runbook(record)

        response = self.client.get(
            f"/runbooks/{record['id']}?return_to=%2Frunbooks%3Fq%3Ddisk%26severity%3Dhigh"
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;script&gt;alert(&#39;title&#39;)&lt;/script&gt;", page)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page)
        self.assertIn("echo &#39;&lt;script&gt;alert(1)&lt;/script&gt;&#39;", page)
        self.assertIn('href="/runbooks?q=disk&amp;severity=high"', page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<img src=x onerror", page)
        self.assertNotIn("<iframe src=javascript:alert(1)>", page)

        external_return = self.client.get(
            f"/runbooks/{record['id']}?return_to=https%3A%2F%2Fexample.invalid"
        )
        self.assertIn(b'href="/runbooks"', external_return.data)

    def test_detail_page_returns_a_not_found_page_for_unknown_and_invalid_ids(self):
        missing = self.client.get("/runbooks/missing-runbook")
        invalid = self.client.get("/runbooks/%2E%2E")

        self.assertEqual(missing.status_code, 404)
        self.assertIn(b"Runbook not found", missing.data)
        self.assertIn(b"Back to results", missing.data)
        self.assertEqual(invalid.status_code, 404)
        self.assertIn(b"Runbook not found", invalid.data)

    def test_listing_page_handles_empty_and_malformed_data(self):
        self.assertEqual(self.client.get("/runbooks").status_code, 200)
        self.runbooks_directory.mkdir(parents=True)
        (self.runbooks_directory / "bad.json").write_text("{", encoding="utf-8")

        api_response = self.client.get("/api/runbooks")
        listing = self.client.get("/runbooks")
        self.assertEqual(api_response.status_code, 500)
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"Runbooks could not be loaded", listing.data)

    def test_missing_directory_lists_empty_collection(self):
        response = self.client.get("/api/runbooks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 0)
        self.assertEqual(response.get_json()["total"], 0)
        self.assertEqual(response.get_json()["runbooks"], [])

    def test_missing_runbook_returns_404(self):
        response = self.client.get("/api/runbooks/not-found")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"])

    def test_malformed_json_is_reported_as_storage_error(self):
        self.runbooks_directory.mkdir(parents=True)
        (self.runbooks_directory / "broken.json").write_text("{", encoding="utf-8")

        response = self.client.get("/api/runbooks")
        self.assertEqual(response.status_code, 500)
        self.assertIn("record fields", response.get_json()["error"])
        self.assertNotIn(str(self.runbooks_directory), response.get_json()["error"])

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Runbook data unavailable", dashboard.data)
        self.assertIn(b"Unavailable", dashboard.data)
        self.assertNotIn(str(self.runbooks_directory).encode(), dashboard.data)

    def test_invalid_stored_schema_is_reported(self):
        self.write_runbook({"id": "invalid-schema"})

        response = self.client.get("/api/runbooks")
        self.assertEqual(response.status_code, 500)
        self.assertIn("record fields", response.get_json()["error"])

    def test_filename_must_match_the_validated_runbook_id(self):
        self.write_runbook(valid_runbook(), filename="..unsafe.json")

        response = self.client.get("/api/runbooks")
        self.assertEqual(response.status_code, 500)
        self.assertIn("record fields", response.get_json()["error"])

    def test_unreadable_file_is_reported(self):
        self.write_runbook(valid_runbook())
        with patch.object(Path, "read_text", side_effect=PermissionError):
            response = self.client.get("/api/runbooks")

        self.assertEqual(response.status_code, 500)
        self.assertIn("file permissions", response.get_json()["error"])
        self.assertNotIn(str(self.runbooks_directory), response.get_json()["error"])

    def test_invalid_json_and_schema_are_rejected(self):
        malformed = self.client.post(
            "/api/runbooks",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(malformed.status_code, 400)

        invalid = valid_runbook()
        invalid.pop("severity")
        response = self.client.post("/api/runbooks", json=invalid)
        self.assertEqual(response.status_code, 400)
        self.assertIn("severity", response.get_json()["error"])

    def test_invalid_structured_steps_are_rejected(self):
        missing_description = valid_runbook("missing-description")
        missing_description["investigation_steps"] = [{
            "command": "inspect",
        }]
        wrong_field_type = valid_runbook("wrong-command-type")
        wrong_field_type["resolution_steps"] = [{
            "description": "Apply a resolution.",
            "command": ["not", "a", "string"],
        }]

        for record in (missing_description, wrong_field_type):
            with self.subTest(runbook_id=record["id"]):
                response = self.client.post("/api/runbooks", json=record)
                self.assertEqual(response.status_code, 400)

    def test_duplicate_id_returns_conflict_without_overwriting(self):
        original = valid_runbook()
        self.write_runbook(original)
        changed = valid_runbook()
        changed["title"] = "Must not replace the existing runbook"

        response = self.client.post("/api/runbooks", json=changed)
        self.assertEqual(response.status_code, 409)
        stored = json.loads(
            (self.runbooks_directory / "test-runbook.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(stored["title"], original["title"])

    def test_unsafe_ids_are_rejected_without_path_access(self):
        response = self.client.post(
            "/api/runbooks",
            json=valid_runbook("../outside"),
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.get("/api/runbooks/%2E%2E")
        self.assertIn(response.status_code, (400, 404))
        self.assertFalse((self.runbooks_directory.parent / "outside.json").exists())

    def test_create_persists_json_and_returns_location(self):
        record = valid_runbook("created-runbook")
        response = self.client.post("/api/runbooks", json=record)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.headers["Location"], "/api/runbooks/created-runbook")
        path = self.runbooks_directory / "created-runbook.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record)
        self.assertEqual(
            self.client.get("/api/runbooks/created-runbook").status_code,
            200,
        )
        restarted_client = app.app.test_client()
        retrieved = restarted_client.get("/api/runbooks/created-runbook")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(
            retrieved.get_json()["runbook"]["title"],
            record["title"],
        )
        self.assertEqual(
            restarted_client.get("/api/runbooks").get_json()["count"],
            1,
        )

    def test_update_runbook_persists_valid_changes_and_rejects_id_changes(self):
        original = valid_runbook("editable")
        self.write_runbook(original)
        changed = valid_runbook("editable")
        changed["title"] = "Updated title"
        changed["investigation_steps"] = [{
            "description": "Inspect the system.",
            "command": "status --verbose",
            "expected_result": "System status is healthy.",
            "notes": "Do not execute additional changes.",
        }]

        response = self.client.put("/api/runbooks/editable", json=changed)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["runbook"]["title"], "Updated title")
        persisted = json.loads(
            (self.runbooks_directory / "editable.json").read_text(encoding="utf-8")
        )
        self.assertEqual(persisted["investigation_steps"], changed["investigation_steps"])
        self.assertGreaterEqual(
            datetime.fromisoformat(persisted["updated_at"]),
            datetime.fromisoformat(changed["updated_at"]),
        )
        self.assertEqual(
            self.client.get("/runbooks/editable").status_code,
            200,
        )

        changed["id"] = "different-id"
        mismatch = self.client.put("/api/runbooks/editable", json=changed)
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(
            json.loads(
                (self.runbooks_directory / "editable.json").read_text(encoding="utf-8")
            )["id"],
            "editable",
        )

    def test_update_missing_and_failed_update_leave_existing_file_unchanged(self):
        original = valid_runbook("update-safe")
        path = self.write_runbook(original)
        changed = valid_runbook("update-safe")
        changed["title"] = "Must not replace when write fails"

        self.assertEqual(
            self.client.put("/api/runbooks/no-such-id", json=valid_runbook("no-such-id")).status_code,
            404,
        )
        with patch("runbook_store.os.replace", side_effect=OSError("simulated")):
            failed = self.client.put("/api/runbooks/update-safe", json=changed)

        self.assertEqual(failed.status_code, 500)
        self.assertIn("existing data was preserved", failed.get_json()["error"])
        self.assertNotIn(str(self.runbooks_directory), failed.get_json()["error"])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)
        self.assertEqual(list(self.runbooks_directory.glob("*.tmp")), [])

    def test_delete_runbook_removes_only_requested_record(self):
        target = valid_runbook("delete-me")
        other = valid_runbook("keep-me")
        self.write_runbook(target)
        self.write_runbook(other)

        response = self.client.delete("/api/runbooks/delete-me")
        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.runbooks_directory / "delete-me.json").exists())
        self.assertTrue((self.runbooks_directory / "keep-me.json").exists())
        self.assertEqual(
            self.client.delete("/api/runbooks/delete-me").status_code,
            404,
        )

    def test_delete_rejects_invalid_json_and_preserves_corrupt_record(self):
        path = self.runbooks_directory / "corrupt.json"
        self.runbooks_directory.mkdir(parents=True)
        path.write_text("{", encoding="utf-8")

        response = self.client.delete("/api/runbooks/corrupt")

        self.assertEqual(response.status_code, 500)
        self.assertIn("could not be deleted", response.get_json()["error"])
        self.assertNotIn(str(self.runbooks_directory), response.get_json()["error"])
        self.assertEqual(path.read_text(encoding="utf-8"), "{")

    def test_failed_delete_reports_safe_error_and_preserves_record(self):
        path = self.write_runbook(valid_runbook("delete-failure"))

        with patch.object(Path, "unlink", side_effect=PermissionError("private path")):
            response = self.client.delete("/api/runbooks/delete-failure")

        self.assertEqual(response.status_code, 500)
        self.assertIn("file permissions", response.get_json()["error"])
        self.assertNotIn(str(self.runbooks_directory), response.get_json()["error"])
        self.assertNotIn("private path", response.get_json()["error"])
        self.assertTrue(path.exists())

    def test_delete_cannot_remove_a_file_outside_the_runbook_directory(self):
        outside_file = self.runbooks_directory.parent / "outside.json"
        outside_file.write_text("leave unchanged", encoding="utf-8")

        response = self.client.delete("/api/runbooks/%2E%2E%2Foutside")

        self.assertIn(response.status_code, (400, 404))
        self.assertEqual(outside_file.read_text(encoding="utf-8"), "leave unchanged")

    def test_failed_atomic_link_leaves_no_partial_runbook(self):
        record = valid_runbook("failed-write")
        with patch("runbook_store.os.link", side_effect=OSError("simulated")):
            response = self.client.post("/api/runbooks", json=record)

        self.assertEqual(response.status_code, 500)
        self.assertFalse((self.runbooks_directory / "failed-write.json").exists())
        self.assertEqual(list(self.runbooks_directory.glob("*.tmp")), [])

    def test_sample_runbooks_follow_schema_and_have_expected_topics(self):
        records = runbook_store.list_runbooks(runbook_store.RUNBOOKS_DIR)
        titles = {record["title"] for record in records}
        self.assertGreaterEqual(len(records), 3)
        self.assertTrue(any("EC2" in title for title in titles))
        self.assertTrue(any("Jenkins" in title for title in titles))
        self.assertTrue(any("Kubernetes" in title for title in titles))


if __name__ == "__main__":
    unittest.main()
