## Context Engine memory and search tools:
store and retrieve development knowledge, find tests and callers

### ce_memory_store
store development knowledge notes decisions in Context Engine
tags optional comma-separated for categorization
usage:
~~~json
{
    "thoughts": [
        "I should save this finding for future reference...",
    ],
    "headline": "Storing development knowledge in Context Engine",
    "tool_name": "ce_memory_store",
    "tool_args": {
        "content": "The authentication module uses JWT tokens with 24h expiry. Refresh tokens are stored in httponly cookies.",
        "tags": "auth,jwt,security"
    }
}
~~~

### ce_memory_find
search stored knowledge and memories by semantic query
- limit: max results default=5
usage:
~~~json
{
    "thoughts": [
        "Let me search my stored knowledge about...",
    ],
    "headline": "Searching Context Engine memory for authentication details",
    "tool_name": "ce_memory_find",
    "tool_args": {
        "query": "authentication token expiry and refresh strategy",
        "limit": 5
    }
}
~~~

### search_tests
find test files for a given function or class name
usage:
~~~json
{
    "thoughts": [
        "I need to find tests for this function before modifying it...",
    ],
    "headline": "Finding tests for the UserService class",
    "tool_name": "search_tests",
    "tool_args": {
        "symbol": "UserService"
    }
}
~~~

### search_callers
find all callers of a function or class across the codebase
usage:
~~~json
{
    "thoughts": [
        "Before refactoring, I need to know what calls this function...",
    ],
    "headline": "Finding callers of the authenticate function",
    "tool_name": "search_callers",
    "tool_args": {
        "symbol": "authenticate"
    }
}
~~~
