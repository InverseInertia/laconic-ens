# LENS

Read `CONTEXT.md` for the domain glossary and `wiki/Architecture.md` and `wiki/Development.md` for the module map and how to add things.

## Changelog

`CHANGELOG.md` is the running changelog, and the release job publishes a tag's section as the GitHub release notes (`packaging/release_notes.py`).

- Any change a user would notice (a feature, a behaviour or output change, a fix, a packaging or install change) adds a line under `## Unreleased`, in the group it belongs to (`### New`, `### Changes`, `### Fixes`), in the same commit or PR. Write it for users, not developers: what they can now do or what no longer goes wrong, ending with the PR or issue number, e.g. `(#74)`. Create the group if it is missing.
- Refactors, tests, CI and docs-only changes need no entry; label the PR `no changelog`. The `changelog` workflow fails a PR that changes `laconic/` or `packaging/` without touching `CHANGELOG.md` and without that label.
- When cutting a release, rename `## Unreleased` to `## [vX.Y.Z](https://github.com/InverseInertia/laconic-ens/releases/tag/vX.Y.Z) (YYYY-MM-DD)` and add a new, empty `## Unreleased` above it, then tag.

## Reviewing

When reviewing a pull request, check the `## Unreleased` section of `CHANGELOG.md` as part of the diff: every user-visible change in the PR has an entry, the entries are accurate and in the right group, and nothing the PR doesn't do is claimed. A missing or wrong entry for a user-visible change is a finding, not a nit.
