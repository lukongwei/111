# Repository Maintenance

## Local checks

Run these checks before committing changes:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q CORE DASHBOARD tests
git diff --check
```

The GitHub Actions workflow runs the same checks on Python 3.11, 3.12, and 3.13.

## Runtime state

The SQLite index under `DASHBOARD/data/` is a local runtime artifact. It is intentionally
ignored by Git, including SQLite WAL, SHM, and journal sidecars. Recreate it by running the
workspace indexing commands against registered projects.

Do not commit `.env` files, credentials, tokens, private keys, or experimental logs containing
local paths or user data. Keep reproducible experiment definitions and sanitized summaries in Git;
keep generated runtime evidence local unless it has been reviewed for publication.

## Architecture boundaries

Changes must preserve the separation between Index, Gateway, Context, Task, Log, Git, and
Semantic Layer responsibilities. Agents obtain project content through the Gateway. The Gateway
is an application boundary, not an OS sandbox; untrusted agents require separate process, OS user,
ACL, or sandbox isolation.

Semantic Mathematical Problems remain Human-owned. Semantic relations require rationale and
Trigger/Gap/Response fields, and semantic history is append-only. Unimplemented capabilities must
remain explicitly marked as TODO in code or documentation.

## Release checklist

- Review `git status` and `git diff` for unrelated or sensitive files.
- Confirm the runtime database and sidecars are ignored.
- Run the local checks above.
- Update `PROJECT.md`, relevant design documents, and tests with behavior changes.
- Use a feature branch and require passing CI before merging to `main`.
