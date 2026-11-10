# PyPI and TestPyPI: trusted publisher setup

The publish workflow (`.github/workflows/pypi-publish.yml`) uses PyPI Trusted
Publishing, so no API token is created or stored. The only thing needed is a
one-time setup on each site, by an account owner.

TestPyPI and PyPI are separate sites with separate accounts. Do each in turn.

## Values to enter

Both names, `sashiny`, are currently free on both sites (checked 2026-11-10).
Because the project does not exist yet, use a **pending** publisher.

| Field | TestPyPI | PyPI |
|---|---|---|
| Site | <https://test.pypi.org/manage/account/publishing/> | <https://pypi.org/manage/account/publishing/> |
| PyPI project name | `sashiny` | `sashiny` |
| Owner | `procogia` | `procogia` |
| Repository name | `SAShiny` | `SAShiny` |
| Workflow name | `pypi-publish.yml` | `pypi-publish.yml` |
| Environment name | `testpypi` | `pypi` |

The owner is `procogia`, not `meharpsingh`. The repository was transferred and
PyPI matches the exact owner and repository name.

## Steps

1. Sign in to test.pypi.org (create an account and enable 2FA if needed).
2. Open the publishing page above and add a pending publisher with the TestPyPI
   column values.
3. Run the rehearsal:

   ```sh
   gh workflow run pypi-publish.yml --repo procogia/SAShiny -f target=testpypi
   ```

4. Check it installs from a clean environment:

   ```sh
   uv venv /tmp/t && uv pip install --python /tmp/t \
     --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ sashiny
   /tmp/t/bin/python -c "import sashiny; print(sashiny.__version__)"
   ```

5. Repeat steps 1-2 on pypi.org with the PyPI column values.
6. Publish for real, either by creating a GitHub release (the workflow runs on
   `release: published`) or by running it manually with `-f target=pypi`.

## Notes

- Versions cannot be re-uploaded. If a TestPyPI upload needs a fix, bump the
  version in `Python/src/sashiny/__init__.py` first.
- Do not create or commit API tokens. If a token is ever used instead, store it
  as a GitHub secret, never in the repo.
