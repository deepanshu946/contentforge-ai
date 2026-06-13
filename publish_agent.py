from __future__ import annotations

from datetime import datetime
from typing import Optional

import requests
from pydantic import BaseModel


class PublishResult(BaseModel):
    platform: str
    article_url: str
    article_id: str
    published_at: str
    success: bool
    message: str
    views: int = 0
    reactions: int = 0
    comments: int = 0


# =====================================================
# DEV.TO
# =====================================================

def publish_to_devto(
    *,
    title: str,
    markdown: str,
    api_key: str,
    tags: Optional[list[str]] = None,
    publish: bool = True,
) -> PublishResult:

    payload = {
        "article": {
            "title": title,
            "published": publish,
            "body_markdown": markdown,
            "tags": tags or []
        }
    }

    try:
        response = requests.post(
            "https://dev.to/api/articles",
            headers={
                "api-key": api_key,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60,
        )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Dev.to API error ({response.status_code}): {response.text}"
            )

        article = response.json()

        return PublishResult(
            platform="devto",
            article_url=article.get("url", ""),
            article_id=str(article.get("id", "")),
            published_at=datetime.utcnow().isoformat(),
            success=True,
            message="Published successfully" if publish else "Draft created successfully"
        )

    except Exception as e:
        return PublishResult(
            platform="devto",
            article_url="",
            article_id="",
            published_at=datetime.utcnow().isoformat(),
            success=False,
            message=str(e)
        )


# =====================================================
# DEV.TO PUBLISH ENTRYPOINT
# =====================================================

def publish_article(
    *,
    title: str,
    markdown: str,
    api_key: str,
    tags: Optional[list[str]] = None,
    publish: bool = True,
) -> PublishResult:

    return publish_to_devto(
        title=title,
        markdown=markdown,
        api_key=api_key,
        tags=tags,
        publish=publish,
    )