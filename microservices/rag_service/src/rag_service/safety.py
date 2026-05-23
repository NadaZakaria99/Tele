"""
safety.py — NemoGuard Safety & Topic Control as LangChain Runnables
====================================================================
Wraps the NemoGuard NIMs as LangChain Runnable objects so they compose
cleanly into the LCEL chain with the | pipe operator.
"""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import Runnable, RunnableConfig
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from rag_service.config import settings
from rag_service.prompts import (
    REFUSAL_RESPONSE_UNSAFE,
    REFUSAL_OFF_TOPIC,
)

log = logging.getLogger(__name__)

class SafetyRunnable(Runnable):
    """
    Checks the query against NemoGuard content-safety NIM.
    Passes through the state dict unchanged if safe.
    """

    def invoke(self, state: dict, config: RunnableConfig | None = None) -> dict:
        query = state["query"]
        llm = ChatNVIDIA(
            model=settings.safety_model,
            base_url=settings.safety_base_url,
            api_key=settings.nvidia_api_key,
        )
        try:
            # External API call to NemoGuard
            response = llm.invoke([{"role": "user", "content": query}])
            raw = response.content.strip().lower()
            
            # Simple check: if the API returns anything containing 'unsafe', we block.
            # NemoGuard usually returns a JSON or a direct string verdict.
            if "unsafe" in raw:
                log.warning(f"Safety blocked query: response='{raw}'")
                state["blocked"] = True
                state["refusal"] = REFUSAL_RESPONSE_UNSAFE
            else:
                log.info(f"Safety passed for query: '{query}'")
        except Exception as exc:
            log.warning(f"Safety check failed (failing open): {exc}")

        return state
