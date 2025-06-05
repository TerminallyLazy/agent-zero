# Media Response Tool

Use this when you need to include visual or multimedia content in your response.
Images will be automatically displayed and clickable in the chat interface.

## Usage Examples:

**Including generated images (DALL-E, charts, etc.):**

I've created the image you requested:
<img src="https://oaidalleapi.../generated-image.png" alt="A sunset over mountains with vibrant colors" width="400px" />

This shows the scene you described with warm lighting and dramatic clouds.

**Including news article images:**

Here's the breaking news story:
<img src="https://news.cnn.com/breaking-news-photo.jpg" alt="Emergency responders at the scene of the incident" width="400px" />

The incident occurred early this morning when...

**Including web article cover photos:**

I found this comprehensive guide:
<img src="https://techcrunch.com/article-cover.jpg" alt="Article cover showing AI and robotics collaboration" width="400px" />

The article discusses the latest developments in AI technology...

**Including product images from research:**

Here's the product you were asking about:
<img src="https://amazon.com/product-image.jpg" alt="Wireless noise-canceling headphones in matte black" width="400px" />

These headphones have received excellent reviews for their sound quality...

**Including analysis results as images:**

I've analyzed the data and created a visualization:
<image alt="Sales trend chart showing 15% growth">{{base64_chart_data}}</image>

The chart shows a clear upward trend in Q3 sales.

**Including reference images:**

Here's the diagram that explains this concept:
<img src="https://example.com/architecture-diagram.png" alt="System architecture showing data flow between components" width="500px" />

**Embedding interactive content:**

Here's the live monitoring dashboard:
<iframe src="https://monitoring.example.com" width="100%" height="500px"></iframe>

**Including reference videos:**

This tutorial explains the concept well:
<video src="https://example.com/tutorial.mp4"></video>

## Best Practices:
- Always include descriptive `alt` text for accessibility
- Use consistent width (400px-500px) for better layout
- Provide context before and after media content
- Images are automatically clickable for full-size viewing
- Use `<img>` tags for URLs, `<image>` tags for base64 data

Always provide context and descriptions alongside media content.
