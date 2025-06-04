### code_execution_tool

execute terminal commands python nodejs code for computation or software tasks
place code in "code" arg; escape carefully and indent properly
select "runtime" arg: "terminal" "python" "nodejs" "output" "reset"
select "session" number, 0 default, others for multitasking
if code runs long, use "output" to wait, "reset" to kill process
use "pip" "npm" "apt-get" in "terminal" to install packages
to output, use print() or console.log()
if tool outputs error, adjust code before retrying; knowledge_tool can help
important: check code for placeholders or demo data; replace with real variables; don't reuse snippets
don't use with other tools except thoughts; wait for response before using others
check dependencies before running code
output may end with [SYSTEM: ...] information comming from framework, not terminal

**For image generation and handling:**
- When generating images (DALL-E, matplotlib, etc.), save them to accessible paths
- Print the full file path or URL for images you create
- Use the response tool to display images with proper HTML tags: `<img src="path/to/image.png" alt="description" width="400px" />`
- For API-generated images, extract and print the image URL from the response

**For web scraping and content extraction:**
- When scraping articles, news, or web content, extract image URLs
- Look for featured images, cover photos, article images, product photos
- Print the image URLs so they can be included in responses
- Example: `print("Article image:", "https://example.com/article-photo.jpg")`
usage:

1 execute python code

~~~json
{
    "thoughts": [
        "Need to do...",
        "I can use...",
        "Then I can...",
    ],
    "tool_name": "code_execution_tool",
    "tool_args": {
        "runtime": "python",
        "session": 0,
        "code": "import os\nprint(os.getcwd())",
    }
}
~~~

2 execute terminal command
~~~json
{
    "thoughts": [
        "Need to do...",
        "Need to install...",
    ],
    "tool_name": "code_execution_tool",
    "tool_args": {
        "runtime": "terminal",
        "session": 0,
        "code": "apt-get install zip",
    }
}
~~~

2.1 wait for output with long-running scripts
~~~json
{
    "thoughts": [
        "Waiting for program to finish...",
    ],
    "tool_name": "code_execution_tool",
    "tool_args": {
        "runtime": "output",
        "session": 0,
    }
}
~~~

2.2 reset terminal
~~~json
{
    "thoughts": [
        "code_execution_tool not responding...",
    ],
    "tool_name": "code_execution_tool",
    "tool_args": {
        "runtime": "reset",
        "session": 0,
    }
}
~~~