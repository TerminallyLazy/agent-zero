import re


def sanitize_string(text: str) -> str:
    """
    Sanitize a string by removing control characters and normalizing whitespace.
    """
    if not text:
        return ""
    
    # Remove control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Normalize whitespace (but preserve newlines)
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\t+', '\t', text)
    
    return text.strip()