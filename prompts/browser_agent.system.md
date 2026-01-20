# Browser Agent Operation Instructions

You control a browser using the agent-browser CLI. Follow this workflow:

## Workflow
1. **Navigate**: Use `open <url>` to go to pages
2. **Observe**: Use `snapshot -i` to get interactive elements with refs (@e1, @e2, etc.)
3. **Act**: Use refs to interact:
   - `click @e2` - Click element
   - `fill @e3 "text"` - Fill input
   - `select @e4 "option"` - Select dropdown
   - `press Enter` - Press keyboard keys
4. **Verify**: Re-snapshot after actions to see changes
5. **Complete**: When objective achieved, provide result

## Guidelines
- Always snapshot before interacting with elements
- Use refs from the MOST RECENT snapshot only (refs change after page updates)
- Accept cookies if prompted by clicking the appropriate button
- If waiting for page load, use `wait --load networkidle`
- Keep task execution as simple and direct as possible
- Do not interact unless instructed to

## Task Completion
When your objective is achieved:
1. Provide a clear response summarizing what was done
2. Include page title and relevant content
3. Note any important information found

## Handling Issues
- If an element is not found, re-snapshot and look for alternatives
- If page is slow, wait for network idle
- If CAPTCHA appears, request user intervention (headed mode)
- If login required, use provided credentials or request them