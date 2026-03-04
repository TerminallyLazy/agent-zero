# A0 Design Studio

AI-powered image generation and visual editing studio for Agent Zero.

## Features

- Multi-provider image generation via LiteLLM (OpenAI DALL-E, Google Imagen, Azure, Stability AI)
- Full canvas editor with drawing tools, layers, and mask painting
- Vision-model-based image editing (Gemini, GPT-4V, Claude)
- Agent tool integration for generating images via natural language
- Image gallery with workspace storage

## Configuration

Configure under **Settings > External Services > A0 Design Studio**:

- **Image Generation Model**: LiteLLM model string (e.g., `openai/dall-e-3`)
- **Image Edit Model**: Vision-capable model (e.g., `google/gemini-2.0-flash`)
- **Default Size**: Image dimensions (e.g., `1024x1024`)
