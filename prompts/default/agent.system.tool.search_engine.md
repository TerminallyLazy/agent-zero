### search_engine:
provide query arg get search results
returns list urls titles descriptions

**After getting search results:**
- Use browser_agent to visit relevant URLs and extract content
- Include any images from articles, news stories, or web pages in your response
- Look for featured images, cover photos, news photos, product images, etc.
- Always include visual content when summarizing articles or news

**Example usage**:
~~~json
{
    "thoughts": [
        "I need to search for recent news about...",
    ],
    "tool_name": "search_engine",
    "tool_args": {
        "query": "latest news about AI developments 2024",
    }
}
~~~