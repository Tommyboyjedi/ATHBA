# OpenAI LLM Provider

This project includes an `OpenAIProvider` which uses OpenAI's Responses API to
produce structured JSON conforming to our PM intent envelope schema.

## Configuration

Set the following environment variables:

- `OPENAI_API_KEY` (required)
- `OPENAI_ORG` or `OPENAI_PROJECT` (optional)
- `OPENAI_API_BASE` (optional, defaults to `https://api.openai.com/v1`)

You can use `.env.example` as a starting point for a local `.env` file.

## Running Tests

```bash
pytest -k openai_provider
```
