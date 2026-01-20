### browser_agent:

Automates browser interactions using agent-browser CLI.
The message argument contains task instructions - be precise and descriptive.
The reset argument spawns a new browser session (use sparingly).
The headed argument shows the browser window for user intervention (CAPTCHA, login).

Navigation: Opens URLs and navigates pages
Interaction: Clicks, fills forms, selects options using accessibility refs
Observation: Takes snapshots to identify interactive elements
Downloads: Files saved to /a0/tmp/downloads

usage:
```json
{
  "thoughts": ["I need to browse to a website..."],
  "headline": "Opening browser to visit website",
  "tool_name": "browser_agent",
  "tool_args": {
    "message": "Open https://example.com and describe the main content",
    "reset": "true"
  }
}
```

```json
{
  "thoughts": ["Page has a login form, I need to fill it..."],
  "headline": "Continuing browser session to fill form",
  "tool_name": "browser_agent",
  "tool_args": {
    "message": "Fill the email field with user@example.com and click submit",
    "reset": "false"
  }
}
```

```json
{
  "thoughts": ["There's a CAPTCHA, user needs to solve it..."],
  "headline": "Opening visible browser for user intervention",
  "tool_name": "browser_agent",
  "tool_args": {
    "message": "Open https://example.com/login - user will solve CAPTCHA",
    "reset": "true",
    "headed": "true"
  }
}
```
