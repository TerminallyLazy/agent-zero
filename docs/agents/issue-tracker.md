# Issue tracker: GitHub

Issues and specs for this repository live in GitHub Issues at `TerminallyLazy/agent-zero`. Use the `gh` CLI with `--repo TerminallyLazy/agent-zero` for all operations.

## Conventions

- **Create an issue**: `gh issue create --repo TerminallyLazy/agent-zero --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --repo TerminallyLazy/agent-zero --comments`, including labels and relevant comments.
- **List issues**: `gh issue list --repo TerminallyLazy/agent-zero --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --repo TerminallyLazy/agent-zero --body "..."`
- **Apply or remove labels**: `gh issue edit <number> --repo TerminallyLazy/agent-zero --add-label "..."` or `--remove-label "..."`
- **Close an issue**: `gh issue close <number> --repo TerminallyLazy/agent-zero --comment "..."`

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repository treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, pull requests run through the same labels and states as issues using the `gh pr` equivalents:

- **Read a pull request**: `gh pr view <number> --repo TerminallyLazy/agent-zero --comments` and `gh pr diff <number> --repo TerminallyLazy/agent-zero`
- **List external pull requests for triage**: `gh pr list --repo TerminallyLazy/agent-zero --state open --json number,title,body,labels,author,authorAssociation,comments`, retaining only `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE`
- **Comment, label, or close**: use `gh pr comment`, `gh pr edit`, or `gh pr close` with `--repo TerminallyLazy/agent-zero`

GitHub shares one number space across issues and pull requests. Resolve a bare `#42` with `gh pr view 42 --repo TerminallyLazy/agent-zero`, falling back to `gh issue view 42 --repo TerminallyLazy/agent-zero`.

## When a skill says “publish to the issue tracker”

Create a GitHub issue in `TerminallyLazy/agent-zero`.

## When a skill says “fetch the relevant ticket”

Run `gh issue view <number> --repo TerminallyLazy/agent-zero --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is one issue with **child** issues as tickets.

- **Map**: an issue labelled `wayfinder:map`, holding Notes, Decisions-so-far, and Fog. Create it with `gh issue create --repo TerminallyLazy/agent-zero --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue. If sub-issues are unavailable, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Use a `wayfinder:<type>` label: `research`, `prototype`, `grilling`, or `task`. Once claimed, assign the ticket to the driving developer.
- **Blocking**: use GitHub’s native issue dependencies. Add an edge with `gh api --method POST repos/TerminallyLazy/agent-zero/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker’s numeric database ID. If dependencies are unavailable, use a `Blocked by: #<n>, #<n>` line at the top of the child body.
- **Frontier query**: list the map’s open children, drop assigned tickets and tickets with open blockers, and select the first remaining ticket in map order.
- **Claim**: `gh issue edit <number> --repo TerminallyLazy/agent-zero --add-assignee @me`; this is the session’s first write.
- **Resolve**: comment with the answer, close the child ticket, and append a context pointer to the map’s Decisions-so-far section.
