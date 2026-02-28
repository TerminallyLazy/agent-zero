## Context Engine tools:
semantic code search, AI answers with citations, symbol graph analysis, codebase indexing

### code_search
search codebase semantically by natural language query
find code snippets, functions, classes across all files
- query: what to search for (natural language)
- limit: max results default=10
- language: filter by programming language (optional)
- under: restrict to directory path (optional)
usage:
~~~json
{
    "thoughts": [
        "Let me search the codebase for...",
    ],
    "headline": "Searching codebase for authentication logic",
    "tool_name": "code_search",
    "tool_args": {
        "query": "user authentication and login validation",
        "limit": 10,
        "language": "python"
    }
}
~~~

### context_answer
get AI-generated answer about the codebase with code citations
ask questions and get explanations grounded in actual code
- question: question about the codebase
usage:
~~~json
{
    "thoughts": [
        "I need to understand how this works...",
    ],
    "headline": "Getting explanation of database connection handling",
    "tool_name": "context_answer",
    "tool_args": {
        "question": "How does the application handle database connections and pooling?"
    }
}
~~~

### symbol_graph
find callers, callees, and importers of a symbol
trace relationships between functions, classes, and modules
- symbol: function, class, or variable name to analyze
- query_type: callers|callees|importers default=callers
usage:
~~~json
{
    "thoughts": [
        "Let me trace the dependencies of...",
    ],
    "headline": "Finding all callers of the authenticate function",
    "tool_name": "symbol_graph",
    "tool_args": {
        "symbol": "authenticate",
        "query_type": "callers"
    }
}
~~~

### context_index
index a directory for semantic code search
run this to make a new directory searchable
- path: absolute path to directory to index
usage:
~~~json
{
    "thoughts": [
        "I need to index this directory first...",
    ],
    "headline": "Indexing project directory for code search",
    "tool_name": "context_index",
    "tool_args": {
        "path": "/path/to/project"
    }
}
~~~
