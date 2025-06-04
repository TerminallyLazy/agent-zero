## "Multimodal (Vision) Agent Tools" available:

### vision_load:
load image data to LLM
use paths arg for attachments
multiple images if needed
only bitmaps supported convert first if needed

## Media Generation Guidelines
When working with visual content:
1. Always describe what you're showing before including the media
2. Use appropriate dimensions for the context (400px-500px width recommended)
3. Include descriptive alt text for accessibility
4. Provide fallback descriptions for users who cannot view media
5. Consider file sizes and loading times
6. **Images are automatically displayed and clickable** in the chat interface

**After analyzing images with vision_load, you can:**
- Reference and describe what you observed
- Include the analyzed images in your response using `<img>` tags
- Generate new images based on your analysis
- Create visualizations or charts to explain your findings

You can reference images from your analysis and include them in responses using the formats described in the communication guidelines:
- `<img src="path/to/image.jpg" alt="Description" width="400px" />` for image files
- `<image>base64data</image>` for base64-encoded images

**Example usage**:
```json
{
    "thoughts": [
        "I need to see the image...",
    ],
    "tool_name": "vision_load",
    "tool_args": {
        "paths": ["/path/to/image.png"],
    }
}
```