"""
YouTube smart-play: turns natural language ("play that new Seetha Ramam
song pls") into a clean YouTube search query using the user's AI key,
with a keyword-stripping heuristic as an offline fallback.
"""

from seetha import ai_client
from seetha.logger import setup_logger

logger = setup_logger()


class YouTubeManager:
    def process_command(self, text):
        """
        Process a 'Play' command.
        Returns (response_text, action_name, params).
        """
        search_query = self._extract_video_title(text)
        if not search_query:
            return "I couldn't understand what to play.", None, None
        return f"Playing '{search_query}' on YouTube.", "play_youtube", {"query": search_query}

    def _extract_video_title(self, text):
        prompt = f"""
        Extract the YouTube search query from this command.
        Ignore words like "play", "seetha", "please", "watch", "can you".
        Return ONLY the raw search terms.

        Command: "{text}"

        Search Query:
        """
        try:
            content, err = ai_client.chat_completion(
                [{"role": "user", "content": prompt}], max_tokens=50
            )
            if content:
                return content.strip().strip('"')
            logger.debug(f"AI title extraction unavailable ({err}), using heuristic.")
        except Exception as e:
            logger.error(f"YouTube intent extraction failed: {e}")

        # Heuristic fallback — works with no API key at all
        clean = text.lower()
        for word in ["play", "seetha", "please", "watch", "video", "youtube", "listen to"]:
            clean = clean.replace(word, "")
        return clean.strip()
