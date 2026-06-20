# Review

I was unable to review the changes since the last commit because the command runner failed before starting PowerShell for every attempted command, including:

- `git status --short`
- `git diff --stat HEAD`
- `git diff --name-only HEAD`
- `pwd`

Each attempt failed with:

```text
windows sandbox: spawn setup refresh
```

No MCP workspace resources were available as a fallback, so I could not inspect the working tree, read changed files, or produce evidence-backed findings.

## Findings

No review findings are reported because the diff could not be inspected.

## Required Follow-Up

Re-run the review once shell access is working, using:

```powershell
git status --short
git diff HEAD
```
