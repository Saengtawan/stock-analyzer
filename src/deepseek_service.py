"""
DeepSeek API Service - Central service for all DeepSeek API calls
"""
import requests
import json
import time
from typing import Optional, Dict, Any
from loguru import logger


class DeepSeekService:
    """Central service for DeepSeek AI API calls"""

    def __init__(self):
        self.api_key = "sk-289bb1da2bc1496c8557a89f62023e78"
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.max_retries = 3
        self.retry_delay = 2  # seconds (increased)
        self.timeout = 60  # seconds (increased from 30)

    def call_api(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3, model: str = 'deepseek-chat') -> Optional[str]:
        """
        Call DeepSeek API with error handling and retries

        Args:
            prompt: The prompt to send to AI
            max_tokens: Maximum tokens for response
            temperature: Temperature for response randomness (0.0-1.0)
            model: Model to use ('deepseek-chat' or 'deepseek-reasoner')

        Returns:
            AI response text or None if failed
        """
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': model,  # Support both deepseek-chat and deepseek-reasoner
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': temperature,
            'max_tokens': max_tokens
        }

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"DeepSeek API call attempt {attempt + 1}/{self.max_retries}")

                response = requests.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    response_data = response.json()
                    content = response_data['choices'][0]['message']['content']
                    logger.debug("DeepSeek API call successful")
                    return content

                elif response.status_code == 429:  # Rate limit
                    logger.warning(f"DeepSeek API rate limit hit, retrying in {self.retry_delay * (attempt + 1)} seconds")
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue

                elif response.status_code == 401:  # Unauthorized
                    logger.error("DeepSeek API authentication failed - check API key")
                    raise Exception("DeepSeek API authentication failed")

                else:
                    logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
                    if attempt == self.max_retries - 1:
                        raise Exception(f"DeepSeek API error: {response.status_code}")
                    time.sleep(self.retry_delay)

            except requests.exceptions.Timeout:
                logger.warning(f"DeepSeek API timeout, attempt {attempt + 1}/{self.max_retries}")
                if attempt == self.max_retries - 1:
                    raise Exception("DeepSeek API timeout after retries")
                time.sleep(self.retry_delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"DeepSeek API request error: {e}")
                if attempt == self.max_retries - 1:
                    raise Exception(f"DeepSeek API request failed: {e}")
                time.sleep(self.retry_delay)

        return None

    def call_api_json(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3, model: str = 'deepseek-chat') -> Optional[Dict[str, Any]]:
        """
        Call DeepSeek API and parse JSON response

        Args:
            prompt: The prompt to send to AI
            max_tokens: Maximum tokens for response
            temperature: Temperature for response randomness
            model: Model to use ('deepseek-chat' or 'deepseek-reasoner')

        Returns:
            Parsed JSON dict or None if failed
        """
        response_text = self.call_api(prompt, max_tokens, temperature, model)

        if not response_text:
            return None

        try:
            # Find JSON in response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1

            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                return json.loads(json_str)
            else:
                logger.warning("No valid JSON found in DeepSeek response")
                return None

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from DeepSeek response: {e}")
            return None

    def health_check(self) -> bool:
        """
        Check if DeepSeek API is accessible

        Returns:
            True if API is working, False otherwise
        """
        try:
            response = self.call_api("Hello", max_tokens=10)
            return response is not None
        except Exception as e:
            logger.error(f"DeepSeek API health check failed: {e}")
            return False


# Global instance
deepseek_service = DeepSeekService()


def main():
    """Test the DeepSeek service"""
    service = DeepSeekService()

    print("Testing DeepSeek API service...")

    # Health check
    if service.health_check():
        print("✅ DeepSeek API is accessible")
    else:
        print("❌ DeepSeek API is not accessible")
        return

    # Test text response
    response = service.call_api("What is 2+2?", max_tokens=50)
    if response:
        print(f"✅ Text response: {response[:100]}...")
    else:
        print("❌ Text response failed")

    # Test JSON response
    json_prompt = """
    Return a JSON object with the following structure:
    {
        "result": 4,
        "explanation": "2 plus 2 equals 4"
    }
    """

    json_response = service.call_api_json(json_prompt, max_tokens=100)
    if json_response:
        print(f"✅ JSON response: {json_response}")
    else:
        print("❌ JSON response failed")


if __name__ == "__main__":
    main()