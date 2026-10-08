#!/usr/bin/env python3
"""Verify that release-facing metadata agrees with the Cargo package version."""

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
STABLE_VERSION = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z"
)
README_INSTALLATION_BOUNDARY = "\n\n## Installation\n"
README_HEADER_SHA256 = "69abe4c659797b87eaa0e869318d2714fdac0b61085027f27f5632ca1b8532fb"
README_DEPENDENCY_PLACEHOLDER = "__IPROBE_CANONICAL_DEPENDENCY__"
README_NORMALIZED_BODY_SHA256 = (
    "77bc44b96b08ad220c2903af6a0bdf07fe27afc33726650c0be0d2dd742cd621"
)
README_FENCES = {"```toml": "toml", "```rust": "rust"}
MONTH_NUMBERS = {
    month: number
    for number, month in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}


class ReleaseCheckError(ValueError):
    """Release metadata is inconsistent or unsafe to publish."""


def readme_code_blocks(readme: str) -> list[tuple[str, str]]:
    """Return code blocks from the repository's constrained README format."""

    if readme.count(README_INSTALLATION_BOUNDARY) != 1:
        raise ReleaseCheckError(
            "README must contain one exact top-level Installation boundary"
        )
    header, body = readme.split(README_INSTALLATION_BOUNDARY, 1)
    header_sha256 = hashlib.sha256(header.encode("utf-8")).hexdigest()
    if header_sha256 != README_HEADER_SHA256:
        raise ReleaseCheckError(
            "README badge header changed; review it and update the pinned digest explicitly"
        )
    if "<" in body or ">" in body:
        raise ReleaseCheckError(
            "README content after Installation must not contain raw HTML or comments"
        )

    blocks = []
    language = None
    block = []
    for line in body.splitlines():
        if language is None:
            if line in README_FENCES:
                language = README_FENCES[line]
                block = []
            elif "```" in line or "~~~" in line:
                raise ReleaseCheckError("README contains an unsupported code fence")
        elif line == "```":
            blocks.append((language, "\n".join(block)))
            language = None
            block = []
        elif "```" in line or "~~~" in line:
            raise ReleaseCheckError("README contains an unsupported code fence")
        else:
            block.append(line)
    if language is not None:
        raise ReleaseCheckError("README contains an unterminated code fence")
    return blocks


def expected_readme_requirement(version: str) -> str:
    """Return the documented Cargo requirement for a stable package version."""

    major, minor, _ = version.split(".")
    return "0.{}".format(minor) if major == "0" else major


def validate_readme(version: str, readme: str) -> None:
    """Require one exact registry dependency example for the package version."""

    expected = expected_readme_requirement(version)
    canonical_body = '[dependencies]\niprobe = "{}"'.format(expected)
    toml_bodies = []
    for language, body in readme_code_blocks(readme):
        if language != "toml":
            continue
        toml_bodies.append(body)
        if body != canonical_body:
            raise ReleaseCheckError(
                "README dependency TOML must use the exact canonical source form"
            )
        try:
            document = tomllib.loads(body)
        except tomllib.TOMLDecodeError as error:
            raise ReleaseCheckError(
                "README contains invalid TOML: {}".format(error)
            ) from error
        if document != {"dependencies": {"iprobe": expected}}:
            raise ReleaseCheckError(
                "README TOML must contain only dependencies.iprobe = {!r}".format(
                    expected
                )
            )

    if len(toml_bodies) != 1:
        raise ReleaseCheckError(
            "README must contain exactly one canonical iprobe dependency document"
        )

    readme_body = readme.split(README_INSTALLATION_BOUNDARY, 1)[1]
    canonical_block = "```toml\n{}\n```".format(canonical_body)
    if readme_body.count(canonical_block) != 1:
        raise ReleaseCheckError(
            "README must contain one exact canonical iprobe dependency block"
        )
    normalized_body = readme_body.replace(
        canonical_block, README_DEPENDENCY_PLACEHOLDER, 1
    )
    normalized_sha256 = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
    if normalized_sha256 != README_NORMALIZED_BODY_SHA256:
        raise ReleaseCheckError(
            "README body changed; review it and update the pinned normalized digest explicitly"
        )


def ordinal_suffix(day: int) -> str:
    """Return the English ordinal suffix for a calendar day."""

    if 10 < day % 100 < 14:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def validate_changelog(version: str, changelog: str, release: bool) -> None:
    """Require one dated current-version entry in the release section."""

    if release and ("<" in changelog or ">" in changelog):
        raise ReleaseCheckError("CHANGELOG must not contain raw HTML or comments")
    if release and ("```" in changelog or "~~~" in changelog):
        raise ReleaseCheckError("CHANGELOG must not contain fenced code blocks")

    lines = changelog.splitlines()
    unreleased_matches = [i for i, line in enumerate(lines) if line == "## Unreleased"]
    released_matches = [i for i, line in enumerate(lines) if line == "## Released"]
    if len(unreleased_matches) != 1:
        raise ReleaseCheckError("CHANGELOG must contain one Unreleased heading")
    if len(released_matches) != 1:
        raise ReleaseCheckError("CHANGELOG must contain one Released heading")

    heading_pattern = re.compile(
        r"^## {} \(([A-Z][a-z]+) ([1-9][0-9]?)(st|nd|rd|th), ([0-9]{{4}})\)$".format(
            re.escape(version)
        )
    )
    version_matches = [
        (index, match)
        for index, line in enumerate(lines)
        for match in [heading_pattern.fullmatch(line)]
        if match is not None
    ]
    if len(version_matches) != 1:
        raise ReleaseCheckError(
            "CHANGELOG must contain one dated release heading for {}".format(version)
        )

    version_heading_prefix = re.compile(
        r"^\s*##\s+{}\b".format(re.escape(version))
    )
    for line in lines:
        if version_heading_prefix.match(line) and not heading_pattern.fullmatch(line):
            raise ReleaseCheckError(
                "CHANGELOG contains a noncanonical heading for {}".format(version)
            )

    version_index, match = version_matches[0]
    month, day_text, suffix, year = match.groups()
    day = int(day_text)
    try:
        datetime(int(year), MONTH_NUMBERS[month], day)
    except (KeyError, ValueError) as error:
        raise ReleaseCheckError("CHANGELOG release date is invalid") from error
    if suffix != ordinal_suffix(day):
        raise ReleaseCheckError("CHANGELOG release date has an invalid ordinal suffix")

    unreleased_index = unreleased_matches[0]
    released_index = released_matches[0]
    if not unreleased_index < released_index < version_index:
        raise ReleaseCheckError(
            "CHANGELOG headings must order Unreleased, Released, then {}".format(
                version
            )
        )
    if release:
        unreleased_body = lines[unreleased_index + 1 : released_index]
        if any(line.strip() for line in unreleased_body):
            raise ReleaseCheckError("CHANGELOG Unreleased section must be empty")


def cargo_package_version(root: Path = ROOT) -> str:
    """Read the root iprobe package version without resolving dependencies."""

    try:
        with (root / "Cargo.toml").open("rb") as manifest_file:
            manifest = tomllib.load(manifest_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ReleaseCheckError("failed to read Cargo.toml: {}".format(error)) from error

    package = manifest.get("package")
    if not isinstance(package, dict) or package.get("name") != "iprobe":
        raise ReleaseCheckError("Cargo.toml must define the root iprobe package")
    version = package.get("version")
    if not isinstance(version, str):
        raise ReleaseCheckError("Cargo.toml package version must be a string")
    return version


def validate_release_metadata(
    version: str, readme: str, changelog: str, tag: str | None = None
) -> None:
    """Validate stable version, tag, README requirement, and release notes."""

    if not STABLE_VERSION.fullmatch(version):
        raise ReleaseCheckError(
            "release version must be stable MAJOR.MINOR.PATCH, got {!r}".format(version)
        )

    expected_tag = "v{}".format(version)
    if tag is not None and tag != expected_tag:
        raise ReleaseCheckError(
            "release tag must be {!r}, got {!r}".format(expected_tag, tag)
        )

    validate_readme(version, readme)
    validate_changelog(version, changelog, tag is not None)


def check_repository(root: Path = ROOT, tag: str | None = None) -> str:
    """Validate the checked-out repository and return its package version."""

    version = cargo_package_version(root)
    try:
        readme = (root / "README.md").read_text(encoding="utf-8")
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError as error:
        raise ReleaseCheckError(
            "failed to read release metadata: {}".format(error)
        ) from error
    validate_release_metadata(version, readme, changelog, tag)
    return version


def main() -> int:
    """Run the release metadata check."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="expected release tag including its leading v")
    arguments = parser.parse_args()
    try:
        version = check_repository(tag=arguments.tag)
    except ReleaseCheckError as error:
        print("release metadata check failed: {}".format(error), file=sys.stderr)
        return 1
    print("release metadata is consistent for {}".format(version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
