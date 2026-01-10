### canvas:

visual workspace for creating and previewing web content
use to write html/css/js files and view them in real browser
query dom elements validate your output capture screenshots

actions:
- start: start workspace (optional path for directory)
- stop: stop workspace
- navigate: go to path within workspace (e.g., /app, /dashboard)
- write: write file to workspace (path + content required)
- read: read file from workspace
- list: list files in workspace
- eval: run javascript in page
- query: query single dom element (selector + mode: text|outer_html)
- query_all: query all matching elements
- screenshot: capture screenshot (optional selector for specific element)
- click: click element
- type: type text into element (selector + text, optional clear=true)
- wait: wait for element state (visible|hidden|attached|detached)
- reload: force page reload
- status: get current canvas status

typical workflow:
1. start canvas
2. write html/css/js files
3. navigate to view content
4. query dom to validate
5. screenshot to capture result

usage:
```json
{
  "thoughts": ["I need to create a web page preview"],
  "headline": "Starting canvas workspace",
  "tool_name": "canvas",
  "tool_args": {
    "action": "start"
  }
}
```

```json
{
  "thoughts": ["Writing the HTML file to canvas"],
  "headline": "Writing index.html to workspace",
  "tool_name": "canvas",
  "tool_args": {
    "action": "write",
    "path": "index.html",
    "content": "<!DOCTYPE html><html><head><title>My Page</title></head><body><h1>Hello World</h1></body></html>"
  }
}
```

```json
{
  "thoughts": ["Checking if the heading rendered correctly"],
  "headline": "Querying h1 element text",
  "tool_name": "canvas",
  "tool_args": {
    "action": "query",
    "selector": "h1",
    "mode": "text"
  }
}
```

```json
{
  "thoughts": ["Capturing final result"],
  "headline": "Taking screenshot of canvas",
  "tool_name": "canvas",
  "tool_args": {
    "action": "screenshot"
  }
}
```
