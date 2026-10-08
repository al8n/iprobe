"""Tests for the release metadata gate used by trusted publishing."""

from datetime import date
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_release_version as checker


README_BOUNDARY = "\n\n## Installation\n"
PINNED_README_HEADER_SHA256 = (
    "69abe4c659797b87eaa0e869318d2714fdac0b61085027f27f5632ca1b8532fb"
)
PINNED_NORMALIZED_README_BODY_SHA256 = (
    "77bc44b96b08ad220c2903af6a0bdf07fe27afc33726650c0be0d2dd742cd621"
)
DEPENDENCY_PLACEHOLDER = "__IPROBE_CANONICAL_DEPENDENCY__"
README_SOURCE = (ROOT / "README.md").read_text(encoding="utf-8")
README_HEADER, CURRENT_README_BODY = README_SOURCE.split(README_BOUNDARY, 1)
MONTH_NAMES = (
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
)


def requirement_for_version(version: str) -> str:
    """Derive the intended README requirement independently of the checker."""

    major, minor, _ = version.split(".")
    return "0.{}".format(minor) if major == "0" else major


def readme_for_version(version: str) -> str:
    """Build a README using the pinned body with only its requirement changed."""

    requirement = requirement_for_version(version)
    canonical_block = '```toml\n[dependencies]\niprobe = "{}"\n```'.format(
        requirement
    )
    body = NORMALIZED_README_BODY.replace(DEPENDENCY_PLACEHOLDER, canonical_block)
    return README_HEADER + README_BOUNDARY + body


def ordinal(day: int) -> str:
    """Format a day with its English ordinal suffix for fixtures."""

    if 10 < day % 100 < 14:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return "{}{}".format(day, suffix)


def changelog_for_version(version: str, release_date: date) -> str:
    """Build a dated release fixture without hardcoding a package version."""

    date_text = "{} {}, {}".format(
        MONTH_NAMES[release_date.month - 1],
        ordinal(release_date.day),
        release_date.year,
    )
    return f'''# Releases

## Unreleased

## Released

## {version} ({date_text})

- Stable release.
'''


def next_patch(version: str) -> str:
    """Return a different stable version for wrong-tag tests."""

    major, minor, patch = (int(part) for part in version.split("."))
    return "{}.{}.{}".format(major, minor, patch + 1)


with (ROOT / "Cargo.toml").open("rb") as manifest_file:
    VERSION = tomllib.load(manifest_file)["package"]["version"]
REQUIREMENT = requirement_for_version(VERSION)
CURRENT_CANONICAL_BLOCK = '```toml\n[dependencies]\niprobe = "{}"\n```'.format(
    REQUIREMENT
)
if CURRENT_README_BODY.count(CURRENT_CANONICAL_BLOCK) != 1:
    raise AssertionError("repository README must contain one current dependency block")
NORMALIZED_README_BODY = CURRENT_README_BODY.replace(
    CURRENT_CANONICAL_BLOCK, DEPENDENCY_PLACEHOLDER, 1
)
RELEASE_DATE = date(2026, 10, 8)
README = readme_for_version(VERSION)
README_BODY = README.split(README_BOUNDARY, 1)[1]
CHANGELOG = changelog_for_version(VERSION, RELEASE_DATE)
RELEASE_HEADING = "## {} ({} {}, {})".format(
    VERSION,
    MONTH_NAMES[RELEASE_DATE.month - 1],
    ordinal(RELEASE_DATE.day),
    RELEASE_DATE.year,
)


class ReleaseMetadataTests(unittest.TestCase):
    """Exercise accepted metadata and every security-relevant rejection."""

    def assert_invalid(
        self, readme=README, changelog=CHANGELOG, tag=None, version=VERSION
    ):
        """Assert that a metadata fixture is rejected."""

        with self.assertRaises(checker.ReleaseCheckError):
            checker.validate_release_metadata(version, readme, changelog, tag)

    def test_fixture_uses_the_known_pinned_readme_header(self):
        self.assertEqual(len(README_HEADER.splitlines()), 33)
        self.assertEqual(
            hashlib.sha256(README_HEADER.encode("utf-8")).hexdigest(),
            PINNED_README_HEADER_SHA256,
        )
        self.assertEqual(checker.README_HEADER_SHA256, PINNED_README_HEADER_SHA256)
        self.assertEqual(
            hashlib.sha256(NORMALIZED_README_BODY.encode("utf-8")).hexdigest(),
            PINNED_NORMALIZED_README_BODY_SHA256,
        )
        self.assertEqual(
            checker.README_NORMALIZED_BODY_SHA256,
            PINNED_NORMALIZED_README_BODY_SHA256,
        )
        self.assertEqual(README, README_SOURCE)
        self.assertEqual(README.count(README_BOUNDARY), 1)

    def test_current_repository_is_consistent_for_candidate(self):
        self.assertEqual(checker.check_repository(), VERSION)

    def test_accepts_exact_version_tag(self):
        checker.validate_release_metadata(VERSION, README, CHANGELOG, "v" + VERSION)

    def test_accepts_future_zero_major_requirement(self):
        version = "0.27.4"
        self.assertEqual(checker.expected_readme_requirement(version), "0.27")
        checker.validate_release_metadata(
            version,
            readme_for_version(version),
            changelog_for_version(version, date(2027, 1, 21)),
            "v" + version,
        )

    def test_accepts_future_nonzero_major_requirement(self):
        version = "2.3.4"
        self.assertEqual(checker.expected_readme_requirement(version), "2")
        checker.validate_release_metadata(
            version,
            readme_for_version(version),
            changelog_for_version(version, date(2028, 2, 2)),
            "v" + version,
        )

    def test_nonrelease_check_allows_unreleased_work(self):
        checker.validate_release_metadata(
            VERSION,
            README,
            CHANGELOG.replace(
                "## Unreleased\n\n## Released",
                "## Unreleased\n\n- Work in progress.\n\n## Released",
            ),
        )

    def test_repository_nonrelease_check_allows_unreleased_work(self):
        changelog = CHANGELOG.replace(
            "## Unreleased\n\n## Released",
            "## Unreleased\n\n- Work in progress.\n\n## Released",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Cargo.toml").write_text(
                '[package]\nname = "iprobe"\nversion = "{}"\n'.format(VERSION),
                encoding="utf-8",
            )
            (root / "README.md").write_text(README, encoding="utf-8")
            (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
            self.assertEqual(checker.check_repository(root), VERSION)

    def test_rejects_nonempty_unreleased_section_for_tag(self):
        changelog = CHANGELOG.replace(
            "## Unreleased\n\n## Released",
            "## Unreleased\n\n- Not released.\n\n## Released",
        )
        self.assert_invalid(changelog=changelog, tag="v" + VERSION)

    def test_rejects_wrong_tag(self):
        self.assert_invalid(tag="v" + next_patch(VERSION))

    def test_rejects_prerelease_and_leading_zero_versions(self):
        for version in (VERSION + "-rc.1", "01.2.3"):
            with self.subTest(version=version):
                self.assert_invalid(version=version)

    def test_rejects_stale_readme_requirement(self):
        stale = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT),
            'iprobe = "99"',
            1,
        )
        self.assert_invalid(readme=stale)

    def test_rejects_modified_pinned_readme_header(self):
        changed = README_HEADER.replace("</div>", "</div> changed", 1)
        self.assert_invalid(readme=changed + README_BOUNDARY + README_BODY)

    def test_rejects_missing_or_duplicate_installation_boundary(self):
        missing = README.replace(README_BOUNDARY, "\n\n## Install\n", 1)
        duplicate = README + README_BOUNDARY + README_BODY
        for readme in (missing, duplicate):
            with self.subTest(readme=readme):
                self.assert_invalid(readme=readme)

    def test_rejects_raw_html_and_comments_after_installation(self):
        for prefix in ("<pre>\n", "<!-- hidden -->\n"):
            with self.subTest(prefix=prefix):
                self.assert_invalid(
                    readme=README_HEADER + README_BOUNDARY + prefix + README_BODY
                )

    def test_rejects_unsupported_and_unterminated_fences(self):
        unsupported = README.replace("```rust", "```text", 1)
        unterminated = README.rsplit("```", 1)[0]
        for readme in (unsupported, unterminated):
            with self.subTest(readme=readme):
                self.assert_invalid(readme=readme)

    def test_rejects_invalid_toml(self):
        invalid = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT), "iprobe = [", 1
        )
        self.assert_invalid(readme=invalid)

    def test_rejects_dependency_decoys_outside_canonical_block(self):
        decoys = (
            '    iprobe = "99"',
            'Use `iprobe = "99"` instead.',
            '# iprobe = "99"',
            'Use `package = "iprobe"` as an alias.',
            "Use `package = 'iprobe'` as an alias.",
        )
        for decoy in decoys:
            with self.subTest(decoy=decoy):
                self.assert_invalid(readme=README + "\n" + decoy + "\n")

    def test_rejects_quoted_dotted_table_and_alias_decoys(self):
        decoys = (
            '`"iprobe" = "99"`',
            '`dependencies.iprobe.version = "99"`',
            '`dependencies.iprobe.git = "https://example.invalid/iprobe"`',
            '    [dependencies.iprobe]\n    version = "99"\n    git = "https://example.invalid/iprobe"',
            'probe = { "package" = "iprobe", version = "99" }',
        )
        for decoy in decoys:
            with self.subTest(decoy=decoy):
                self.assert_invalid(readme=README + "\n" + decoy + "\n")

    def test_rejects_any_other_readme_body_mutation(self):
        appended = README + "\nAdditional release text.\n"
        changed = README.replace(
            "These are local operation checks.",
            "These are local host operation checks.",
            1,
        )
        for readme in (appended, changed):
            with self.subTest(readme=readme):
                self.assert_invalid(readme=readme)

    def test_rejects_noncanonical_toml_source_forms(self):
        multiline = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT),
            'iprobe = """\\\n{}"""'.format(REQUIREMENT),
            1,
        )
        dotted = README.replace(
            '[dependencies]\niprobe = "{}"'.format(REQUIREMENT),
            'dependencies.iprobe = "{}"'.format(REQUIREMENT),
            1,
        )
        commented = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT),
            'iprobe = "{}" # current requirement'.format(REQUIREMENT),
            1,
        )
        for readme in (multiline, dotted, commented):
            with self.subTest(readme=readme):
                self.assert_invalid(readme=readme)

    def test_rejects_dependency_alias(self):
        aliased = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT),
            'probe = {{ package = "iprobe", version = "{}" }}'.format(REQUIREMENT),
            1,
        )
        self.assert_invalid(readme=aliased)

    def test_rejects_dependency_source_override(self):
        overridden = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT),
            'iprobe = {{ version = "{}", git = "https://example.invalid/iprobe" }}'.format(
                REQUIREMENT
            ),
            1,
        )
        self.assert_invalid(readme=overridden)

    def test_rejects_extra_toml_keys(self):
        extra_dependency = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT),
            'iprobe = "{}"\nother = "1"'.format(REQUIREMENT),
            1,
        )
        extra_table = README.replace(
            'iprobe = "{}"'.format(REQUIREMENT),
            'iprobe = "{}"\n\n[package]\nname = "decoy"'.format(REQUIREMENT),
            1,
        )
        for readme in (extra_dependency, extra_table):
            with self.subTest(readme=readme):
                self.assert_invalid(readme=readme)

    def test_rejects_duplicate_or_missing_toml_document(self):
        duplicated = README + "\n" + README_BODY.split("```rust", 1)[0]
        missing = README_HEADER + README_BOUNDARY + "```rust\nfn main() {}\n```\n"
        for readme in (duplicated, missing):
            with self.subTest(readme=readme):
                self.assert_invalid(readme=readme)

    def test_rejects_candidate_or_missing_release_heading(self):
        candidate = CHANGELOG.replace(
            RELEASE_HEADING, "## {} (release candidate)".format(VERSION), 1
        )
        missing = CHANGELOG.replace(RELEASE_HEADING + "\n", "", 1)
        for changelog in (candidate, missing):
            with self.subTest(changelog=changelog):
                self.assert_invalid(changelog=changelog, tag="v" + VERSION)

    def test_rejects_candidate_heading_alongside_valid_release_heading(self):
        changelog = CHANGELOG.replace(
            RELEASE_HEADING,
            RELEASE_HEADING + "\n\n## {} (release candidate)".format(VERSION),
            1,
        )
        self.assert_invalid(changelog=changelog, tag="v" + VERSION)

    def test_rejects_invalid_release_date_and_ordinal(self):
        invalid_date = CHANGELOG.replace(
            RELEASE_HEADING, "## {} (February 30th, 2026)".format(VERSION), 1
        )
        invalid_ordinal = CHANGELOG.replace(
            RELEASE_HEADING, "## {} (October 8st, 2026)".format(VERSION), 1
        )
        for changelog in (invalid_date, invalid_ordinal):
            with self.subTest(changelog=changelog):
                self.assert_invalid(changelog=changelog, tag="v" + VERSION)

    def test_rejects_indented_pseudoheadings(self):
        pseudo_unreleased = CHANGELOG.replace(
            "## Unreleased", "    ## Unreleased", 1
        )
        pseudo_version = CHANGELOG.replace(
            RELEASE_HEADING, "    " + RELEASE_HEADING, 1
        )
        for changelog in (pseudo_unreleased, pseudo_version):
            with self.subTest(changelog=changelog):
                self.assert_invalid(changelog=changelog, tag="v" + VERSION)

    def test_rejects_release_heading_before_released_section(self):
        reordered = CHANGELOG.replace(
            "## Released\n\n" + RELEASE_HEADING,
            RELEASE_HEADING + "\n\n## Released",
            1,
        )
        self.assert_invalid(changelog=reordered, tag="v" + VERSION)

    def test_rejects_html_and_fences_in_tagged_changelog(self):
        html = CHANGELOG + "\n<!-- hidden -->\n"
        fenced = CHANGELOG + "\n```text\nhidden\n```\n"
        for changelog in (html, fenced):
            with self.subTest(changelog=changelog):
                self.assert_invalid(changelog=changelog, tag="v" + VERSION)


if __name__ == "__main__":
    unittest.main()
