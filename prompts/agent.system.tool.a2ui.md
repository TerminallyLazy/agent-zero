### a2ui_component:
Renders rich, interactive UI components using A2UI (Agent-to-UI) format.
A2UI uses an adjacency list format where components reference each other by ID.

!!! Always provide fallback_text for accessibility
!!! Use semantic hints, NOT visual properties (no fontSize, color, padding)

#### Arguments:
 *  "surface_id" (string) : Unique identifier for this UI surface.
 *  "components" (array) : Array of {id, component} entries (adjacency list format).
 *  "data_model" (object) : Optional data for dynamic bindings.
 *  "fallback_text" (string) : Plain text fallback for non-A2UI clients.
 *  "break_loop" (Optional, boolean) : Whether to end the response loop after rendering.

#### Component Structure (Adjacency List):
Components are defined as an array where each entry has an `id` and a `component`:
```json
[
  {"id": "root", "component": {"Card": {"child": "content"}}},
  {"id": "content", "component": {"Column": {"children": {"explicitList": ["title", "body"]}}}}
]
```

#### Text Values:
Text can be literal or bound to data:
- Literal: `{"literalString": "Hello"}` or `{"literalNumber": 42}`
- Data binding: `{"path": "/user/name"}` resolves from data_model

#### Available Components:

##### Text - Display text with semantic purpose
```json
{"id": "title", "component": {"Text": {"text": {"literalString": "Hello"}, "usageHint": "h1"}}}
```
Valid usageHints: h1, h2, h3, h4, h5, h6, body, caption, label, code, subtitle, overline, quote

##### Card - Group content with optional title
```json
{"id": "card", "component": {"Card": {"title": {"literalString": "Status"}, "child": "card-content"}}}
```

##### Button - Interactive button with action
Buttons use `child` to reference their label component:
```json
{"id": "btn", "component": {"Button": {"child": "btn-label", "action": {"name": "submit"}}}},
{"id": "btn-label", "component": {"Text": {"text": {"literalString": "Submit"}, "usageHint": "label"}}}
```

Button with context data for the action:
```json
{"id": "btn", "component": {"Button": {
  "child": "btn-label",
  "action": {
    "name": "delete_item",
    "context": [
      {"key": "item_id", "value": {"path": "/selected_item/id"}},
      {"key": "confirmed", "value": {"literalBoolean": true}}
    ]
  }
}}}
```

##### Row/Column - Layout containers
```json
{"id": "row", "component": {"Row": {"children": {"explicitList": ["item1", "item2"]}, "gap": "medium", "alignment": "center"}}}
```
Layout hints: gap (small/medium/large), alignment (start/center/end/baseline/stretch), distribution (spaceBetween/spaceAround/spaceEvenly)

##### List - Display items
```json
{"id": "list", "component": {"List": {"children": {"explicitList": ["item1", "item2"]}}}}
```

##### Table - Structured data display
```json
{"id": "table", "component": {"Table": {"headers": ["Name", "Status"], "rows": [["Server A", "Online"]]}}}
```

##### Progress - Show progress indicator
```json
{"id": "prog", "component": {"Progress": {"value": 75, "max": 100, "label": {"literalString": "Loading..."}}}}
```

##### Image - Display images
```json
{"id": "img", "component": {"Image": {"url": {"literalString": "https://..."}, "usageHint": "thumbnail", "altText": {"literalString": "Preview"}}}}
```

##### TextField - Text input
```json
{"id": "input", "component": {"TextField": {"label": {"literalString": "Name"}, "placeholder": {"literalString": "Enter name"}}}}
```

##### CheckBox - Boolean input
```json
{"id": "check", "component": {"CheckBox": {"label": {"literalString": "Accept terms"}, "checked": false}}}
```

#### Usage examples:

##### 1: Status Card with Progress
```json
{
    "thoughts": ["Display task progress in a card"],
    "tool_name": "a2ui_component",
    "tool_args": {
        "surface_id": "task_status",
        "components": [
            {"id": "root", "component": {"Card": {"title": {"literalString": "Task Progress"}, "child": "content"}}},
            {"id": "content", "component": {"Column": {"children": {"explicitList": ["progress", "status"]}}}},
            {"id": "progress", "component": {"Progress": {"value": 60, "max": 100}}},
            {"id": "status", "component": {"Text": {"text": {"literalString": "Processing files..."}, "usageHint": "body"}}}
        ],
        "fallback_text": "Task Progress: 60% - Processing files..."
    }
}
```

##### 2: Data Table
```json
{
    "thoughts": ["Present server data in a table"],
    "tool_name": "a2ui_component",
    "tool_args": {
        "surface_id": "server_status",
        "components": [
            {"id": "root", "component": {"Card": {"title": {"literalString": "Server Status"}, "child": "table"}}},
            {"id": "table", "component": {"Table": {
                "headers": ["Server", "Status", "Uptime"],
                "rows": [["Server A", "Online", "99.9%"], ["Server B", "Offline", "0%"]]
            }}}
        ],
        "fallback_text": "Server Status:\n- Server A: Online (99.9%)\n- Server B: Offline"
    }
}
```

##### 3: Action Buttons
```json
{
    "thoughts": ["Present action choices to user"],
    "tool_name": "a2ui_component",
    "tool_args": {
        "surface_id": "user_actions",
        "components": [
            {"id": "root", "component": {"Card": {"title": {"literalString": "Choose Action"}, "child": "content"}}},
            {"id": "content", "component": {"Column": {"children": {"explicitList": ["prompt", "buttons"]}}}},
            {"id": "prompt", "component": {"Text": {"text": {"literalString": "What would you like to do?"}, "usageHint": "body"}}},
            {"id": "buttons", "component": {"Row": {"children": {"explicitList": ["btn-continue", "btn-cancel"]}, "gap": "medium"}}},
            {"id": "btn-continue", "component": {"Button": {"child": "btn-continue-text", "action": {"name": "continue"}, "primary": true}}},
            {"id": "btn-continue-text", "component": {"Text": {"text": {"literalString": "Continue"}, "usageHint": "label"}}},
            {"id": "btn-cancel", "component": {"Button": {"child": "btn-cancel-text", "action": {"name": "cancel"}}}},
            {"id": "btn-cancel-text", "component": {"Text": {"text": {"literalString": "Cancel"}, "usageHint": "label"}}}
        ],
        "fallback_text": "Choose Action:\nWhat would you like to do?\n[Continue] [Cancel]"
    }
}
```

##### 4: Dynamic Data Binding
```json
{
    "thoughts": ["Display user info from data model"],
    "tool_name": "a2ui_component",
    "tool_args": {
        "surface_id": "user_profile",
        "components": [
            {"id": "root", "component": {"Card": {"title": {"literalString": "Profile"}, "child": "content"}}},
            {"id": "content", "component": {"Column": {"children": {"explicitList": ["name", "email"]}}}},
            {"id": "name", "component": {"Text": {"text": {"path": "/user/name"}, "usageHint": "h2"}}},
            {"id": "email", "component": {"Text": {"text": {"path": "/user/email"}, "usageHint": "body"}}}
        ],
        "data_model": {
            "user": {"name": "John Doe", "email": "john@example.com"}
        },
        "fallback_text": "Profile: John Doe (john@example.com)"
    }
}
```

#### Handling User Actions

When users click buttons, actions are sent back as messages:
```
[A2UI_ACTION:action_name] | Component: component_id | Surface: surface_id | Data: {...}
```

Example incoming action:
```
[A2UI_ACTION:delete_item] | Component: btn-delete | Surface: item_list | Data: {'item_id': '123'}
```

How to handle:
1. Parse the action name (e.g., "delete_item")
2. Use the surface_id to identify context
3. The Data field contains context values from the button's action definition
4. Respond appropriately - update the UI, execute logic, or ask for confirmation
