# DevOps Runbook

A local web application for organizing personal DevOps procedures and operational notes. Runbooks are stored as individual JSON files in the project directory.

## Scope and technology

- Python and Flask provide the local web server, HTML rendering, and JSON API.
- HTML, CSS, and vanilla JavaScript provide the responsive user interface.
- Flask is the only direct Python dependency (`Flask==3.1.2`).
- There is no database, authentication, external API, AI service, frontend framework, Node.js runtime, or build step.

The application is intended for one person using a local development server. Data remains on this computer unless the owner manually copies or deliberately commits it elsewhere.

## Prerequisites

- Python 3.9 or newer.
- Git only if you want to use the optional source-control workflow.
- PowerShell commands below are for Windows. On other platforms, use the equivalent virtual-environment activation and path syntax.

## Installation and startup

From the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell prevents virtual-environment activation, invoke its Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The development server listens on `127.0.0.1:5000`. Open <http://127.0.0.1:5000/> in a browser. Press **Ctrl+C** in the server terminal to stop it. The built-in Flask server/debugger is for local development only; do not expose it to a network or use it as a production server.

## Features

- **Dashboard:** data-derived runbook and technology counts, recently updated records, global quick search, technology/category shortcuts, and a persistent light/dark theme toggle.
- **All Runbooks:** API-backed search across titles, symptoms, errors, investigation/resolution steps, commands, and tags; combinable technology, category, environment, and severity filters; title and updated-date sorting; result counts and empty/error states.
- **Runbook details:** metadata and all runbook sections, display-only commands with copy feedback, edit/delete actions, and a return link that preserves listing context.
- **Create and edit:** one form for both workflows, field validation, add/remove/reorder investigation and resolution steps, collapsible optional sections, JSON preview, save feedback, and unsaved-change warnings.
- **Delete:** explicit confirmation showing the runbook title; cancel leaves data unchanged.
- **Categories and Technologies:** groups and counts are computed from stored records; selecting a group opens the existing filtered listing.
- **Settings and Help:** application/version and local-storage information, schema guidance, startup, Git, backup/restore, and troubleshooting instructions.
- **Responsive navigation and layouts:** desktop, tablet, and mobile layouts; keyboard-accessible controls and labels.

Runbook content is displayed as text. Commands are never executed by the application. Template autoescaping and DOM text APIs are used for user-entered content.

## Architecture and project structure

```text
.
├── .gitignore
├── README.md
├── app.py                    # Flask page routes and JSON API
├── requirements.txt          # Pinned Flask dependency
├── runbook_store.py          # Validation and local JSON persistence
├── data/
│   └── runbooks/              # One <id>.json file per runbook
├── docs/
├── static/
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       ├── runbooks.js
│       ├── runbook-detail.js
│       └── runbook-form.js
├── templates/
│   ├── index.html
│   ├── runbooks.html
│   ├── categories.html
│   ├── runbook-detail.html
│   ├── runbook-form.html
│   └── settings-help.html
└── tests/
    └── test_api.py
```

The browser calls the Flask API for listing and detail data. Flask delegates JSON validation and file operations to `runbook_store.py`; no records are held only in browser memory.

## JSON schema and storage

Records are UTF-8 JSON files under `data/runbooks/`, named `<id>.json`. The ID must match the file stem and contain 1–64 lowercase letters, digits, or hyphens, starting with a letter or digit. API requests accept IDs, not filesystem paths.

Every record requires:

| Field(s) | Type and validation |
| --- | --- |
| `id` | Stable safe ID used as the filename stem |
| `title`, `category`, `environment` | Non-empty strings |
| `technologies`, `symptoms`, `error_messages`, `prerequisites`, `verification_steps`, `rollback_steps`, `prevention`, `tags` | Lists of non-empty strings; lists may be empty |
| `investigation_steps`, `resolution_steps` | Lists of non-empty strings or step objects |
| Step object | Required non-empty `description`; optional string `command`, `expected_result`, and `notes` |
| `severity` | `critical`, `high`, `medium`, or `low` |
| `root_cause` | Object containing exactly `status` (`unknown`, `suspected`, or `confirmed`) and string `details` |
| `created_at`, `updated_at` | ISO 8601 datetime strings with timezone offsets; `updated_at` cannot precede `created_at` |

`summary` and `commands` are optional; when present they must be a string and a list of non-empty strings, respectively. Other additional top-level fields are retained. The API validates required fields, types, timestamps, IDs, step objects, and stored filename/ID consistency.

Writes are serialized within the application process and staged in a temporary file in the runbook directory before an atomic create or replacement. Failed writes clean up temporary files and preserve prior records. Malformed or unreadable stored data produces an explicit error rather than a misleading successful response. The three generic sample records cover AWS/EC2 disk usage, Jenkins build failure, and Kubernetes pod failure; they contain no company data or credentials.

## API overview

| Method and path | Success | Behavior |
| --- | --- | --- |
| `GET /api/runbooks` | `200` | List records; supports `q`, `technology`, `category`, `environment`, `severity`, and `sort=updated\|title` query parameters |
| `GET /api/runbooks/<id>` | `200` | Retrieve one record |
| `POST /api/runbooks` | `201` | Validate and create a record; returns a `Location` header |
| `PUT /api/runbooks/<id>` | `200` | Validate and update the matching record; ID stays stable and `updated_at` advances |
| `DELETE /api/runbooks/<id>` | `200` | Delete the matching record |

Errors return JSON such as `{"error": "..."}`. Invalid JSON/schema or IDs return `400`; unsupported content types return `415`; duplicate IDs return `409`; missing records return `404`; invalid or inaccessible stored data and storage failures return `500`. User-facing storage errors do not expose filesystem paths or stack traces.

Page routes include `/`, `/runbooks`, `/categories`, `/settings-help`, `/runbooks/new`, `/runbooks/<id>`, and `/runbooks/<id>/edit`.

## Tests and quality checks

Activate the project virtual environment and run:

```powershell
python -m unittest discover -s tests -v
```

Or run without activation:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests use temporary runbook directories and do not modify the included sample records. The suite covers API CRUD and errors, schema validation, malformed/unreadable data, safe filenames and deletion, atomic-write failures, search/filter/sort behavior, page routes, escaping, categories, help content, static assets, and sample data.

### Final integration results (2026-10-11)

- Full suite in the project environment — **41 tests passed** (`unittest discover`; 0 failures).
- Full suite in a clean isolated project copy with a newly created virtual environment — **41 tests passed**. Installing `requirements.txt` installed Flask 3.1.2 successfully.
- Startup using the documented direct-venv command (`.venv\Scripts\python.exe app.py`) — passed in the clean copy. The homepage, page routes, static assets, API, and all three sample records responded as expected.
- Restart persistence — created a temporary runbook through the API, stopped and restarted the clean-copy Flask process, retrieved the record successfully, then deleted the temporary record.
- Browser UI — dashboard search, theme toggle, listing search, technology filter, and filter reset worked; no page or console errors were observed during these interactions.
- Responsive browser check — dashboard, listing, categories, Settings/Help, create form, detail, and edit routes had no horizontal document overflow at **1440, 768, 390, and 320px**.
- `node --check` on the four JavaScript assets — passed. Node is an optional QA tool and is not needed to install or run the application.
- Pylance workspace diagnostics — no issues reported.
- Git ignore checks — virtual environments, bytecode/cache, `.env` files, coverage output, and `*.tmp` files are ignored; runbook JSON remains trackable for intentional manual Git workflows.

A fresh Git clone was not tested: this working project has no project-specific commit history or configured remote URL. The clean install/start check used an isolated copy of the project files, not `git clone`.

## Git workflow

No repository URL is configured by this project. Substitute your repository URL and directory:

```powershell
git clone <repository-url>
Set-Location <project-folder>
git pull
git status
git diff
git diff -- data/runbooks
git add README.md app.py runbook_store.py requirements.txt templates static tests data/runbooks
git diff --cached
git commit -m "Describe the runbook changes"
git push
```

Review changes before staging. Runbook files may contain operationally sensitive information; do not put credentials or secrets in records, and only commit data to a repository whose sharing policy is appropriate. Git operations are manual. The application does not synchronize records automatically.

## Backup and restore

Run these PowerShell commands from the project directory. The backup is outside `data/runbooks/`:

```powershell
$backup = ".\backup\runbooks-$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Path $backup -Force
Copy-Item -Path .\data\runbooks\*.json -Destination $backup
```

To restore selected backup files, first stop the application and copy the current data directory to another backup. Then verify the backup path and files before overwriting matching records:

```powershell
Copy-Item -Path .\backup\runbooks-YYYYMMDD-HHMMSS\*.json `
  -Destination .\data\runbooks\ -Force
```

Reload the application and verify the runbook list after restoring. There is no built-in bulk import, export, backup, or restore operation.

## Known limitations and troubleshooting

- Storage is local JSON on one device. There is no database, automatic synchronization, multi-user service, or built-in backup/restore.
- Flask's built-in server and debugger are for local development only.
- The project currently provides no Git remote URL; Git commands above use a placeholder.
- **Flask is not installed:** activate `.venv` and run `python -m pip install -r requirements.txt`.
- **Port 5000 is occupied:** stop the other local process or close its server, then retry `python app.py`.
- **Malformed JSON or invalid runbook:** make a backup before manual repair; validate JSON syntax and required schema fields, or restore a known-good file.
- **Save fails:** keep the form open to retain entered values; check the displayed error, record validation, duplicate ID, and write permissions. Failed updates preserve the previous record.
- **Git conflict:** inspect `git status` and `git diff`, resolve each conflict without discarding needed changes, validate conflicted JSON, then stage and commit the resolution.
