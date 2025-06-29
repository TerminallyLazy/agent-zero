import re
from python.helpers.api import ApiHandler
from flask import Request, Response

from python.helpers import runtime, settings, kokoro_tts

class Synthesize(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        text = input.get("text", "")
        ctxid = input.get("ctxid", "")

        context = self.get_context(ctxid)
        if await kokoro_tts.is_downloading():
            context.log.log(type="info", content="Kokoro TTS model is currently being downloaded, please wait...")

        try:
            # Clean and split text into sentences
            cleaned_text = self._clean_text(text)
            sentences = self._split_sentences(cleaned_text)
            
            # Generate audio for all sentences
            audio_base64 = await kokoro_tts.synthesize_sentences(sentences)
            return {"audio": audio_base64, "success": True, "sentence_count": len(sentences)}
        except Exception as e:
            return {"error": str(e), "success": False}
    
    def _clean_text(self, text: str) -> str:
        """Clean text by removing markdown, tables, code blocks, and other formatting"""
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]*`', '', text)
        
        # Remove markdown links
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove markdown formatting
        text = re.sub(r'[*_#]+', '', text)
        
        # Remove tables (basic cleanup)
        text = re.sub(r'\|[^\n]*\|', '', text)
        
        # Remove extra whitespace and newlines
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # Remove URLs
        text = re.sub(r'https?://[^\s]+', '', text)
        
        # Remove email addresses
        text = re.sub(r'\S+@\S+', '', text)
        
        return text.strip()
    
    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences"""
        # Split on sentence endings
        sentences = re.split(r'[.!?]+', text)
        
        # Filter out empty sentences and normalize
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 3:  # Skip very short fragments
                # Ensure sentence ends with period for better speech
                if not sentence.endswith(('.', '!', '?')):
                    sentence += '.'
                cleaned_sentences.append(sentence)
        
        return cleaned_sentences