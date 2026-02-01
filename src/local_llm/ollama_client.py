#!/usr/bin/env python3
"""
Ollama Client - Local LLM Interface
====================================

Connects to Ollama running locally for AI-powered stock analysis.
Supports multiple models: llama3.2, mistral, qwen2.5, etc.

Features:
- Async and sync API support
- Streaming responses
- Model management
- Retry logic with fallbacks
"""

import os
import json
import requests
from typing import Dict, List, Optional, Generator
from dataclasses import dataclass
from loguru import logger
import time


@dataclass
class LLMResponse:
    """Response from LLM"""
    content: str
    model: str
    tokens_used: int
    generation_time: float
    success: bool
    error: Optional[str] = None


class OllamaClient:
    """
    Client for Ollama Local LLM

    Usage:
        client = OllamaClient()
        response = client.generate("Analyze NVDA stock")
        print(response.content)
    """

    # Recommended models for stock analysis
    RECOMMENDED_MODELS = {
        'fast': 'llama3.2:1b',      # Fastest, good for simple queries
        'balanced': 'llama3.2:3b',  # Good balance of speed and quality
        'quality': 'mistral:7b',    # Better reasoning
        'best': 'qwen2.5:7b',       # Best for financial analysis
    }

    def __init__(self,
                 base_url: str = "http://localhost:11434",
                 default_model: str = "llama3.2:3b",
                 timeout: int = 120):
        """
        Initialize Ollama client

        Args:
            base_url: Ollama API URL (default: localhost:11434)
            default_model: Default model to use
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.default_model = default_model
        self.timeout = timeout
        self._available_models = None

        logger.info(f"OllamaClient initialized: {base_url}")

    def is_available(self) -> bool:
        """Check if Ollama is running and accessible"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = [m['name'] for m in data.get('models', [])]
                self._available_models = models
                return models
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
        return []

    def pull_model(self, model_name: str) -> bool:
        """Pull/download a model"""
        logger.info(f"Pulling model: {model_name}")
        try:
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                timeout=600,  # 10 minutes for large models
                stream=True
            )

            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    status = data.get('status', '')
                    if 'pulling' in status:
                        logger.info(f"  {status}")
                    elif status == 'success':
                        logger.info(f"✅ Model {model_name} pulled successfully")
                        return True

            return True
        except Exception as e:
            logger.error(f"Failed to pull model: {e}")
            return False

    def generate(self,
                 prompt: str,
                 model: str = None,
                 system_prompt: str = None,
                 temperature: float = 0.7,
                 max_tokens: int = 2048,
                 stream: bool = False) -> LLMResponse:
        """
        Generate text using the LLM

        Args:
            prompt: User prompt
            model: Model to use (default: self.default_model)
            system_prompt: System instructions
            temperature: Creativity (0-1)
            max_tokens: Max tokens to generate
            stream: Whether to stream response

        Returns:
            LLMResponse object
        """
        model = model or self.default_model
        start_time = time.time()

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": stream,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                },
                timeout=self.timeout
            )

            if response.status_code != 200:
                return LLMResponse(
                    content="",
                    model=model,
                    tokens_used=0,
                    generation_time=0,
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}"
                )

            if stream:
                return self._handle_stream(response, model, start_time)
            else:
                data = response.json()
                content = data.get('message', {}).get('content', '')
                tokens = data.get('eval_count', 0)

                return LLMResponse(
                    content=content,
                    model=model,
                    tokens_used=tokens,
                    generation_time=time.time() - start_time,
                    success=True
                )

        except requests.exceptions.ConnectionError:
            return LLMResponse(
                content="",
                model=model,
                tokens_used=0,
                generation_time=0,
                success=False,
                error="Ollama not running. Start with: ollama serve"
            )
        except Exception as e:
            return LLMResponse(
                content="",
                model=model,
                tokens_used=0,
                generation_time=0,
                success=False,
                error=str(e)
            )

    def _handle_stream(self, response, model: str, start_time: float) -> LLMResponse:
        """Handle streaming response"""
        full_content = ""
        tokens = 0

        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if 'message' in data:
                    content = data['message'].get('content', '')
                    full_content += content
                if data.get('done', False):
                    tokens = data.get('eval_count', 0)

        return LLMResponse(
            content=full_content,
            model=model,
            tokens_used=tokens,
            generation_time=time.time() - start_time,
            success=True
        )

    def generate_stream(self,
                        prompt: str,
                        model: str = None,
                        system_prompt: str = None) -> Generator[str, None, None]:
        """
        Generate text with streaming (yields chunks)

        Usage:
            for chunk in client.generate_stream("Analyze NVDA"):
                print(chunk, end="", flush=True)
        """
        model = model or self.default_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                },
                timeout=self.timeout,
                stream=True
            )

            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if 'message' in data:
                        content = data['message'].get('content', '')
                        if content:
                            yield content

        except Exception as e:
            yield f"\n[Error: {e}]"

    def chat(self,
             messages: List[Dict[str, str]],
             model: str = None,
             temperature: float = 0.7) -> LLMResponse:
        """
        Multi-turn chat conversation

        Args:
            messages: List of {"role": "user/assistant", "content": "..."}
            model: Model to use
            temperature: Creativity

        Returns:
            LLMResponse
        """
        model = model or self.default_model
        start_time = time.time()

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature}
                },
                timeout=self.timeout
            )

            data = response.json()
            content = data.get('message', {}).get('content', '')

            return LLMResponse(
                content=content,
                model=model,
                tokens_used=data.get('eval_count', 0),
                generation_time=time.time() - start_time,
                success=True
            )

        except Exception as e:
            return LLMResponse(
                content="",
                model=model,
                tokens_used=0,
                generation_time=0,
                success=False,
                error=str(e)
            )


def test_ollama():
    """Test Ollama connection"""
    print("=" * 60)
    print("Testing Ollama Connection")
    print("=" * 60)

    client = OllamaClient()

    if not client.is_available():
        print("❌ Ollama is not running!")
        print()
        print("To start Ollama:")
        print("  1. Install: curl -fsSL https://ollama.com/install.sh | sh")
        print("  2. Start:   ollama serve")
        print("  3. Pull model: ollama pull llama3.2:3b")
        return

    print("✅ Ollama is running")

    models = client.get_available_models()
    print(f"✅ Available models: {models}")

    if not models:
        print("No models installed. Pulling llama3.2:3b...")
        client.pull_model("llama3.2:3b")

    print()
    print("Testing generation...")
    response = client.generate("Say hello in one sentence.")

    if response.success:
        print(f"✅ Response: {response.content}")
        print(f"   Model: {response.model}")
        print(f"   Time: {response.generation_time:.2f}s")
    else:
        print(f"❌ Error: {response.error}")


if __name__ == "__main__":
    test_ollama()
