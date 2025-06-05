### response:
final answer to user
ends task processing use only when done or no task active
put result in text arg
always write full file paths

**For responses with images:**
- Use `<img src="url" alt="description" width="400px" />` for image URLs
- Use `<image>base64data</image>` for base64-encoded images
- Images will be automatically displayed and clickable in the chat interface
- Always include descriptive alt text and context

usage:
~~~json
{
    "thoughts": [
        "...",
    ],
    "tool_name": "response",
    "tool_args": {
        "text": "Answer to the user with optional images: <img src='https://example.com/image.jpg' alt='Description' width='400px' />",
    }
}
~~~