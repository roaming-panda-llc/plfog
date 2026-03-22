Review the current PR and, if it passes review, approve it as PastLivesReviewBot.

## Steps

1. Determine the current branch and find its open PR:
   ```
   gh pr view --json number,title,url,body,headRefName,baseRefName
   ```

2. Get the full diff against the base branch:
   ```
   gh pr diff
   ```

3. Review the diff against the project's coding standards in CLAUDE.md / AGENTS.md. Check for:
   - Fat models, skinny views — no business logic in views
   - Type annotations on all functions (including `-> None`)
   - `help_text` on all model fields
   - `TextChoices` for choice fields
   - Proper error handling (`dict[key]` not `dict.get()`, re-raised `DoesNotExist`)
   - No N+1 queries (use `select_related`/`prefetch_related`)
   - Tests exist for new code (BDD-style `*_spec.py`, `it_*` functions)
   - Ruff-compatible style (120 char lines, correct import ordering)
   - No `@pytest.mark.skip`, `# pragma: no cover`, or `# pragma: no mutate`
   - Migrations have reverse functions (no `RunPython.noop`)
   - No security issues (SQL injection, XSS, etc.)

4. If issues are found:
   - Post a **comment** (not an approval) on the PR as PastLivesReviewBot listing the issues:
     ```
     GH_TOKEN="$BOT_PAT" gh pr comment <number> --body "<review comments>"
     ```
   - Tell me what needs to be fixed.

5. If the code passes review:
   - Post a formal **APPROVE** review as PastLivesReviewBot:
     ```
     GH_TOKEN="$BOT_PAT" gh api --method POST repos/{owner}/{repo}/pulls/<number>/reviews \
       -f event='APPROVE' \
       -f body='Reviewed and approved by PastLivesReviewBot. Code meets PLFOG coding standards.'
     ```
   - Confirm the approval to me.

## Important
- The `BOT_PAT` environment variable must be set (it's stored in GitHub Secrets, but for local use it needs to be in the shell environment or `.env`).
- Never approve your own changes without actually reviewing the diff.
- Be strict — follow the coding standards exactly as written.
