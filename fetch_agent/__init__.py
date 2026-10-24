"""Clawback Assistant: the Fetch.ai agent Dana (the owner of Peak Bar Co., fictional) chats with in ASI:One.

It reads GET /summary and passes Dana's answer to POST /questions/{id}/answer. Nothing else: it never approves money,
never calls another endpoint and never computes an amount. See fetch_agent/README.md.
"""
