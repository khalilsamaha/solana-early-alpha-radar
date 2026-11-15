# R1 scanner image candidate

This additive package replaces the source-overlay assumption for the scanner
image boundary. It does not implement or approve the complete production stack.
Existing accepted source, fixture images and evidence remain unchanged.

`candidate.py` stages only tracked scanner package/src/public/scripts files plus
two image-contained verification tools. It rejects symlinks, new runtime npm
dependencies, dirty source and reused output. A manifest binds every staged file,
Git revision/tree and the exact previously observed runtime image ID. The default
image command verifies these bytes and exits; it does not start the scanner.
Inherited environment variables are cleared by the entrypoint.

The base is the existing local image
`sha256:786529348e5b7b6563a33d8c358c3d03c97110879d6ad53af0fbae65cd0249f9`.
The previous /app contents are removed in the new layer and the complete selected
scanner source is copied in. This reuses the previously observed Node/OS runtime;
it is not a fresh upstream dependency/security approval or reproducible OS build.
Its historical lower layers remain in the image. No credentials, production data,
.env, node_modules or untracked source are included in the build context.

## Consolidated host boundary

Run `scripts/r1-image-kali.sh` from a clean pinned `source` checkout, as UID/GID
1000 with existing local Docker access. Only Python standard library, Node and
existing Docker are used. No pip, sudo, remote builder, pull or provider access.
The builder is explicitly the local legacy builder (`DOCKER_BUILDKIT=0`) so the
local immutable image ID is used directly. If unavailable, stop; do not install,
change permissions, switch builders or download a replacement automatically.

The batch runs focused tests, creates a private source context, records build
intent, builds with network none and a 120-second client limit, inspects image
configuration and executes four owned disposable containers from the built ID:

1. Default command independently verifies all image contents against staged hashes.
2. Native Unix discovery consumes create/migration/create, including a second creation.
3. A sequence-gap frame produces a gap and no accepted creation.
4. A missing endpoint refuses startup and does not fall back upstream.

No source overlay is mounted. Only the private synthetic Unix endpoint is mounted
read-only. Containers use network none, user 1000, no capabilities, no new
privileges, read-only root, no restart, no healthcheck, no logging, init and fixed
CPU/memory/PID limits. Before start and cleanup, exact image/label/ID and isolation
are verified. A lost create response is reconciled only by its random owned name;
uncertain identity is retained. Exit code zero alone cannot pass. Cleanup requires
an exact removal acknowledgment. There is no production-container selector.

Success is `image-candidate-offline-passed-live-blocked`; it emits an image ID,
source-bound deployment candidate and four removal receipts in `acceptance.zip`.
The candidate image and build context are retained for review, never pushed or
installed. The image ID is local content identity, not a registry RepoDigest.
A build timeout may leave daemon-side work; never retry, prune or remove unknown
objects. Preserve the review directory and report/log on any failure. This check
is not a live-host claim until its supplied evidence is reviewed.

Production handoff/rollback, the upstream owner, credential provisioning, finite
live supervision, real evidence delivery, capacity/retention and approved pilot
terms remain separate gates. This candidate has no production launch command or
approval file. Image/source acceptance cannot refresh E0 evidence or release holds.
