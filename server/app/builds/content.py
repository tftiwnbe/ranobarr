from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.builds.service import cache_file_path
from app.core.errors import TrackingError


@dataclass(slots=True)
class NormalizedChapter:
    chapter_key: str
    volume: str
    number: str
    title: str | None
    branch_id: str | None
    branch_name: str | None
    content_type: str
    html_content: str
    attachments: list[dict[str, Any]]


def load_cached_payload(relative_path: str) -> dict[str, Any]:
    file_path = cache_file_path(relative_path)
    if not file_path.is_file():
        raise TrackingError(f"Cached chapter payload is missing: {relative_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def normalize_cached_payload(payload: dict[str, Any], *, content_type: str) -> NormalizedChapter:
    raw_content = payload.get("content")
    attachments = payload.get("attachments") or []

    if content_type == "html":
        html_content = normalize_html_string(str(raw_content or ""))
    elif content_type == "text":
        html_content = normalize_text_string(str(raw_content or ""))
    elif content_type == "doc":
        doc_nodes = extract_doc_nodes(raw_content)
        html_content = normalize_doc_content(doc_nodes, attachments)
    else:
        raise TrackingError(f"Unsupported cached chapter content type: {content_type}")

    return NormalizedChapter(
        chapter_key=str(payload["chapter_key"]),
        volume=str(payload.get("volume", "1")),
        number=str(payload.get("number", "0")),
        title=payload.get("title"),
        branch_id=payload.get("branch_id"),
        branch_name=payload.get("branch_name"),
        content_type=content_type,
        html_content=html_content,
        attachments=attachments,
    )


def extract_doc_nodes(raw_content: Any) -> list[dict[str, Any]]:
    if isinstance(raw_content, dict) and raw_content.get("type") == "doc":
        content = raw_content.get("content")
        return content if isinstance(content, list) else []
    if isinstance(raw_content, list):
        return raw_content
    if isinstance(raw_content, dict) and isinstance(raw_content.get("content"), list):
        return raw_content["content"]
    return []


def normalize_html_string(content: str) -> str:
    if not content.strip():
        return "<p></p>"
    return content


def normalize_text_string(content: str) -> str:
    if not content:
        return "<p></p>"

    paragraphs = []
    for block in re.split(r"\n{2,}", content):
        lines = [line.strip() for line in block.splitlines()]
        line_text = " ".join(line for line in lines if line)
        if line_text:
            paragraphs.append(f"<p>{html.escape(line_text)}</p>")

    return "".join(paragraphs) if paragraphs else "<p></p>"


def normalize_doc_content(content: list[dict[str, Any]], attachments: list[dict[str, Any]]) -> str:
    parser = DocToHtmlParser(attachments)
    return "".join(parser.render_node(node) for node in content)


class DocToHtmlParser:
    def __init__(self, attachments: list[dict[str, Any]]) -> None:
        self.attachments = attachments

    def render_node(self, node: dict[str, Any]) -> str:
        node_type = node.get("type")

        if node_type == "paragraph":
            return self.render_paragraph(node)
        if node_type == "heading":
            level = int((node.get("attrs") or {}).get("level") or 2)
            tag = f"h{min(max(level, 1), 6)}"
            return f"<{tag}>{self.render_inline_nodes(node.get('content') or [])}</{tag}>"
        if node_type == "horizontalRule":
            return "<hr />"
        if node_type == "bulletList":
            return f"<ul>{self.render_list_items(node.get('content') or [])}</ul>"
        if node_type == "orderedList":
            return f"<ol>{self.render_list_items(node.get('content') or [])}</ol>"
        if node_type == "blockquote":
            return f"<blockquote>{''.join(self.render_node(item) for item in node.get('content') or [])}</blockquote>"
        if node_type == "image":
            return self.render_image_node(node)
        if node_type == "text":
            return self.render_text(node)
        if node_type == "hardBreak":
            return "<br />"
        if node_type == "listItem":
            return f"<li>{''.join(self.render_node(item) for item in node.get('content') or [])}</li>"
        return ""

    def render_paragraph(self, node: dict[str, Any]) -> str:
        attrs = node.get("attrs") or {}
        align = attrs.get("textAlign")
        style = f' style="text-align: {html.escape(str(align))};"' if align else ""
        inner = self.render_inline_nodes(node.get("content") or [])
        return f"<p{style}>{inner}</p>"

    def render_list_items(self, items: list[dict[str, Any]]) -> str:
        return "".join(self.render_node(item) for item in items)

    def render_inline_nodes(self, nodes: list[dict[str, Any]]) -> str:
        return "".join(self.render_inline_node(node) for node in nodes)

    def render_inline_node(self, node: dict[str, Any]) -> str:
        node_type = node.get("type")
        if node_type == "text":
            return self.render_text(node)
        if node_type == "hardBreak":
            return "<br />"
        if node_type == "image":
            return self.render_image_node(node)
        if node_type in {"paragraph", "heading", "blockquote", "bulletList", "orderedList", "listItem"}:
            return self.render_node(node)
        return ""

    def render_text(self, node: dict[str, Any]) -> str:
        text = decode_html_entities(str(node.get("text") or ""))
        escaped = html.escape(re.sub(r" +", " ", text.replace("\n", " ")))
        marks = node.get("marks") or []
        return apply_marks(escaped, marks)

    def render_image_node(self, node: dict[str, Any]) -> str:
        attrs = node.get("attrs") or {}
        image_defs = attrs.get("images") or []
        if image_defs:
            fragments = []
            for image_def in image_defs:
                image_id = image_def.get("image")
                attachment = next(
                    (
                        item
                        for item in self.attachments
                        if item.get("name") == image_id or item.get("id") == image_id
                    ),
                    None,
                )
                if attachment and attachment.get("url"):
                    fragments.append(f"<img src=\"{html.escape(str(attachment['url']))}\" alt=\"\" />")
            return "".join(fragments)

        src = attrs.get("src")
        if src:
            return f"<img src=\"{html.escape(str(src))}\" alt=\"\" />"
        return ""


def apply_marks(text: str, marks: list[dict[str, Any]]) -> str:
    wrappers = {
        "bold": ("<b>", "</b>"),
        "italic": ("<i>", "</i>"),
        "underline": ("<u>", "</u>"),
        "strike": ("<del>", "</del>"),
    }
    rendered = text
    for mark in marks:
        open_tag, close_tag = wrappers.get(mark.get("type"), ("", ""))
        rendered = f"{open_tag}{rendered}{close_tag}"
    return rendered


def decode_html_entities(text: str, max_iterations: int = 5) -> str:
    previous = text
    for _ in range(max_iterations):
        decoded = html.unescape(previous)
        if decoded == previous:
            break
        previous = decoded
    return previous
