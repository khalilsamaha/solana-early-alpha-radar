# R1 image candidate Kali acceptance — 15 November 2026

Accept published 74a37138734ca22713b2f2c0a3e9bbfaf9644841, tree
c5594d7ccbcc15738a99e5974658df1e25c87179, for the bounded offline image scope.
The uploaded acceptance(5).zip SHA-256 is
36eacccb3e5f8a76f4b08ae4aa5bb248c777d43aa703db9e7966c4ef4dba3cfc.

Independent review reproduced the exact staged manifest and Dockerfile from the
clean source. All 65 report fingerprints match, all 59 image-file hashes match,
the build intent and image ID bind, and the deployment-candidate digest is exact.
The validation log records 22 passing tests, no errors/failures/skips or matched
runtime diagnostics. The build log includes a legacy-builder deprecation notice;
that is an acknowledged tooling limitation, not a runtime failure or future
compatibility guarantee.

Accepted local image ID:
sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140.
Manifest SHA-256:
e23bb7b4628496f5083fc26817f67f863bb248e412f9f83b0a4fdf64b6d1daf9.
This is a local image identity, not a published registry digest.

All four before/after receipts pass image/label/ID/isolation checks, with distinct
containers reported removed. Default verification matches the manifest; normal
Unix delivery yields create/migration/create and two creations; a sequence gap
accepts none; a missing endpoint refuses startup. All probe upstream/fetch attempt
counts are zero. No source overlay is mounted. The normal case's final gap is the
intentional synthetic peer EOF, not a live feed failure.

Reported run: November 15, 08:23:13.474084–08:23:20.255770 UTC /
09:23:13–09:23:20 CET. This is supplied artifact evidence, not reviewer access to
Kali/Docker, current remote state, RPC or balances. Container removal is supported
by retained receipts, not a fresh daemon query. Do not repeat the passing batch.

Closed boundary: scanner image/source packaging and isolated discovery behavior.
Still open: complete production deployment/admission, service-control handoff and
rollback, actual owner/connection proof, live supervision and credentials, real
variable-session delivery and retention/capacity, approved measurement/exposure
terms and activation. No pilot or confirmation study has started. E0 remains
independent with holds preserved; this evidence does not refresh its observation.
