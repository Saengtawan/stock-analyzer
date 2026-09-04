"""orb_trader / channels / text.py — TEXT retrieval for news + web (embedding similarity).

The one place vectors earn their keep: unstructured TEXT where semantic similarity matters.
Numeric data does NOT belong here (use channels/numeric.py — SQL, not embeddings).

Planned channels (logic to be designed by the AI):
  news(date, sym, minute)   -> today's headlines for a name, published <= cutoff (sim-safe),
                               each tagged fresh/stale + age. (pass ①)
  similar_news(text)        -> past news semantically similar to today's catalyst — "have we
                               seen a story like this, and did the market already price it?"
  theme(date, minute)       -> cluster today's movers' headlines into themes (what's the driver).

Notes: web search itself is a tool the brain calls directly (WebSearch); this module is for
retrieving/embedding the STORED news corpus (news_events) and comparing against it.

TODO(AI): choose the embedding approach + implement.
"""
