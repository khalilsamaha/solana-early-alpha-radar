# Local-first engineering rhythm

## User-confirmed workflow — November 8

Development commits and branches may be pushed to GitHub whenever needed to
retrieve and test an implementation on Kali. These are development pushes, not
releases or gate acceptance, and do not require a separate publication question.
Use immutable commits in complete fetch/checkout/test commands. The running
project is `/home/redeye/apps/solana-early-alpha-radar`; development tools remain
in `/home/redeye/apps/solana-radar-dev` without overlaying the running installation.

Review uploaded Kali evidence and fix failures until a complete engineering phase
or gate is locally accepted. Only then consolidate the batch and initiate its
PR/full-check/CI/merge cycle. Do not create per-increment PRs or manually trigger CI
before that acceptance. Required merge checks and post-merge verification remain
required during consolidation. Neither a development push nor consolidation
constitutes deployment or operational-execution authorization. A failed host gate
cannot be cleared by a faster assistant-host run.

The earlier general batch guidance below applies subject to this gate ordering.

1. Make focused local changes and run relevant offline tests. Commit each coherent
   successful change locally; a commit does not require a new PR or CI run.
2. Batch roughly two or three related tasks into one published update, using the
   existing PR when its scope still fits. Correctness and reviewability matter
   more than an exact commit count.
3. Before publishing a release candidate, run `bash scripts/check.sh all` locally,
   plus any scale or integration exercise needed by the change. Record failures
   and limitations; passing synthetic tests does not prove host performance.
4. Run the full GitHub checks on the final PR head before merge or deployment.
   The workflow runs for pull requests, pushes to main and manual dispatch. A
   feature-branch push no longer creates an additional duplicate push run.
5. Review the final diff, preserve recovery instructions and deploy only a tested
   immutable commit. Keep research and production evidence separate.

Draft PR updates still trigger PR checks. Batch updates locally instead of relying
on draft status or skip directives to suppress required checks. Main-branch checks
remain a post-merge verification. Production changes and evidence-only tools have
separate deployment decisions.
