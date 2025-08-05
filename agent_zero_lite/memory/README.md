# Memory Directory

This directory is used to store agent memories. The structure is as follows:

- `main/`: Default memory area
- `<custom_area>/`: Custom memory areas

Each memory is stored as a JSON file with the following structure:

```json
{
  "id": "20250805123456",
  "text": "Memory content",
  "area": "main",
  "created_at": "2025-08-05T12:34:56.789Z",
  "metadata": {}
}
```

Memories can be saved and loaded using the `memory_save` and `memory_load` tools.