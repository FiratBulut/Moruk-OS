import re
import os


def markdown_to_html(text: str) -> str:
    """
    Konvertiert Markdown-Text zu HTML für QLabel.
    Unterstützt: bold, italic, code, code blocks, headers, links, images, lists, hr.
    """
    if not text:
        return ""

    # Prüfe ob überhaupt Markdown-Zeichen vorhanden
    if not any(c in text for c in ("*", "`", "#", "[", "!", "-", ">", "~", ".")):
        return _escape_html(text).replace("\n", "<br>")

    lines = text.split("\n")
    html_lines = []
    in_code_block = False
    code_block_content = []
    in_list = False
    list_type = "ul"  # "ul" oder "ol"

    for line in lines:
        # ── Code Block ──
        if line.strip().startswith("```"):
            if in_code_block:
                # Ende Code Block
                code = _escape_html("\n".join(code_block_content))
                html_lines.append(
                    f'<div style="background-color: rgba(0,0,0,0.4); '
                    f"border: 1px solid rgba(255,255,255,0.1); "
                    f"border-radius: 8px; padding: 12px; margin: 8px 0; "
                    f"font-family: monospace; font-size: 13px; "
                    f'color: #00ff88; white-space: pre-wrap;">{code}</div>'
                )
                code_block_content = []
                in_code_block = False
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                in_code_block = True
            continue

        if in_code_block:
            code_block_content.append(line)
            continue

        # ── Headers ──
        if line.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(
                f'<b style="font-size: 14px; color: #00d2ff;">{_inline_format(line[4:])}</b><br>'
            )
            continue
        if line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(
                f'<b style="font-size: 15px; color: #e94560;">{_inline_format(line[3:])}</b><br>'
            )
            continue
        if line.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(
                f'<b style="font-size: 16px; color: #e94560;">{_inline_format(line[2:])}</b><br>'
            )
            continue

        # ── Horizontal Rule ──
        if re.match(r"^(-{3,}|_{3,}|\*{3,})\s*$", line.strip()):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append('<hr style="border: 1px solid rgba(255,255,255,0.1);">')
            continue

        # ── Blockquote ──
        if line.strip().startswith("> "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            quote_text = _inline_format(line.strip()[2:])
            html_lines.append(
                f'<div style="border-left: 3px solid #e94560; padding-left: 8px; '
                f'margin: 4px 0; color: rgba(255,255,255,0.7); font-style: italic;">{quote_text}</div>'
            )
            continue

        # ── Lists ──
        li_match = re.match(r"^\s*[\*\+-]\s+(.*)$", line)
        if li_match:
            if not in_list:
                html_lines.append('<ul style="margin-left: 15px;">')
                in_list = True
                list_type = "ul"
            elif list_type == "ol":
                html_lines.append("</ol>")
                html_lines.append('<ul style="margin-left: 15px;">')
                list_type = "ul"
            html_lines.append(f"<li>{_inline_format(li_match.group(1))}</li>")
            continue

        ol_match = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if ol_match:
            if not in_list:
                html_lines.append('<ol style="margin-left: 15px;">')
                in_list = True
                list_type = "ol"
            elif list_type == "ul":
                html_lines.append("</ul>")
                html_lines.append('<ol style="margin-left: 15px;">')
                list_type = "ol"
            html_lines.append(f"<li>{_inline_format(ol_match.group(1))}</li>")
            continue

        if in_list and not line.strip():
            html_lines.append(f"</{list_type}>")
            in_list = False
            continue

        # Normaler Text
        if line.strip():
            html_lines.append(_inline_format(line) + "<br>")
        else:
            html_lines.append("<br>")

    if in_list:
        html_lines.append(f"</{list_type}>")

    # Unclosed code block — restlichen Inhalt noch rendern
    if in_code_block and code_block_content:
        code = _escape_html("\n".join(code_block_content))
        html_lines.append(
            f'<div style="background-color: rgba(0,0,0,0.4); '
            f"border: 1px solid rgba(255,255,255,0.1); "
            f"border-radius: 8px; padding: 12px; margin: 8px 0; "
            f"font-family: monospace; font-size: 13px; "
            f'color: #00ff88; white-space: pre-wrap;">{code}</div>'
        )

    return "".join(html_lines)


def _inline_format(text: str) -> str:
    """Inline Markdown: bold, italic, code, strikethrough, links, images."""
    # 1. Escape HTML first
    text = _escape_html(text)

    # 2. Code: `text` (Should be done before others to protect content)
    text = re.sub(
        r"`([^`]+)`",
        r'<span style="background: rgba(0,0,0,0.3); padding: 1px 5px; '
        r"border-radius: 3px; font-family: monospace; font-size: 12px; "
        r'color: #00ff88;">\1</span>',
        text,
    )

    # 3. Images: ![alt](path) -> Thumbnail with link
    def replace_image(match):
        alt = match.group(1)
        path = match.group(2).strip()
        if not path.startswith(("http", "file://", "data:")):
            if path.startswith("~"):
                path = os.path.expanduser(path)
            abs_path = os.path.abspath(path)
            full_path = f"file://{abs_path}"
        else:
            full_path = path
        return f"[[IMG_S]]{full_path}[[IMG_M]]{full_path}[[IMG_A]]{alt}[[IMG_E]]"

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_image, text)

    # 4. Bold: **text** or __text__
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)__(.*?)__(?!\w)", r"<b>\1</b>", text)

    # 5. Italic: *text* or _text_
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.*?)_(?!\w)", r"<i>\1</i>", text)

    # 6. Strikethrough: ~~text~~
    text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)

    # 7. Links: [text](url)
    text = re.sub(
        r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" style="color: #00d2ff; text-decoration: underline;">\1</a>',
        text,
    )

    # 8. Restore Image Tags (QLabel doesn't support border-radius in RichText)
    text = text.replace("[[IMG_S]]", '<a href="')
    text = text.replace("[[IMG_M]]", '"><img src="')
    text = text.replace("[[IMG_A]]", '" width="250" alt="')
    text = text.replace("[[IMG_E]]", '"></a>')

    return text


def _escape_html(text: str) -> str:
    """Escaped HTML-Sonderzeichen."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
