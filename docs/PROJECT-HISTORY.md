# Solana Early Alpha Radar — project history and current position

Updated: 11 October 2026. Operational dates below use the supplied logs; report filenames use UTC. The host uses Europe/Amsterdam (UTC+2 during this period).

## Purpose and scope

The project began as a way to discover newly appearing Solana tokens early, assess their market activity and available security information, display candidates, and send useful Telegram alerts. The longer-term question is whether those signals can support a repeatable strategy in a market where price moves and collapses can happen within minutes.

Our objective evolved from “find tokens early” into “measure whether an early signal has a realistically available entry and exit.” Those are different milestones. A visible spike, high score, successful API response, or favorable paper price is not sufficient evidence of an executable advantage.

The system currently performs discovery, scoring, notifications, paper observations, experimental shadow comparisons, and walletless route quoting. It does not buy or sell tokens. No wallet private key or funded trading account is required by the quote observer.

This history is reconstructed from the supplied terminal outputs, reviewed source, reports and GitHub development. It covers the earliest available setup through the latest development. Exact dates or version assignments absent from that evidence are not invented. An installed component in an old log is not a guarantee that its service is healthy today.

## Architecture and operating environment

| Part | Role and established configuration |
| --- | --- |
| Host | Kali Linux installed directly on an x86_64 machine, intended to remain connected and running 24/7 |
| Production directory | `~/apps/solana-early-alpha-radar` |
| Development checkout | `~/apps/solana-radar-dev` |
| Runtime | Node.js 24; Docker and Docker Compose |
| Scanner container | Compose service `radar`, restart policy `unless-stopped`, reported 512 MiB memory limit |
| Dashboard | Localhost binding `127.0.0.1:8787`, authenticated API, readiness endpoint |
| Discovery and enrichment | PumpPortal, DEX Screener, Jupiter and Helius, with separate rate limits and data-quality states |
| Scanner persistence | SQLite candidates, events, outbox and key/value state |
| Notifications | Telegram alerts and separate external health/backup monitoring |
| Backups | Verified local SQLite snapshots and compressed Backblaze B2 copies |
| Research tools | Offline/read-only collectors and paper scenario analysis; a 30-minute systemd timer was installed |
| Quote observer | Separate systemd service and ledger, walletless hypothetical fixed-quantity buy/sell quotes |
| GitHub | Private repository `khalilsamaha/solana-early-alpha-radar`; source tests and review branches |

The original host project remains the deployment location. Running Compose from the repository's `scanner/` directory could select a different Compose project or database volume. The guarded installers therefore copy approved source changes into the existing host project.

## 1. Initial hosting and connectivity — 29–30 September

You initially considered a VPS/OVHcloud but already had an always-on Kali machine. We used it for the initial deployment. The reported machine architecture was x86_64, with Node 24, Docker 28.5.2 and Compose 2.29.2.

The container became healthy and the dashboard opened successfully. Live doctor checks confirmed configured PumpPortal, Jupiter and Helius access, DEX market responses and Helius security fields. Telegram was initially unconfigured, and notification sending was initially off.

PumpPortal connected but rejected a subscription with the message “Minimum balance not met for PumpSwap websocket data.” The integration was adjusted; later logs showed a connection without that rejection and the dashboard showed `pumpportal:create` observations. This established new-token discovery without treating a connection alone as proof of a successful subscription. It did not establish comprehensive coverage of every Solana launch venue.

Telegram delivery was subsequently confirmed, including a “fresh market observations are arriving” message. Paper alerts and their delivery state became visible in the system.

## 2. Host monitoring, restart behavior and recovery — 30 September

Docker and containerd were enabled at boot. Container inspection confirmed `unless-stopped`. A host heartbeat script was configured with a private Healthchecks URL and scheduled through cron.

You tested the external check: a DOWN event and email arrived, followed by a green recovery. This was an actual notification-path test, not just configuration inspection. The heartbeat URL and other credentials remain outside source control.

An initial SQLite backup was copied from the container and checked. The supplied verification reported:

- SQLite integrity: OK.
- 1,000 stored candidates and 22,226 events.
- A readable host backup with restricted permissions.

A daily systemd backup timer was then installed for roughly 03:15–03:20 host time, with missed-run catch-up. A manual service run completed successfully and reported the row counts and archive size.

Supabase and other free services were considered. The implemented off-host backup destination was Backblaze B2, not a Supabase database migration.

## 3. Backblaze B2 and restore verification — 30 September onward

The Kali package repository did not provide an `rclone` installation candidate at the time. A working rclone binary was subsequently available at `/usr/local/bin/rclone`.

A bucket-restricted application key was configured. The initial command still contained the placeholder `YOUR_BUCKET_NAME`; using the actual configured bucket resolved access. The rclone configuration was kept private under `/etc/solana-radar`.

The cloud backup workflow then:

1. Produced a verified local SQLite snapshot.
2. Compressed and uploaded it to B2.
3. Downloaded the uploaded archive.
4. Compared SHA-256 and checked restored SQLite integrity.
5. Recorded completion and acknowledged the backup monitor.

A restore drill also passed: dashboard startup, authenticated API access, HTML response, unchanged notification outbox, and cleanup of temporary test files were verified against a saved backup.

Later logs confirmed scheduled local and cloud backup success. These checks established recovery for the scanner database. They did **not** establish backup/restore protection for the quote observer's later, separate ledger; that remains an explicit open task.

## 4. Discovery coverage and scheduling — 30 September

Early diagnostics exposed a significant coverage problem: among 1,000 retained candidates, 919 had never been attempted and only 70 had fresh market data. Healthy provider connections were therefore insufficient to establish useful discovery coverage.

The scanner scheduling was improved. In the supplied v0.2.1 report:

- 969 candidates were active.
- Only one had never been attempted.
- No candidates were reported evicted before their first attempt.
- 868 had fresh market data.
- Market-attempt age was approximately 22 seconds median and 64 seconds p95.

Market polling and slower metadata/security enrichment were separated. This let market coverage improve without enriching every thin or ineligible token at maximum frequency. The initial alert score remained 72 in the supplied diagnostics.

The 1,000-candidate bound still limits the retained active set. A token absent from the current dashboard is not necessarily a token never discovered. Historical events and paper entries provide additional evidence.

## 5. Security labels, token links and historical visibility

Security fields were made more explicit: mint authority, freeze authority, token-account concentration, extensions, and data freshness. Known metadata extensions were distinguished from broadly unevaluated token behavior. These checks are limited observations, not a safety certification.

You asked about NightFloat, seen in Phantom but not the dashboard. Its mint could no longer be found, so that particular case could not be reconstructed. We did not infer its chain, launch route or missed-detection cause from its name.

Token lookup links were added to speed identification in Phantom, Jupiter and Solscan. The mint address is the authoritative lookup reference; ticker/name matching is unreliable for similarly named tokens. Historical token audits later confirmed archived alerts, exits, outcomes and snapshots for tokens no longer retained in the queue.

This work was intended to generalize across future tokens. SGI and other examples were case studies motivating improvements, not hard-coded token exceptions.

## 6. Snapshot retention, decision traces and paper outcomes — 1 October

Scanner v0.2.3 reported snapshot archiving at a routine interval of 60 seconds and a thin-market interval of 300 seconds, skipping redundant routine storage while market polling continued more frequently.

The 1 October report showed healthy providers, zero never-attempted candidates at that snapshot, 883 fresh markets and complete recorded one-hour outcomes for 331 paper entries at the time. Alert and notification totals were larger than unique paper entries because they included different event types and repeated/exit-related messages.

V0.2.4 added decision traces and more detailed outcome reporting. Unknown liquidity was explicitly represented rather than automatically equated with known low liquidity.

The results were a warning about strategy quality: in one retained sample, the one-hour median paper price change was about −95.7%, with roughly 82% of observed outcomes losing at least 50%. A historical sampled peak of 2× did not imply that an actionable exit captured that peak.

This shifted the research toward short holding periods, realistic timing and separate execution evidence rather than headline spikes.

## 7. Resource growth and backup timeout — 1–4 October

Memory and CPU were initially modest, but SQLite and block I/O grew. The database progressed from tens of MiB into hundreds of MiB and later over 1 GiB. A process-level measurement identified approximately 66 MiB written in 60 seconds during one sample. Earlier measurements had inadvertently targeted the wrong process; process names were not a reliable way to identify Node in this container.

On 3 October the daily backup service timed out after one hour. Previous success JSON files were still present, demonstrating why a stale success record cannot prove today's run succeeded.

The backup implementation was replaced with a bounded host snapshot method. The subsequent supplied run:

- Copied an approximately 1.19 GB SQLite database in about 15 seconds.
- Uploaded and verified an approximately 303 MB compressed archive.
- Completed the full service in about 3 minutes 33 seconds.
- Reported a 2.7 GB peak for the host backup service, separate from the scanner container's limit.

The next scheduled backup on 4 October also completed and verified its cloud copy. Database growth, disk writes and host-level backup resource usage remain things to monitor; these logs do not prove that every storage-growth concern is permanently solved.

## 8. Research history continuity and the move to short-duration evidence — 2–5 October

An early research snapshot showed most candidates warming up with one sample and repeated observation-gap resets. Only a small subset had usable continuous histories. Pending paper observations were receiving better coverage than the broad candidate population.

Research focus and continuity handling were improved over subsequent updates, culminating in the deployed scanner 0.2.9. Research paths kept original-pool evidence separate and exposed missing/gapped observations instead of inventing returns. Exact release attribution for every intermediate adjustment is not recoverable from the supplied logs, so those changes are grouped here.

Research tools 1.0.0 introduced bounded read-only analysis and a 30-minute timer. The tools compared fixed 60-/120-second holds and a target/stop/time scenario, initially with hypothetical 1% costs on each side and 10-second entry/exit delays. These were sampled-price models, not route quotes or fills.

The first backup analysis stopped when it reached a snapshot row limit; it published no partial report. Version 1.0.1 corrected the collector limitation. A separate scanner evidence patch increased checkpoint history from 8 to 24 samples, preserving enough evidence for delayed two-minute exits without crossing pool changes.

Research tools 1.1.0 added severe-loss records, feature availability, explanations for unresolved paths, and registered shadow comparisons. Historical data remained exploratory; validation began at a stored registration timestamp. Missing liquidity/organic/security features were not silently filled using later information.

## 9. Walletless quote observation — 5–10 October

A manual quote-check tool was introduced. A shell compatibility issue arose because Bash `read -p` syntax was run in Kali's default interactive shell; subsequent instructions favored explicit Bash blocks or direct arguments.

The quote observer then automated bounded signal-linked observations:

| Release | Main change evidenced in the project |
| --- | --- |
| 0.2.0 | Separate walletless observer, indexed signal feed, persistent cursor, fixed hypothetical quantity, buy plus four sell quote observations |
| 0.3.0 | Paced cohort reservation and safer distinction between ordinary HTTP 400 errors and global transport cooldowns |
| 0.4.0 | Independent rolling cohort budgets, no borrowing, structured bounded error evidence and preserved legacy budget usage |
| 0.5.0–0.6.0 | Further entry/exit evidence and Fast30 integration; the reviewed deployed release is 0.6.0 with three-cohort sampling |

The initial limits included one active watch, six admissions per hour, 144 per 24 hours, five requests per admission, ten-second request spacing, and seven-day evidence retention. Admission sampling evolved; historical policies must be analyzed separately rather than pooled as if random.

The observer records a hypothetical buy quote and reuses its exact token quantity for sell quotes. It performs no transaction signing, broadcasting, buying or selling. Quote failure, provider cooldown, busy state, stale signals and exhausted budgets remain explicit exclusions.

A “zero-offset” sell is delayed by request spacing; it is not an instantaneous round trip. Buy-response-relative exit clocks also differ from signal-relative paper clocks.

## 10. Memory failures and worker isolation — 9 October

You observed 44 container restarts without manual intervention. Logs showed V8 JavaScript heap exhaustion near its heap limit. Docker's `OOMKilled=false` did not contradict those logs: a process-level JavaScript heap failure is different from a container being killed by the kernel.

The statistics memory patch 1.0.0 replaced materialization of detailed statistics with lazy iteration and summaries. It preserved detailed stored evidence and existing summary semantics. After rebuilding, the supplied short verification showed zero restarts and about 120 MiB container memory.

Statistics worker 1.1.0 then moved expensive summary calculations off the scanner's main event loop. It added shared refreshes, cache age labeling, worker failure cooldown, timeout termination and explicit unavailable responses. Tests checked health responsiveness while statistics were calculated.

The supplied activation check showed zero restarts before and after a roughly 45-second observation period and approximately 103 MiB memory. This confirmed initial activation, not indefinite stability.

A contemporaneous gap audit showed substantially better continuous research paths. It preserved unavailable original-pool endpoints as unavailable.

## 11. Fast30 quality research and GitHub — 9–10 October

Research quality 1.0.0 added labels for first, repeated, changed, stale and invalid provider responses. Recent receipt time was explicitly separated from proof of fresh exchange data.

Fast30 introduced an experimental earlier signal, distinct from the existing 60-second research cohort. It required enough changed transitions and rising recent activity; a single initial observation plus one changed point could not create the required history. Unknown pump liquidity remained unknown, and security limitations remained explicit.

Fast30 initially did not alter follow-up scheduling. Its initial five-minute coverage was therefore uneven, especially for entries that did not later qualify for the older early-activity cohort.

The private GitHub repository was created on 9 October. Source was imported with provenance and hygiene checks. CI runs offline scanner, observer, research, quality and deployment tests. Production `.env`, database files, backups and credentials are excluded.

The Fast30 follow-up development at commit `a55e567a11ba8baa0f308a71061ebd4892183b8a` added bounded follow-up, timing reports and three-cohort quote sampling. User deployment was confirmed. Fast tracking has a cap of up to 12 active positions within existing focus capacity; polling/provider limits were not broadly increased.

In the 10 October afternoon report, mature five-minute coverage for post-update Fast30 entries reached 321/336 (95.5%). This improved evidence completeness, not profitability. The contemporaneous quote samples were small and had unfavorable median outcomes.

GitHub review sequence:

- PR #2: bounded Fast30 follow-up and sampling, branch `feature/fast30-followup-20261010`.
- PR #3: joined evidence and diagnostics, branch `feature/evidence-diagnostics-20261010`.
- Both remained open draft PRs at the latest review. Deployment of a pinned branch commit is separate from merging into `main`.

## 12. Joined evidence and entry hypotheses — 10 October evening

Commit `fdf7199e3391f04ae7b179aef46f2236b511ec20` introduced `fast-evidence-1` and report format 3. You deployed it at approximately 19:19 UTC / 21:19 local.

This update:

- Joined exact Fast30 entries to quote watches using database identity, entry ID, mint, pool, time and price.
- Preserved original-pool price returns and fixed-quantity route quote changes separately.
- Recorded bounded attempt diagnostics for missing checkpoints.
- Registered two independent entry hypotheses: known liquidity at least $5,000; preceding 30-second increase no greater than 50%.
- Kept selected, excluded and unknown groups, without changing signal admission or notifications.

Registration began at 19:19:44.955 UTC. The first report contained 37 forward entries. The moderate-rise group's initial positive two-minute paper mean was treated as preliminary because only one corresponding quote watch existed in that group.

## 13. Latest assessment — 11 October, 04:33 UTC / 06:33 local

The new report contained 516 Fast30 entries, of which 404 were forward entries for the registered entry hypotheses. Thirty-seven overlapped the prior report, leaving 367 additional forward entries. Overlapping exports must not be added together without deduplication.

| Independent entry comparison | Entries | Observed 120-second outcomes | Mean paper price change | Median | Missing |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prior 30-second rise ≤50% | 328 | 319 | −7.56% | −11.51% | 9 |
| Prior 30-second rise >50% | 76 | 73 | −14.36% | −24.75% | 3 |
| Known liquidity ≥$5,000 | 52 | 52 | −1.75% | −2.25% | 0 |
| Unknown liquidity | 352 | 340 | −9.91% | −15.93% | 12 |

These comparisons overlap; liquidity and momentum groups are not additive. Missing observations are excluded from numerical return averages, not counted as zero.

Among the 18 Fast30 quote watches associated with forward entry-test signals:

- At 30 seconds: mean quoted change +4.38%, median −0.04%.
- At 120 seconds: mean −9.08%, median −11.47%.
- Five changed from a positive 30-second quote result to a negative two-minute result.
- Only three were in the known-liquidity group.

The full 12-hour quote export contained 67 watches: 65 complete, one complete with failures and one running. One early-activity watch had a successful buy quote followed by four failed sell-quote requests. It remains unresolved execution evidence, not a zero return or proof of permanent unsellability.

All 44 missing forward checkpoints across 21 tokens recorded different-pool observations. At five minutes the forward sample had 379 observed outcomes, 21 missing and four pending. A different pool does not itself prove migration.

The larger sample reversed the earlier positive moderate-rise paper mean. Neither entry filter is validated for live trading. Earlier detection by itself has not demonstrated an edge.

## 14. Current development — pool evidence, timing and fixed exits

The development prepared on 11 October is `pool-timing-evidence-1`, with fixed exit protocol `fixed-short-exits-1` and report format 4. Until the user runs the deployment commands and returns verification, it is **prepared source, not a confirmed host deployment**.

It adds:

1. Eight recent received market observations per active Fast30 position, plus its first alternate-pool observation. These are bounded in memory and copied onto existing outcome events; no new per-poll database writes or provider requests are introduced.
2. Separate alternate-pool checkpoint observations. Original-pool missing outcomes remain missing; no cross-pool return is substituted.
3. Backward-only price/quote comparisons: use an original-pool response recorded before the quote request and at most 20 seconds old. The actual age is reported, with a separate indicator for observations within five seconds. No interpolation or identical-time claim is made.
4. A stored prospective fixed-exit protocol: 30 seconds as the primary comparison, 60 and 120 seconds as fixed comparators, all relative to the hypothetical buy response. Quotes requested more than five seconds late are labeled late. Failed, pending, missing and invalid exits remain explicit.
5. Additional proceeds haircuts of 0%, 1% and 3% as stress scenarios. These are not measured costs or a net execution model; quotes may already include some fees.

Historical replay is exploratory for the new exit protocol. Its forward period starts with a persisted registration created by the first new Fast30 entry after deployment. Registration survives restart. Restarted incomplete trajectories are explicitly partial/gapped.

## Current roadmap and gates

| Stage | Position | Evidence needed to move forward |
| --- | --- | --- |
| Hosting, alerts and scanner recovery | Established in supplied tests | Continue monitoring; protect and restore the separate quote ledger |
| Discovery and paper evidence | Operating, with bounded retention/focus | Maintain coverage and explicit missing/unknown states |
| Forward strategy and quote research | **Current stage** | Stable, distinct forward windows; complete failure denominators; reproducible results beyond a few winners |
| Execution engineering | Not implemented | Quote-to-transaction simulation, fee/slippage/amount caps, idempotency, reconciliation and independent stop controls |
| Small funded engineering pilot | Not ready | Tested controls, documented limits and explicit user approval of wallet/budget/actions |
| Scaling | Not planned for deployment | Evidence from the controlled pilot, operational reliability and capacity/cost assessment |

There is no evidence-based date for funded testing. A large number of paper entries alone is not a gate, and a short positive mean is not enough. Strategy evidence and execution correctness are separate requirements.

## Outstanding work and known limitations

- Verified backup and restore of the separate quote observer ledger, including its cursor/registration state.
- Sustained memory/restart monitoring after the statistics fixes; current deployment logs alone cannot prove long-run stability.
- Database/retention/write-volume monitoring and cloud storage budget review.
- Pool-transition interpretation without merging incompatible evidence.
- Underlying exchange freshness remains partly unknown even when HTTP responses are recent.
- Quote unit-price comparison is limited by absent token-decimal evidence in existing exports. Atomic token quantities must not be treated as whole tokens.
- Capacity-limited quote sampling is not random, and repeated mints/overlapping exports require careful handling.
- Current quote groups are too small for strong claims about liquidity-filtered subsets.
- Sampled target/stop models do not prove those orders could execute between observations.
- No real execution, transaction simulation or funded-wallet protection has been demonstrated.
- The project currently covers Solana integrations; a multichain expansion has not been implemented.

## Operating and development practices

1. Keep production under the existing host directory and use pinned commits for deployment.
2. Run offline tests and the guarded source installer before rebuilding.
3. Keep credentials, SQLite files, report archives and backups out of GitHub.
4. Inspect readiness, component version markers and restart counts after installation.
5. Check early completed paths for correctness; do not wait a full day to discover a broken implementation.
6. Collect forward evidence under frozen rules. Use full denominators, not only successful returns.
7. Deduplicate quote exports by source identity and sequence; use immutable entry IDs for scanner evidence.
8. Treat provider errors and unavailable outcomes as explicit unknowns.
9. Preserve rollback and restore evidence before changing storage or deployment topology.
10. Require a separate, concrete decision before enabling any real-money execution.

## Key references

- Repository: https://github.com/khalilsamaha/solana-early-alpha-radar
- Fast30 follow-up review: https://github.com/khalilsamaha/solana-early-alpha-radar/pull/2
- Joined evidence review: https://github.com/khalilsamaha/solana-early-alpha-radar/pull/3
- Deployment source commit: `fdf7199e3391f04ae7b179aef46f2236b511ec20`.
- Latest reviewed files: `radar-evidence-review-20261011T043349Z-1110888.json.gz` and `radar-auto-quotes-20261011T043349Z-1110888.json.gz`.
- Earlier comparison: the paired `20261010T200339Z-4189548` evidence/quote exports.
- See `docs/POOL-EXIT-UPDATE.md` for the current update and rollback procedure.

This document records engineering progress and research findings. It is not a claim that the scanner identifies safe assets or that the current strategy is profitable.

## 11 October 2026 — consolidated launch-quality direction and evidence foundation

Reviewed the uploaded edge plan against current source and observed negative Fast30 outcomes. Adopted launch-feature research, explicit as-of information, frozen prospective trials and an evidence-based stop decision. Corrected quote-failure/rug conflation, dust-size sellability, exact-reconstruction claims, cost double-counting, sample-capacity assumptions and inconsistent time horizons. The consolidated decision record is `docs/EDGE-RESEARCH-PLAN.md`.

Prepared the launch-foundation release: bounded immutable creation evidence independent of candidate eviction; distinct creator/trader roles; local receipt timestamps; no fabricated on-chain time or raw metadata downloads; a read-only feature-availability audit; and independent quote-ledger backup with isolated all-table restore verification and optional B2 round trip. The combined guarded installer includes the previous pool/exit patch and accepts either known source state. New tests cover retention/caps, adapter failure isolation, archive corruption, cursor preservation, cloud failure and installer rollback.

This entry records development, not confirmed Kali deployment. The scanner stays 0.2.9 and the quote observer stays 0.6.0. No new admission rule, wallet, paid subscription or live order is introduced. The next substantive research step is an as-of launch-feature study after actual field availability has been audited. External alerts for the new backup and cloud retention remain explicit follow-ups.

## 11 October 2026 — host foundation confirmed and as-of launch study built

Supplied Kali output confirms deployment of GitHub commit `2dd705df52327e33e5837c31586794c149e3de30`, a short healthy/restart-free check and successful local/cloud quote-ledger restore verification. The first launch audit retained 38 creations: trader reported in all 38, creator reported in none, URI hash in 37. This confirms field availability in that sample, not verified creator identity or full-market coverage.

Built a standalone bounded read-only launch study while production collects. It links three research cohorts to immutable launch receipts available by signal time, computes strictly earlier other-mint trader/URI-hash counts, and retains original-pool outcome state denominators at 30/60/120/300 seconds. Exploratory groups preserve cohort, follow-up selection and entry liquidity; exports are replayable with fixed cutoff/protocol identity. The health audit now distinguishes an unknown persisted snapshot timestamp from the current read time, and separately counts reported traders. Scanner, observer, entry rules, request budgets and installed backups are unchanged. The new study still needs a real host export; local tests are not live results. Details: `docs/LAUNCH-STUDY.md`.

### Launch-study first-run correction

The first host report attempt failed with a generic SQLite OperationalError and published no report. Local investigation reproduced an inefficient planner choice in the outcome lookup. The reader now uses unique-key equality lookups, preserves the same 10-second read budget and cutoff semantics, and emits safe stage-specific SQLite diagnostics. Large-history, locked-database and missing-schema tests were added. The original host failure has no detailed cause recorded; successful host collection remains to be verified.


## 11 October 2026 — launch export verified and joined report automated

The corrected launch collector succeeded on Kali: the supplied report records a 0.283-second read, 609 study entries and 378 entries with prior available launch context. Its actual post-registration coverage is about 4 hours 53 minutes, so earlier-launch counts still have partial lookback. The companion quote export joins to all 609 observer decisions; 27 were admitted (eight baseline, ten early-activity, nine Fast30). This confirms successful collection and joins without assigning an unrecorded cause to the first generic failure.

Implemented an offline, replayable launch/observer/paper/quote report and a one-command read-only wrapper. Identity checks handle distinct baseline IDs; common cutoffs exclude later evidence; integer fixed-quantity checks recompute quoted changes; skipped, failed, unavailable and late observations retain explicit denominators. Matched and wider quote windows remain separate, including the wider Fast30 severe loss. Twenty added tests include wrapper failure cleanup and private atomic publication. This entry records development and validation against supplied files; the fresh host wrapper run is pending.

The report's primary descriptive quote horizon is 30 seconds after buy response, with 60/120-second comparators. All three matched cohorts have negative mean quoted change at 30 seconds in the supplied sample. A positive nine-watch Fast30 result at 120 seconds is exploratory, not a new exit rule or proof of profitability. Scanner, observer, provider budgets, signal rules and backup services remain unchanged. The next gate is sufficient descriptive evidence to justify a frozen prospective hypothesis, followed separately by execution engineering. See `docs/LAUNCH-QUOTE-UPDATE.md`.
