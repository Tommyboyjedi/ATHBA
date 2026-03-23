# Setting Up Cloud Provider for Architect Agent

## Overview

The Architect agent requires access to Anthropic's Claude Sonnet 4.5 via their cloud API. This guide walks you through the setup process.

## Prerequisites

- ATHBA repository cloned and configured
- Python environment set up with dependencies installed
- Access to create an Anthropic account (credit card required for API access)

## Step 1: Create Anthropic Account

1. Navigate to [https://console.anthropic.com/](https://console.anthropic.com/)
2. Click "Sign Up" or "Get Started"
3. Complete the registration process
4. Verify your email address

## Step 2: Add Payment Method

1. Log into the Anthropic Console
2. Navigate to Settings → Billing
3. Add a payment method (credit card)
4. Note: You can set spending limits to control costs

## Step 3: Generate API Key

1. In the Anthropic Console, navigate to "API Keys"
2. Click "Create Key"
3. Give your key a descriptive name (e.g., "ATHBA Architect")
4. Copy the generated API key immediately (you won't be able to see it again)
5. Store it securely

## Step 4: Configure ATHBA

### Option A: Using .env file (Recommended)

1. Navigate to your ATHBA repository root
2. Copy `.env.example` to `.env` if you haven't already:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` in your editor
4. Add your Anthropic API key:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```
5. Optionally configure other settings:
   ```bash
   ANTHROPIC_API_BASE=https://api.anthropic.com/v1  # Usually not needed
   ANTHROPIC_DEFAULT_MODEL=claude-sonnet-4.5-20250514  # Usually not needed
   ```

### Option B: Using environment variables

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## Step 5: Verify Setup

Test that the Architect can connect to Claude:

```python
# In Python REPL or test script
from core.config.anthropic import AnthropicSettings

try:
    settings = AnthropicSettings.from_env()
    print("✅ Anthropic API key configured successfully!")
    print(f"Model: {settings.default_model}")
except RuntimeError as e:
    print(f"❌ Configuration error: {e}")
```

Or test with the provider:

```python
from core.llm.providers.anthropic_provider import AnthropicProvider

try:
    provider = AnthropicProvider()
    result = provider.invoke("Hello, Claude!", model="claude-sonnet-4.5-20250514", max_tokens=50)
    print("✅ Successfully connected to Claude!")
    print(f"Response: {result.text}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
```

## Step 6: Test Architect Agent

1. Start your ATHBA services:
   ```bash
   # Terminal 1: Django app
   poetry run uvicorn athba.asgi:app --port 8000
   
   # Terminal 2: LLM server (for other agents)
   poetry run uvicorn llm_service.llm_server:app --port 8011
   ```

2. Create a test specification through the UI

3. Finalize the specification:
   - Chat: "finalize the spec"
   - Watch for Architect to analyze and create tickets
   - Check console logs for `[CLOUD]` messages indicating Claude usage

## Cost Management

### Setting Spending Limits

1. In Anthropic Console, go to Settings → Billing
2. Set a monthly spending limit
3. Configure email alerts for usage thresholds

### Monitoring Usage

1. Check the Usage page in Anthropic Console
2. Monitor token consumption per request
3. Review monthly costs

### Typical Costs

Based on Claude Sonnet 4.5 pricing (~$3/million input tokens, ~$15/million output tokens):

| Specification Size | Estimated Cost |
|-------------------|----------------|
| Small (1-2 pages) | $0.01 - $0.05  |
| Medium (5-10 pages) | $0.10 - $0.25 |
| Large (20+ pages) | $0.50 - $1.00  |

The Architect is only invoked when finalizing a spec, so costs are predictable and infrequent.

## Troubleshooting

### Error: "ANTHROPIC_API_KEY is not set"

**Solution**: Make sure your `.env` file contains the API key and restart your services.

### Error: "401 Unauthorized"

**Solutions**:
- Verify your API key is correct
- Check that your Anthropic account is active
- Ensure billing is set up

### Error: "429 Rate Limit"

**Solutions**:
- Wait a few minutes and try again
- The Architect automatically retries with exponential backoff
- Check your rate limits in Anthropic Console

### Error: "Timeout after 120s"

**Solutions**:
- Check your internet connection
- Verify Anthropic API is operational (status.anthropic.com)
- Large specs may take longer - the fallback mechanism will create basic tickets

### Fallback to Default Tickets

If Claude is unavailable, the Architect creates 3 default tickets:
- "Initial project setup"
- "Implement core features from specification"
- "Add tests for core functionality"

This ensures the workflow continues even with API issues.

## Security Best Practices

1. **Never commit API keys**: Keep `.env` in `.gitignore`
2. **Rotate keys regularly**: Generate new keys every 90 days
3. **Use separate keys**: Different keys for dev/staging/production
4. **Monitor usage**: Set up alerts for unusual activity
5. **Restrict key access**: Use per-project keys when possible

## Alternative: Using OpenAI Instead

While the Architect is configured for Anthropic Claude by default, you could modify it to use OpenAI's GPT-4 if preferred:

1. Uncomment the OpenAI provider configuration
2. Modify `LlmExchange` to use `OpenAIProvider`
3. Update the model selection in `architect_agent.py`

However, Claude Sonnet 4.5 is specifically chosen for its superior specification analysis capabilities.

## Support

If you encounter issues:

1. Check the [Anthropic Documentation](https://docs.anthropic.com/)
2. Review ATHBA logs for detailed error messages
3. Consult the ARCHITECT_AGENT.md documentation
4. Raise an issue in the ATHBA repository

## Summary

Once configured, the Architect agent will:
- ✅ Automatically use Claude Sonnet 4.5 for all analysis
- ✅ Never fall back to local LLM models
- ✅ Generate high-quality, consistent tickets
- ✅ Provide detailed logging of API calls
- ✅ Handle errors gracefully with fallback tickets

The one-time setup enables reliable, cloud-powered specification analysis for all your projects.
