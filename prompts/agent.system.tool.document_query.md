### document_query
read and analyze remote/local documents get text content or answer questions
pass a single url/path or a list for multiple documents in "document"
for web documents use "http://" or "https://"" prefix
for local files "file://" prefix is optional but full path is required
if "queries" is empty tool returns document content
if "queries" is a list of strings tool returns answers
supports various formats HTML PDF Office Text etc
usage:

1 get content
~~~json
{
    "thoughts": [
        "I need to read..."
    ],
    "headline": "...",
    "tool_name": "document_query",
    "tool_args": {
        "document": "https://.../document"
    }
}
~~~

2 query document
~~~json
{
    "thoughts": [
        "I need to answer..."
    ],
    "headline": "...",
    "tool_name": "document_query",
    "tool_args": {
        "document": "https://.../document",
        "queries": [
            "What is...",
            "Who is..."
        ]
    }
}
~~~

3 query multiple documents
~~~json
{
    "thoughts": [
        "I need to compare..."
    ],
    "headline": "...",
    "tool_name": "document_query",
    "tool_args": {
        "document": [
            "https://.../document-one",
            "file:///path/to/document-two"
        ],
        "queries": [
            "Compare the main conclusions...",
            "What are the key differences..."
        ]
    }
}
~~~

4 visual document analysis
use mode "visual" for documents with complex layouts charts tables
~~~json
{
    "thoughts": [
        "This PDF has charts and tables, visual mode will help..."
    ],
    "headline": "Analyzing document visually",
    "tool_name": "document_query",
    "tool_args": {
        "document": "file:///path/to/report.pdf",
        "queries": ["What does the revenue chart show?"],
        "mode": "visual"
    }
}
~~~

5 auto mode (both text and visual analysis)
use mode "auto" when unsure which approach works best
returns both text and visual results in separate sections
~~~json
{
    "thoughts": [
        "Not sure if text or visual will work better for this document..."
    ],
    "headline": "Analyzing document with text and visual",
    "tool_name": "document_query",
    "tool_args": {
        "document": "https://example.com/paper.pdf",
        "queries": ["Summarize the methodology section"],
        "mode": "auto"
    }
}
~~~
