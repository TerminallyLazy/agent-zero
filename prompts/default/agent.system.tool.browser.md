### browser_agent:

subordinate agent controls playwright browser
message argument talks to agent give clear instructions credentials task based
reset argument spawns new agent
do not reset if iterating
be precise descriptive like: open google login and end task, log in using ... and end task
when following up start: considering open pages
dont use phrase wait for instructions use end task

**When browsing web content with images:**
- Ask the browser agent to extract image URLs from articles, news stories, or web pages
- Include these images in your response using `<img>` tags
- This includes: article cover photos, news images, product photos, screenshots, etc.
- Example: "Extract the main article image URL and provide it to me so I can include it in my response"

usage:
```json
{
  "thoughts": ["I need to log in to..."],
  "tool_name": "browser_agent",
  "tool_args": {
    "message": "Open and log me into...",
    "reset": "true"
  }
}
```

```json
{
  "thoughts": ["I need to log in to..."],
  "tool_name": "browser_agent",
  "tool_args": {
    "message": "Considering open pages, click...",
    "reset": "false"
  }
}
```
