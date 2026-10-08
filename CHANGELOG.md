# Releases

## 0.1.2 (October 8th, 2026)

- Fix Windows Winsock startup and cleanup pairing so cleanup follows only a
  successful startup.
- Clarify the cached, best-effort local socket probe semantics and add
  deterministic accessor and caching tests.
- Raise the MSRV to Rust 1.71, enable the `rustix` `time` feature, and expand
  CI checks for stable, MSRV, documentation, packaging, semver, dry-run
  publishing, and coverage.

## 0.1.1 (March 7th, 2025)

- Upgrade `rustix` from 0.38 to 1 and update the `bind` call for the new API.

## 0.1.0 (January 6th, 2025)

FEATURES

- Add `ipv4`, `ipv6` and `ipv4_mapped_ipv6`
