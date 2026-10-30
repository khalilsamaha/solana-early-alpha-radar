# Development and release workflow

## Agreed batch rhythm

The user-approved workflow update supersedes the per-increment PR cadence
below. Make small local commits with relevant local tests and source hygiene;
publish pinned development heads when Kali acceptance is needed. Build related
increments on their reviewed predecessor, recording that lineage. Consolidate
about three successful increments into one PR, run the full repository checks and
CI for that batch, and review before merging. A required host check remains an
acceptance gate. Neither publishing a branch nor merging deploys to Kali.

The numbered workflow below describes the consolidated release cycle.

1. Branch from the current `main` and target `main` with a short-lived branch for one change. Record the hypothesis and success/failure measures before changing signal rules.
2. Run `bash scripts/check.sh` from the repository root. Tests use temporary databases, mocked external providers and local HTTP servers.
3. Open a pull request describing behavior, tests, evidence compatibility and rollback. Separate fixes to measurement from changes to signal selection.
4. Review CI and the diff before merging. A merge is not a deployment.
5. Prepare an explicit release and host deployment procedure. Back up and verify databases before a data-affecting change. Keep configuration outside Git.

`SOURCE-REVIEW-MANIFEST.json` is an immutable record of the initial deployed snapshot. `release-manifest.json` records this import's component versions and added files. Future releases get their own manifest; do not rewrite historical provenance to make a changed file appear original.

The observer and collector installers verify their component `manifest.json`. When changing either package, version and regenerate that package deliberately and test its upgrade path. Do not bypass its integrity checks.

## Existing host

The existing project is `~/apps/solana-early-alpha-radar`, with Compose and `.env` at that directory's root. This repository nests those sources in `scanner/`. Do not overlay the repository on the running directory or create a new volume by accident.

Before a later Git-based deployment, inventory the existing Compose project name, named database volume and bind mounts; preserve their identity explicitly. Test a release in an isolated directory using a copied database and disabled notifications/providers. Keep the prior image, source and migration instructions available for rollback. Never use `docker compose down -v` for this migration.

No CI deployment key, production `.env`, API credential or wallet material is needed for development. Source fixtures contain public token identifiers and synthetic data. Do not commit live quote exports or backups.

## Current quality report

The imported helper can be run against the existing installation without installing a patch:

```bash
cd ~/apps/solana-early-alpha-radar
node --env-file=.env /path/to/checkout/quality-tools/verify.mjs
bash /path/to/checkout/quality-tools/run-report.sh
```

Replace `/path/to/checkout` with the real cloned repository path. The report helper takes a bounded read-only snapshot and writes a private report on the host. GitHub cannot read the live Kali database.

## October 25 consolidation

Use [ENGINEERING-RELEASE-20261025.md](ENGINEERING-RELEASE-20261025.md) for the source-only rollout, compatible code rollback and capture-only evidence preservation. Keep historical development branches for provenance; close superseded PRs only after their exact heads are confirmed as ancestors of the consolidated main commit. Do not force-push, rewrite old manifests, reset private journals or reinstall the frozen experiment as release cleanup.
