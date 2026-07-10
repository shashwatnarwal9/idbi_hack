"""Agentic lead-to-customer outreach layer.

A model (GLM-5.2 via the NVIDIA OpenAI-compatible endpoint) uses typed tools in
a loop to PLAN, DRAFT, SCHEDULE and TRACK outreach. The lending decision is
untouched, the agent only proposes; a human commits. The API key is read from
the NVIDIA_API_KEY environment variable and is never hardcoded.
"""
