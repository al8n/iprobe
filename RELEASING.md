# Releasing iprobe

The current release candidate is `0.1.2`. A version in `Cargo.toml`, release
notes, or a successful dry run is not a published release. Publication is
complete only after crates.io reports the version and its checksum matches the
archive verified by the release workflow.

## Prepare the candidate

1. Start from a clean, current `main` branch with green CI.
2. Confirm that the package version in `Cargo.toml`, the `README.md` dependency
   requirement, and the dated `CHANGELOG.md` entry describe the same release.
   `Unreleased` must be empty before tagging.
3. Run the release metadata checks:

   ```sh
   python3 -B -m unittest scripts/test_check_release_version.py
   python3 -B scripts/check_release_version.py --tag v0.1.2
   ```

   The checker requires Python 3.11 or newer. It intentionally accepts only the
   repository's pinned README badge header and normalized body, one exact
   Installation boundary, and one canonical TOML dependency example. Review
   any legitimate README badge or body change and update the corresponding
   pinned digest and its test explicitly; do not broaden the parser to
   accommodate unrelated Markdown.

4. Run the same substantive Rust checks as CI with stable Rust and Rust 1.71:

   ```sh
   cargo +stable generate-lockfile
   cargo +stable fmt --all -- --check
   RUSTFLAGS=-Dwarnings cargo +stable clippy --all-targets --all-features -- -D warnings
   RUSTFLAGS=-Dwarnings cargo +stable test --locked --all-features --all-targets
   RUSTFLAGS=-Dwarnings cargo +stable test --locked --all-features --doc
   RUSTDOCFLAGS=-Dwarnings cargo +stable doc --locked --all-features --no-deps
   RUSTFLAGS=-Dwarnings cargo +1.71.0 check --locked --all-features --all-targets
   RUSTFLAGS=-Dwarnings cargo +1.71.0 test --locked --all-features --all-targets
   RUSTFLAGS=-Dwarnings cargo +1.71.0 test --locked --all-features --doc
   cargo +stable semver-checks check-release --baseline-version 0.1.0 --release-type patch --all-features
   ```

   The semver check uses `0.1.0` as its registry baseline because the published
   `0.1.1` dependency resolution currently encounters the `rustix 1.1.5` build
   regression. Keep the explicit patch-release check until that baseline issue
   is resolved and reviewed.

5. Validate the archive and the standard Cargo publish path without uploading:

   ```sh
   cargo +stable package --locked --all-features
   cargo +stable publish --locked --package iprobe --registry crates-io --all-features --dry-run
   ```

The repository is a library and intentionally does not commit `Cargo.lock`.
Generate a lockfile for release validation, keep it ignored, and never add it
to the release commit.

## Configure trusted publishing

Configure the external controls only after `.github/workflows/crates.yml` is
merged to `main`. Changing either platform is a separate external action and
requires explicit confirmation at the time of the change.

The crates.io Trusted Publisher must use these exact values:

- GitHub owner: `al8n`
- Repository: `iprobe`
- Workflow: `crates.yml`
- Environment: `crates-io`

The GitHub `crates-io` environment must require reviewer `al8n`, allow only
tags matching `v*`, and have administrator bypass disabled. Do not add a
long-lived crates.io token or a token-based recovery path.

## Release workflow trust boundary

The unprivileged verify job generates one ephemeral `Cargo.lock`, tests the
locked graph, performs Cargo's package and publish dry run, and records the
SHA-256 of both the lockfile and the archive created under Cargo's
`tmp-registry` directory. It transfers the exact lockfile and verified archive
as separate short-lived workflow artifacts.

The publish job installs the exact stable toolchain and Linux host tuple
recorded by the verify job, confirms the exact `rustc` and `cargo` versions,
restores and checks the verified lockfile, and repeats the annotated-tag,
commit, and current-`main` identity checks. The crates.io token exists only in
the environment of the `cargo publish` step. After publication, a token-free
step checks that Cargo's published archive has the same SHA-256 as the archive
from the verify job.

Release actions use immutable commit SHAs even though ordinary CI uses mutable
major-version tags. This tighter rule applies because the release job can mint
publication credentials and initiate an irreversible upload.

The `id-token: write` permission applies to the entire publish job, not only to
the authentication step. That job is therefore limited to immutable-pinned
checkout, artifact download, and crates.io authentication actions; fixed Git
and checksum checks; exact Rust installation; and Cargo publication. Rustup
downloads over HTTPS and validates checksums but not artifact signatures.
Cargo's required publish verification executes the locked dependency graph
while the job has OIDC permission and while the publish step has its ephemeral
token. The human environment review, unprivileged verification job, immutable
action pins, and exact toolchain and artifact checks reduce but do not remove
that residual supply-chain risk.

## Publish with explicit authorization

Stop before each external mutation unless a human has explicitly authorized
that action: enabling the Trusted Publisher or GitHub environment, uploading
the crate, creating and pushing the tag, and creating the GitHub release.

After the platform settings and upload have been authorized:

1. Confirm that `0.1.2` is absent from crates.io and that current `main` is the
   reviewed release commit.
2. Create annotated tag `v0.1.2` at that commit and push only the tag. The tag
   workflow rejects lightweight tags, version mismatches, tags that do not peel
   to the triggering commit, and commits that are not current `origin/main`.
3. Review the tag workflow's commit and verification results, then reviewer
   `al8n` approves the `crates-io` environment deployment.
4. Keep `main` at the tagged commit until crates.io reports `0.1.2` and its
   checksum matches the verify job's recorded archive SHA-256. Download the
   short-lived verified-crate artifact before it expires if an independent
   local checksum is needed.
5. Create the GitHub release only after the registry version and checksum
   match. The GitHub release and annotated tag must point to the same commit.

If a publish run fails or its outcome is ambiguous, keep `main` frozen and
query crates.io before rerunning anything. Never move or delete the tag, invent
a replacement version, or blindly republish. Rerun the same tag workflow only
after confirming that crates.io does not contain the version. A checksum
mismatch blocks the GitHub release and must not trigger another upload attempt.
