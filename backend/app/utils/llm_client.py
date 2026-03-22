"""
LLM Client Wrapper
Supports Anthropic (via native SDK or OpenAI-compatible proxy) and OpenAI backends
"""

import json
import re
from typing import Optional, Dict, Any, List

from ..config import Config


def _is_openai_compatible_url(url: str) -> bool:
    """Check if a URL is an OpenAI-compatible endpoint (not native Anthropic)."""
    if not url:
        return False
    return 'anthropic.com' not in url


class LLMClient:
    """LLM Client - supports Anthropic and OpenAI backends"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None
    ):
        self.provider = provider or Config.LLM_PROVIDER
        self.model = model or Config.LLM_MODEL_NAME

        if self.provider == 'anthropic':
            self.api_key = api_key or Config.ANTHROPIC_API_KEY
            self.base_url = base_url or Config.ANTHROPIC_BASE_URL
        else:
            self.api_key = api_key or Config.LLM_API_KEY
            self.base_url = base_url or Config.LLM_BASE_URL

        if not self.api_key:
            raise ValueError("LLM API key is not configured (set LLM_API_KEY or ANTHROPIC_API_KEY)")

        # Use OpenAI SDK for OpenAI-compatible endpoints (e.g. cliproxy),
        # native Anthropic SDK only for direct Anthropic API access
        if self.provider == 'anthropic' and not _is_openai_compatible_url(self.base_url):
            import anthropic
            client_kwargs = {"api_key": self.api_key}
            self.client = anthropic.Anthropic(**client_kwargs)
            self._use_anthropic_sdk = True
        else:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self._use_anthropic_sdk = False

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Send chat request

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format (e.g., JSON mode) - OpenAI-compatible only

        Returns:
            Model response text
        """
        if self._use_anthropic_sdk:
            return self._chat_anthropic(messages, temperature, max_tokens, response_format)
        else:
            return self._chat_openai(messages, temperature, max_tokens, response_format)

    def _chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict] = None
    ) -> str:
        """Send chat request via native Anthropic API"""
        # Extract system message if present
        system_msg = None
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)

        # If response_format requests JSON, add instruction to system prompt
        if response_format and response_format.get("type") == "json_object":
            json_instruction = "\n\nIMPORTANT: You must respond with valid JSON only, no markdown formatting."
            if system_msg:
                system_msg += json_instruction
            else:
                system_msg = "You are a helpful assistant." + json_instruction

        kwargs = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system_msg:
            kwargs["system"] = system_msg

        response = self.client.messages.create(**kwargs)
        content = response.content[0].text
        # Some models include <think> content that needs to be removed
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict] = None
    ) -> str:
        """Send chat request via OpenAI-compatible API"""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # Some models include <think> content that needs to be removed
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count

        Returns:
            Parsed JSON object
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # Clean up markdown code block markers
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format returned by LLM: {cleaned_response}")
