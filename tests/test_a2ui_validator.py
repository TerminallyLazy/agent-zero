#!/usr/bin/env python3

import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from python.helpers.a2ui_validator import (
    validate_component,
    A2UIValidationError,
    sanitize_text_content,
    extract_string,
    validate_and_extract_fallback,
)


class TestValidateComponent:
    def test_valid_text_component(self):
        component = {"Text": {"text": "Hello World", "usageHint": "h1"}}
        result = validate_component(component)
        assert result == component

    def test_valid_card_with_children(self):
        component = {
            "Card": {
                "title": "Test Card",
                "children": [{"Text": {"text": "Content", "usageHint": "body"}}],
            }
        }
        result = validate_component(component)
        assert result == component

    def test_valid_button_component(self):
        component = {"Button": {"label": "Click Me", "usageHint": "primary"}}
        result = validate_component(component)
        assert result == component

    def test_valid_table_component(self):
        component = {
            "Table": {
                "headers": ["Name", "Value"],
                "rows": [["Item 1", "100"], ["Item 2", "200"]],
            }
        }
        result = validate_component(component)
        assert result == component

    def test_valid_progress_component(self):
        component = {"Progress": {"value": 75, "max": 100, "label": "Loading"}}
        result = validate_component(component)
        assert result == component

    def test_valid_list_component(self):
        component = {
            "List": {
                "items": [{"Text": {"text": "Item 1"}}, {"Text": {"text": "Item 2"}}]
            }
        }
        result = validate_component(component)
        assert result == component

    def test_valid_row_column_layout(self):
        component = {
            "Row": {
                "children": [
                    {"Column": {"children": [{"Text": {"text": "Left"}}]}},
                    {"Column": {"children": [{"Text": {"text": "Right"}}]}},
                ]
            }
        }
        result = validate_component(component)
        assert result == component

    def test_valid_layout_with_semantic_hints(self):
        component = {
            "Column": {
                "children": [{"Text": {"text": "Content"}}],
                "gap": "small",
                "alignment": "center",
                "distribution": "spaceAround",
            }
        }
        result = validate_component(component)
        assert result == component

    def test_valid_divider_null_props(self):
        component = {"Divider": None}
        result = validate_component(component)
        assert result == component


class TestForbiddenProperties:
    def test_rejects_font_size_strict(self):
        component = {"Text": {"text": "Hello", "fontSize": "16px"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)

    def test_allows_font_size_lenient(self):
        component = {"Text": {"text": "Hello", "fontSize": "16px"}}
        result = validate_component(component, strict=False)
        assert result == component

    def test_rejects_color_strict(self):
        component = {"Text": {"text": "Hello", "color": "red"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)

    def test_rejects_background_color_strict(self):
        component = {"Card": {"title": "Test", "backgroundColor": "#fff"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)

    def test_rejects_padding_strict(self):
        component = {"Card": {"title": "Test", "padding": "10px"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)

    def test_rejects_width_strict(self):
        component = {"Image": {"url": "test.png", "width": "100px"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)

    def test_rejects_style_strict(self):
        component = {"Button": {"label": "Click", "style": {"color": "red"}}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)

    def test_rejects_css_strict(self):
        component = {"Text": {"text": "Hello", "css": "color: red;"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)

    def test_rejects_class_name_strict(self):
        component = {"Card": {"title": "Test", "className": "custom-class"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Forbidden visual property" in str(exc_info.value)


class TestUsageHints:
    def test_valid_text_hints(self):
        valid_hints = [
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
        for hint in valid_hints:
            component = {"Text": {"text": "Test", "usageHint": hint}}
            result = validate_component(component)
            assert result == component

    def test_invalid_text_hint_strict(self):
        component = {"Text": {"text": "Test", "usageHint": "invalid_hint"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Invalid usageHint" in str(exc_info.value)

    def test_invalid_text_hint_lenient(self):
        component = {"Text": {"text": "Test", "usageHint": "invalid_hint"}}
        result = validate_component(component, strict=False)
        assert result == component

    def test_valid_button_hints(self):
        valid_hints = [
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
        for hint in valid_hints:
            component = {"Button": {"label": "Test", "usageHint": hint}}
            result = validate_component(component)
            assert result == component

    def test_invalid_button_hint_strict(self):
        component = {"Button": {"label": "Test", "usageHint": "fancy"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Invalid usageHint" in str(exc_info.value)

    def test_valid_image_hints(self):
        valid_hints = [
            "avatar",
            "header",
            "icon",
            "largeFeature",
            "thumbnail",
            "banner",
            "logo",
            "background",
        ]
        for hint in valid_hints:
            component = {"Image": {"url": "test.png", "usageHint": hint}}
            result = validate_component(component)
            assert result == component

    def test_invalid_image_hint_strict(self):
        component = {"Image": {"url": "test.png", "usageHint": "huge"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "Invalid usageHint" in str(exc_info.value)


class TestTableValidation:
    def test_rejects_non_list_headers_strict(self):
        component = {"Table": {"headers": "Name, Value", "rows": []}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "headers" in str(exc_info.value).lower()

    def test_allows_non_list_headers_lenient(self):
        component = {"Table": {"headers": "Name, Value", "rows": []}}
        result = validate_component(component, strict=False)
        assert result == component

    def test_rejects_non_list_rows_strict(self):
        component = {"Table": {"headers": ["A"], "rows": "not a list"}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "rows" in str(exc_info.value).lower()

    def test_allows_non_list_rows_lenient(self):
        component = {"Table": {"headers": ["A"], "rows": "not a list"}}
        result = validate_component(component, strict=False)
        assert result == component

    def test_rejects_non_list_row_item_strict(self):
        component = {"Table": {"headers": ["A"], "rows": ["not a list"]}}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "row" in str(exc_info.value).lower()


class TestEdgeCases:
    def test_rejects_non_dict_component(self):
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component("not a dict")
        assert "must be a dict" in str(exc_info.value)

    def test_rejects_empty_component(self):
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component({})
        assert "empty" in str(exc_info.value)

    def test_rejects_non_dict_props_strict(self):
        component = {"Text": "not a dict"}
        with pytest.raises(A2UIValidationError) as exc_info:
            validate_component(component, strict=True)
        assert "props must be a dict" in str(exc_info.value)

    def test_allows_non_dict_props_lenient(self):
        component = {"Text": "not a dict"}
        result = validate_component(component, strict=False)
        assert result == component


class TestSanitizeTextContent:
    def test_removes_script_tags(self):
        result = sanitize_text_content("<script>alert('xss')</script>Hello")
        assert "<script>" not in result
        assert "Hello" in result

    def test_removes_javascript_urls(self):
        result = sanitize_text_content("javascript:alert('xss')")
        assert "javascript:" not in result

    def test_removes_event_handlers(self):
        result = sanitize_text_content('<div onclick="alert(1)">test</div>')
        assert "onclick" not in result

    def test_preserves_safe_content(self):
        result = sanitize_text_content("Hello, World!")
        assert result == "Hello, World!"

    def test_handles_none(self):
        result = sanitize_text_content(None)
        assert result == ""

    def test_converts_non_string(self):
        result = sanitize_text_content(123)
        assert result == "123"


class TestExtractString:
    def test_plain_string(self):
        result = extract_string("Hello")
        assert result == "Hello"

    def test_literal_string_format(self):
        result = extract_string({"literalString": "Hello"})
        assert result == "Hello"

    def test_data_binding_format(self):
        result = extract_string({"dataBinding": "user.name"})
        assert "user.name" in result

    def test_none_value(self):
        result = extract_string(None)
        assert result == ""


class TestValidateAndExtractFallback:
    def test_extracts_text_from_valid_component(self):
        component = {"Text": {"text": "Hello World"}}
        result = validate_and_extract_fallback(component, "default")
        assert "Hello World" in result

    def test_extracts_card_title(self):
        component = {"Card": {"title": "My Card", "children": []}}
        result = validate_and_extract_fallback(component, "default")
        assert "My Card" in result

    def test_extracts_button_label(self):
        component = {"Button": {"label": "Click Me"}}
        result = validate_and_extract_fallback(component, "default")
        assert "Click Me" in result

    def test_returns_default_on_invalid(self):
        component = {"Text": {"text": "Hello", "color": "red"}}
        result = validate_and_extract_fallback(component, "fallback text")
        assert result == "fallback text"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
