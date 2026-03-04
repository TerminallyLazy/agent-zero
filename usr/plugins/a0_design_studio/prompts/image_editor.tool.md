## image_editor

Generate, edit, or save images using AI image models.

### Actions

**generate** — Create an image from a text description.
- `prompt` (required): Detailed description of the image to generate.
- `size` (optional): Image dimensions (e.g., "1024x1024"). Default from settings.
- `model` (optional): LiteLLM model string. Default from settings.

**edit** — Analyze and describe edits for an existing image.
- `image_path` (required): Path to the source image in workspace.
- `prompt` (required): Editing instructions.
- `model` (optional): Vision model to use. Default from settings.

**save** — Copy an image to a specific location.
- `image_path` (required): Source image path.
- `output_path` (required): Destination path.

### Examples

Generate an image:
~~~json
{
  "action": "generate",
  "prompt": "A serene mountain landscape at sunset with a lake reflection"
}
~~~

Edit an image:
~~~json
{
  "action": "edit",
  "image_path": "images/landscape.png",
  "prompt": "Change the sky to a dramatic stormy atmosphere"
}
~~~

Save an image:
~~~json
{
  "action": "save",
  "image_path": "images/generated_1709567890.png",
  "output_path": "project/assets/hero-image.png"
}
~~~
