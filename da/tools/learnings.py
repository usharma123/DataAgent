"""
Learnings Tools
===============

Tools for searching and saving learnings - patterns discovered through
interaction that help the agent improve over time.

Learnings are DIFFERENT from Knowledge:
- Knowledge: Static, curated facts (table schemas, validated queries, business rules)
- Learnings: Dynamic, discovered patterns (query fixes, type gotchas, user corrections)

Examples of learnings:
- "When querying race_wins by year, use TO_DATE(date, 'DD Mon YYYY')"
- "User prefers results sorted by date descending"
- "Position column in drivers_championship is TEXT, not INTEGER"
"""

import json
from datetime import datetime, timezone

from agno.knowledge import Knowledge
from agno.knowledge.reader.text_reader import TextReader
from agno.tools import tool
from agno.utils.log import logger


def create_learnings_tools(knowledge: Knowledge) -> tuple:
    """Factory function that creates search_learnings and save_learning tools.

    Args:
        knowledge: The knowledge base to store learnings in.

    Returns:
        Tuple of (search_learnings, save_learning) tool functions.
    """

    @tool
    def search_learnings(query: str, limit: int = 5) -> str:
        """Search for relevant learnings from past interactions.

        ALWAYS call this BEFORE saving a new learning to check for duplicates.
        Also call this when you encounter an error or unexpected result.

        Args:
            query: Keywords describing what you're looking for.
                   Examples: "date parsing", "position column type", "race wins query"
            limit: Maximum results (default: 5)

        Returns:
            List of relevant learnings, or message if none found.
        """
        try:
            results = knowledge.search(query=query, max_results=limit)

            if not results:
                return "No relevant learnings found."

            learnings: list[str] = []
            for i, result in enumerate(results, 1):
                content = result.content if hasattr(result, "content") else str(result)
                try:
                    data = json.loads(content)
                    if data.get("type") == "learning":
                        title = data.get("title", "Untitled")
                        learning = data.get("learning", "")
                        context = data.get("context", "")
                        learnings.append(f"{i}. **{title}**\n   {learning}")
                        if context:
                            learnings.append(f"   _Context: {context}_")
                except json.JSONDecodeError:
                    # Raw text content
                    learnings.append(f"{i}. {content[:200]}")

            if not learnings:
                return "No relevant learnings found."

            return f"Found {len(learnings)} learning(s):\n\n" + "\n".join(learnings)

        except Exception as e:
            logger.error(f"search_learnings failed: {e}")
            return f"Error searching learnings: {e}"

    @tool
    def save_learning(
        title: str,
        learning: str,
        context: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Save a discovered pattern or insight for future reference.

        IMPORTANT: Always call search_learnings FIRST to check for duplicates.

        Call this when you discover:
        - A query fix (e.g., "use TO_DATE for date parsing in race_wins")
        - A type gotcha (e.g., "position is TEXT in drivers_championship")
        - A pattern that worked (e.g., "always check column types before comparison")
        - A user correction (e.g., "user clarified that X means Y")

        Do NOT save:
        - Raw facts (those go in knowledge)
        - Common SQL syntax (everyone knows this)
        - One-off answers that won't generalize

        Args:
            title: Concise, searchable title (e.g., "Date parsing in race_wins table")
            learning: The specific insight - actionable and clear
            context: When/where this applies (e.g., "When filtering by year")
            tags: Categories for organization (e.g., ["date", "race_wins", "parsing"])

        Returns:
            Confirmation message.
        """
        if not title or not title.strip():
            return "Error: Title is required."

        if not learning or not learning.strip():
            return "Error: Learning content is required."

        try:
            payload = {
                "type": "learning",
                "title": title.strip(),
                "learning": learning.strip(),
                "context": context.strip() if context else None,
                "tags": tags or [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}

            knowledge.add_content(
                name=f"learning_{title.strip().lower().replace(' ', '_')[:50]}",
                text_content=json.dumps(payload, ensure_ascii=False, indent=2),
                reader=TextReader(),
                skip_if_exists=True,
            )

            logger.info(f"Saved learning: {title}")
            return f"Learning saved: {title}"

        except Exception as e:
            logger.error(f"save_learning failed: {e}")
            return f"Error saving learning: {e}"

    return search_learnings, save_learning
