import tiktoken

# Cache the encoder to avoid recreating it
_encoder = None


def get_encoder():
    """Get or create the tiktoken encoder."""
    global _encoder
    if _encoder is None:
        try:
            _encoder = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        except:
            # Fallback to another encoding if cl100k_base is not available
            _encoder = tiktoken.get_encoding("p50k_base")
    return _encoder


def approximate_tokens(text: str) -> int:
    """
    Approximate the number of tokens in a text string.
    """
    if not text:
        return 0
    
    try:
        encoder = get_encoder()
        return len(encoder.encode(text))
    except Exception:
        # Fallback to a simple approximation if tiktoken fails
        return len(text) // 4  # Rough approximation: ~4 chars per token