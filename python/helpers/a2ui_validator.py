"""
A2UI Component Validator

Validates A2UI component definitions to ensure:
1. Only semantic hints are used (no visual properties)
2. Component structure follows A2UI standard catalog
3. No script injection or unsafe content

A2UI (Agent-to-UI) is Google's open standard for semantic UI rendering.
Agents describe WHAT to display, clients control HOW it looks.
"""

import re
from typing import Any


# Forbidden visual property names - agents should NOT specify these
FORBIDDEN_PROPERTIES = frozenset(
    [
        # Font properties
        "fontSize",
        "fontsize",
        "font_size",
        "font-size",
        "fontWeight",
        "fontweight",
        "font_weight",
        "font-weight",
        "fontFamily",
        "fontfamily",
        "font_family",
        "font-family",
        "fontStyle",
        "fontstyle",
        "font_style",
        "font-style",
        "lineHeight",
        "lineheight",
        "line_height",
        "line-height",
        "letterSpacing",
        "letterspacing",
        "letter_spacing",
        "letter-spacing",
        # Color properties
        "color",
        "textColor",
        "text_color",
        "text-color",
        "backgroundColor",
        "background_color",
        "background-color",
        "bgColor",
        "bg_color",
        "bg-color",
        "borderColor",
        "border_color",
        "border-color",
        # Spacing properties
        "padding",
        "paddingTop",
        "paddingBottom",
        "paddingLeft",
        "paddingRight",
        "margin",
        "marginTop",
        "marginBottom",
        "marginLeft",
        "marginRight",
        "rowGap",
        "columnGap",
        # Size properties
        "width",
        "height",
        "minWidth",
        "maxWidth",
        "minHeight",
        "maxHeight",
        "size",
        "flex",
        "flexGrow",
        "flexShrink",
        # Border properties
        "border",
        "borderWidth",
        "borderRadius",
        "borderStyle",
        "outline",
        "boxShadow",
        "shadow",
        # Layout properties
        "display",
        "position",
        "top",
        "left",
        "right",
        "bottom",
        "zIndex",
        "z_index",
        "z-index",
        "float",
        "clear",
        "overflow",
        "alignItems",
        "justifyContent",
        "flexDirection",
        # Visual properties
        "opacity",
        "visibility",
        "transform",
        "transition",
        "animation",
        "cursor",
        "textDecoration",
        "textAlign",
        # Raw styling
        "style",
        "css",
        "className",
        "class",
        "classes",
    ]
)

# Valid A2UI component types (Standard Catalog)
VALID_COMPONENTS = frozenset(
    [
        # Display components
        "Text",
        "Card",
        "Image",
        "Icon",
        "Video",
        # Layout components
        "Row",
        "Column",
        "List",
        "Divider",
        "Tabs",
        "TabItem",
        # Interactive components
        "Button",
        "Link",
        # Form components
        "TextField",
        "DateTimeInput",
        "ChoicePicker",
        "Slider",
        "CheckBox",
        # Data display components
        "Table",
        "Progress",
        # Container components
        "Modal",
        "Accordion",
        "AccordionItem",
    ]
)

# Valid usage hints for Text component
VALID_TEXT_HINTS = frozenset(
    [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "body",
        "caption",
        "label",
        "code",
        "subtitle",
        "overline",
        "quote",
    ]
)

# Valid usage hints for Image component
VALID_IMAGE_HINTS = frozenset(
    [
        "avatar",
        "header",
        "icon",
        "largeFeature",
        "thumbnail",
        "banner",
        "logo",
        "background",
    ]
)

# Valid usage hints for Button component
VALID_BUTTON_HINTS = frozenset(
    [
        "primary",
        "secondary",
        "tertiary",
        "danger",
        "warning",
        "success",
        "outlined",
        "text",
        "icon",
    ]
)


class A2UIValidationError(Exception):
    """Raised when A2UI component validation fails."""

    pass


class A2UIValidationWarning:
    """Non-fatal validation warning."""

    def __init__(self, message: str, path: str):
        self.message = message
        self.path = path

    def __str__(self):
        return f"{self.path}: {self.message}"


class ValidationResult:
    """Result of validation with errors and warnings."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[A2UIValidationWarning] = []

    def add_error(self, message: str):
        self.errors.append(message)

    def add_warning(self, message: str, path: str):
        self.warnings.append(A2UIValidationWarning(message, path))

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def validate_component(
    component: dict, path: str = "root", strict: bool = False
) -> dict:
    """
    Validate an A2UI component definition.

    Args:
        component: The component definition dict
        path: Current path for error messages

    Returns:
        The validated component (unchanged if valid)

    Raises:
        A2UIValidationError: If validation fails
    """
    if not isinstance(component, dict):
        raise A2UIValidationError(
            f"Component at {path} must be a dict, got {type(component).__name__}"
        )

    if not component:
        raise A2UIValidationError(f"Component at {path} is empty")

    # Get the component type (first key that's a valid component)
    component_types = [k for k in component.keys() if k in VALID_COMPONENTS]

    if not component_types:
        _check_forbidden_properties(component, path, strict)

        for key, value in component.items():
            if isinstance(value, dict):
                validate_component(value, f"{path}.{key}", strict)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        validate_component(item, f"{path}.{key}[{i}]", strict)
        return component

    component_type = component_types[0]
    props = component[component_type]

    if props is None:
        return component

    if not isinstance(props, dict):
        if strict:
            raise A2UIValidationError(
                f"Component {component_type} at {path} props must be a dict, "
                f"got {type(props).__name__}"
            )
        return component

    _check_forbidden_properties(props, f"{path}.{component_type}", strict)
    _validate_usage_hint(component_type, props, path, strict)

    if "children" in props:
        _validate_children(
            props["children"], f"{path}.{component_type}.children", strict
        )

    if "items" in props:
        items = props["items"]
        if isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    validate_component(
                        item, f"{path}.{component_type}.items[{i}]", strict
                    )

    if component_type == "Table":
        _validate_table(props, f"{path}.{component_type}", strict)

    return component


def _check_forbidden_properties(props: dict, path: str, strict: bool = False) -> None:
    """Check for forbidden visual properties."""
    for key in props.keys():
        key_normalized = key.lower().replace("-", "").replace("_", "")

        for forbidden in FORBIDDEN_PROPERTIES:
            forbidden_normalized = forbidden.lower().replace("-", "").replace("_", "")
            if key_normalized == forbidden_normalized:
                if strict:
                    raise A2UIValidationError(
                        f"Forbidden visual property '{key}' at {path}. "
                        f"A2UI uses semantic hints (usageHint), not visual properties. "
                        f"The client controls all styling."
                    )
                return


def _validate_usage_hint(
    component_type: str, props: dict, path: str, strict: bool = False
) -> None:
    """Validate usage hints for specific component types."""
    if "usageHint" not in props:
        return

    hint = props["usageHint"]

    if component_type == "Text":
        if hint not in VALID_TEXT_HINTS:
            if strict:
                raise A2UIValidationError(
                    f"Invalid usageHint '{hint}' for Text at {path}. "
                    f"Valid hints: {', '.join(sorted(VALID_TEXT_HINTS))}"
                )
    elif component_type == "Image":
        if hint not in VALID_IMAGE_HINTS:
            if strict:
                raise A2UIValidationError(
                    f"Invalid usageHint '{hint}' for Image at {path}. "
                    f"Valid hints: {', '.join(sorted(VALID_IMAGE_HINTS))}"
                )
    elif component_type == "Button":
        if hint not in VALID_BUTTON_HINTS:
            if strict:
                raise A2UIValidationError(
                    f"Invalid usageHint '{hint}' for Button at {path}. "
                    f"Valid hints: {', '.join(sorted(VALID_BUTTON_HINTS))}"
                )


def _validate_children(children: Any, path: str, strict: bool = False) -> None:
    """Validate children property."""
    if children is None:
        return

    if isinstance(children, dict):
        if "explicitList" in children:
            ids = children.get("explicitList", [])
            if not isinstance(ids, list):
                if strict:
                    raise A2UIValidationError(f"explicitList at {path} must be a list")
        elif "template" in children:
            pass
        else:
            validate_component(children, path, strict)
    elif isinstance(children, list):
        for i, child in enumerate(children):
            if isinstance(child, dict):
                validate_component(child, f"{path}[{i}]", strict)
    elif isinstance(children, str):
        pass
    elif strict:
        raise A2UIValidationError(
            f"children at {path} must be a dict, list, string, or null, "
            f"got {type(children).__name__}"
        )


def _validate_table(props: dict, path: str, strict: bool = False) -> list[str]:
    """Validate Table component structure. Returns list of warnings."""
    warnings = []
    headers = props.get("headers")
    rows = props.get("rows")

    if headers is not None and not isinstance(headers, list):
        if strict:
            raise A2UIValidationError(f"Table headers at {path} must be a list")
        warnings.append(f"Table headers at {path} should be a list")

    if rows is not None:
        if not isinstance(rows, list):
            if strict:
                raise A2UIValidationError(f"Table rows at {path} must be a list")
            warnings.append(f"Table rows at {path} should be a list")
        else:
            for i, row in enumerate(rows):
                if not isinstance(row, list):
                    if strict:
                        raise A2UIValidationError(
                            f"Table row at {path}.rows[{i}] must be a list"
                        )
                    warnings.append(f"Table row at {path}.rows[{i}] should be a list")

    return warnings


def sanitize_text_content(text: Any) -> str:
    """
    Sanitize text content to prevent XSS and script injection.

    Args:
        text: Text to sanitize (will be converted to string)

    Returns:
        Sanitized text string
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # Remove script tags and their contents
    text = re.sub(
        r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL
    )

    # Remove javascript: URLs
    text = re.sub(r"javascript:", "", text, flags=re.IGNORECASE)

    # Remove event handlers (onclick, onerror, etc.)
    text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+on\w+\s*=\s*\S+", "", text, flags=re.IGNORECASE)

    # Remove data: URLs that could contain scripts
    text = re.sub(r"data:\s*text/html", "data:text/plain", text, flags=re.IGNORECASE)

    return text


def extract_string(value: Any) -> str:
    """
    Extract a string value from an A2UI text representation.

    A2UI text can be:
    - A plain string
    - {"literalString": "text"}
    - {"dataBinding": "path.to.data"}

    Args:
        value: The value to extract string from

    Returns:
        Extracted string (sanitized)
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return sanitize_text_content(value)

    if isinstance(value, dict):
        if "literalString" in value:
            return sanitize_text_content(value["literalString"])
        if "dataBinding" in value:
            # Return placeholder for data binding
            return f"{{{{ {value['dataBinding']} }}}}"

    return sanitize_text_content(str(value))


def validate_and_extract_fallback(
    component: dict, default_fallback: str = "", strict: bool = True
) -> str:
    """
    Validate a component and extract a text fallback.

    This is useful for generating fallback text when A2UI rendering is disabled.

    Args:
        component: The component to validate and extract from
        default_fallback: Default fallback if extraction fails
        strict: Use strict validation (default True for fallback extraction)

    Returns:
        Extracted fallback text
    """
    try:
        validate_component(component, strict=strict)
    except A2UIValidationError:
        return default_fallback

    # Try to extract meaningful text from common patterns
    texts = []
    _extract_texts_recursive(component, texts)

    if texts:
        return " | ".join(texts[:5])  # Limit to first 5 text elements

    return default_fallback


def _extract_texts_recursive(obj: Any, texts: list, max_depth: int = 10) -> None:
    """Recursively extract text content from a component tree."""
    if max_depth <= 0 or not isinstance(obj, dict):
        return

    # Check for Text component
    if "Text" in obj:
        text_props = obj["Text"]
        if isinstance(text_props, dict) and "text" in text_props:
            extracted = extract_string(text_props["text"])
            if extracted:
                texts.append(extracted)

    # Check for Card title
    if "Card" in obj:
        card_props = obj["Card"]
        if isinstance(card_props, dict) and "title" in card_props:
            extracted = extract_string(card_props["title"])
            if extracted:
                texts.append(extracted)

    # Check for Button label
    if "Button" in obj:
        button_props = obj["Button"]
        if isinstance(button_props, dict) and "label" in button_props:
            extracted = extract_string(button_props["label"])
            if extracted:
                texts.append(f"[{extracted}]")

    # Recurse into children and other nested structures
    for key, value in obj.items():
        if isinstance(value, dict):
            _extract_texts_recursive(value, texts, max_depth - 1)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _extract_texts_recursive(item, texts, max_depth - 1)
