# -*- coding: utf-8 -*-
"""
mdxp v1.1 - Markdown eXPerience Viewer
A graphical Markdown file viewer for Windows XP (Python 2.7 / Tkinter).
Standard library only. No external dependencies.
"""

import sys
import os
import re
import webbrowser
import codecs
import Tkinter as tk
import tkFileDialog
import tkMessageBox
import tkFont
import time


# ---------------------------------------------------------------------------
# Unicode utilities
# ---------------------------------------------------------------------------

def _to_unicode(value):
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        for enc in ("utf-8", "mbcs", "latin-1"):
            try:
                return value.decode(enc)
            except (UnicodeError, LookupError):
                pass
        return value.decode("latin-1", "replace")
    try:
        raw = str(value)
    except Exception:
        try:
            raw = repr(value)
        except Exception:
            return u"<unprintable>"
    if isinstance(raw, unicode):
        return raw
    for enc in ("utf-8", "mbcs", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeError, LookupError):
            pass
    return raw.decode("latin-1", "replace")


_CONTROL_RE = re.compile(u"[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]", re.UNICODE)


def _sanitize_text(value):
    return _CONTROL_RE.sub(u"", _to_unicode(value))


def _sanitize_exception(e):
    try:
        msg = _to_unicode(e)
        if not msg:
            msg = type(e).__name__
        return msg
    except Exception:
        return u"Unknown error"


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_VALID_URL_SCHEMES = frozenset(["http", "https", "mailto", "ftp"])
_DANGEROUS_SCHEMES = frozenset(["javascript", "vbscript", "file", "data"])


def _validate_url(url):
    url = url.strip()
    if not url:
        return None
    # Remove angle brackets
    if url.startswith(u"<") and url.endswith(u">"):
        url = url[1:-1].strip()
    # Check for scheme
    scheme_match = re.match(r'^([a-zA-Z][a-zA-Z0-9+\-.]*):', url)
    if scheme_match:
        scheme = scheme_match.group(1).lower()
        if scheme in _DANGEROUS_SCHEMES:
            return None
        if scheme in _VALID_URL_SCHEMES:
            return url
        return None
    # No scheme
    if u"@" in url and u"." in url:
        return u"mailto:" + url
    if url.startswith(u"www."):
        return u"http://" + url
    if re.match(r'^[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}', url):
        return u"http://" + url
    return None


# ---------------------------------------------------------------------------
# Block-level Markdown parser
# ---------------------------------------------------------------------------

# Block types used internally:
#   {"type": "paragraph", "lines": [raw_lines]}
#   {"type": "heading", "level": int(1-6), "text": raw_text}
#   {"type": "code_block", "code": [raw_code_lines]}
#   {"type": "hr"}
#   {"type": "blockquote", "blocks": [sub_blocks]}
#   {"type": "list", "ordered": bool, "start": int, "tight": bool,
#    "items": [{"content": [sub_blocks_or_lines], "task": None or bool, "start": int or None}]}
#   {"type": "blank"}


def _parse_blocks(lines, start=0, nesting=0):
    """Parse Markdown lines into a list of block dicts."""
    blocks = []
    i = start
    max_nesting = 20
    if nesting > max_nesting:
        # Treat remaining as paragraph
        if i < len(lines):
            blocks.append({"type": "paragraph", "lines": lines[i:]})
        return blocks, len(lines) - start

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip(u"\n\r")

        # Blank line
        if not stripped or not line.strip():
            i += 1
            continue

        # Fenced code block
        fence_match = re.match(r'^ {0,3}((````*)|(~~~~*))\s*(\S*)\s*$', line)
        if fence_match:
            fence_char = fence_match.group(2) or fence_match.group(3)
            fence_len = len(fence_char)
            fence_re = re.compile(
                r'^ {0,3}' + re.escape(fence_char[:1]) + r'{' + str(fence_len) + r',}\s*$'
            )
            code_lines = []
            i += 1
            while i < len(lines):
                if fence_re.match(lines[i]):
                    i += 1
                    break
                # Expand tabs
                code_line = lines[i].replace(u"\t", u"    ")
                code_lines.append(code_line)
                i += 1
            blocks.append({"type": "code_block", "code": code_lines})
            continue

        # Horizontal rule
        hr_match = re.match(r'^ {0,3}([-*_])[ \t]*\1[ \t]*\1[ \t]*$', stripped)
        if hr_match:
            blocks.append({"type": "hr"})
            i += 1
            continue

        # ATX heading
        heading_match = re.match(r'^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            blocks.append({"type": "heading", "level": level, "text": text})
            i += 1
            continue

        # Blockquote
        if re.match(r'^ {0,3}>', line):
            quote_lines = []
            while i < len(lines):
                qm = re.match(r'^ {0,3}>\s?(.*)', lines[i])
                if qm:
                    quote_lines.append(qm.group(1))
                    i += 1
                elif not lines[i].strip():
                    quote_lines.append(u"")
                    i += 1
                else:
                    break
            # Strip trailing blank lines
            while quote_lines and not quote_lines[-1].strip():
                quote_lines.pop()
            sub_blocks, _ = _parse_blocks(quote_lines, 0, nesting + 1)
            if not sub_blocks:
                sub_blocks = [{"type": "paragraph", "lines": quote_lines}]
            blocks.append({"type": "blockquote", "blocks": sub_blocks})
            continue

        # Unordered list
        ul_match = re.match(r'^( {0,3})[-*+]\s+(.*)', line)
        if ul_match:
            indent = len(ul_match.group(1))
            items, consumed = _parse_list_items(lines, i, indent, False, nesting)
            if items:
                blocks.append({"type": "list", "ordered": False, "start": 1,
                               "tight": True, "items": items})
                i += consumed
                continue

        # Ordered list
        ol_match = re.match(r'^( {0,3})(\d{1,9})[.)]\s+(.*)', line)
        if ol_match:
            indent = len(ol_match.group(1))
            start_num = int(ol_match.group(2))
            items, consumed = _parse_list_items(lines, i, indent, True, nesting)
            if items:
                blocks.append({"type": "list", "ordered": True, "start": start_num,
                               "tight": True, "items": items})
                i += consumed
                continue

        # Setext heading or paragraph
        # Collect paragraph lines
        para_lines = []
        setext_level = None
        para_start = i
        while i < len(lines):
            para_lines.append(lines[i].rstrip(u"\n\r"))
            i += 1
            # Check next line for setext underline
            if i < len(lines):
                next_stripped = lines[i].strip()
                if re.match(r'^={3,}\s*$', next_stripped):
                    setext_level = 1
                    i += 1
                    break
                if re.match(r'^-{3,}\s*$', next_stripped):
                    # Make sure it's not a list item continuation
                    # Check if previous para lines are empty
                    if para_lines and para_lines[-1].strip():
                        setext_level = 2
                        i += 1
                        break
                # Check if next line starts a different block
                next_line = lines[i]
                if not next_line.strip():
                    i += 1
                    break
                if re.match(r'^ {0,3}([-*_])[ \t]*\1[ \t]*\1[ \t]*$', next_line.strip()):
                    break
                # Other block starts
                if re.match(r'^ {0,3}>', next_line):
                    break
                if re.match(r'^ {0,3}[-*+]\s', next_line):
                    break
                if re.match(r'^ {0,3}\d{1,9}[.)]\s', next_line):
                    break
                if re.match(r'^ {0,3}#{1,6}\s', next_line):
                    break
                if re.match(r'^ {0,3}(```|~~~)', next_line):
                    break
            else:
                break

        if setext_level:
            text = u"\n".join(para_lines)
            blocks.append({"type": "heading", "level": setext_level, "text": text})
        else:
            blocks.append({"type": "paragraph", "lines": para_lines})

    return blocks, len(lines) - start


def _parse_list_items(lines, start, base_indent, ordered, nesting):
    """Parse consecutive list items starting at start."""
    items = []
    i = start
    max_nesting = 20
    if nesting > max_nesting:
        return items, 0

    # Determine if we use loose or tight
    all_blank_separators = False

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        ws = line[:len(line) - len(stripped)]

        # Check if this line starts a list item at this level
        item_match = None
        if ordered:
            item_match = re.match(r'^(\s*)(\d{1,9})[.)]\s+(.*)$', line)
            if item_match and len(item_match.group(1)) != base_indent:
                item_match = None
        else:
            item_match = re.match(r'^(\s*)[-*+]\s+(.*)$', line)
            if item_match and len(item_match.group(1)) != base_indent:
                item_match = None

        if not item_match:
            # Check for continuation (indented text)
            if items and line.strip() and len(ws) > base_indent:
                # Continuation line
                items[-1]["content_lines"].append(line)
                i += 1
                continue
            # Check for nested list
            if items and re.match(r'^(\s*)[-*+]\s', line):
                ns = re.match(r'^(\s*)[-*+]\s+(.*)$', line)
                if ns and len(ns.group(1)) > base_indent:
                    items[-1]["content_lines"].append(line)
                    i += 1
                    continue
            if items and re.match(r'^(\s*)\d{1,9}[.)]\s', line):
                ns = re.match(r'^(\s*)\d{1,9}[.)]\s+(.*)$', line)
                if ns and len(ns.group(1)) > base_indent:
                    items[-1]["content_lines"].append(line)
                    i += 1
                    continue
            break

        # Check for blank line separating items
        if items:
            # Check if there was a blank line between items
            pass

        item_indent = len(item_match.group(1))
        item_marker_content = item_match.group(2) if ordered else None
        item_content = item_match.group(2) if not ordered else item_match.group(3)

        # Task list
        task = None
        task_match = re.match(r'^\[([ xX])\]\s*(.*)', item_content)
        if task_match:
            task = task_match.group(1) in (u"x", u"X")
            item_content = task_match.group(2)

        items.append({
            "content_lines": [item_content],
            "task": task,
            "start": int(item_marker_content) if ordered and item_marker_content else None,
        })
        i += 1

        # Check for blank line (transition to loose list)
        if i < len(lines) and not lines[i].strip():
            pass  # We'll detect loose vs tight later

    # Parse content_lines into sub-blocks for each item
    for item in items:
        content_lines = item.pop("content_lines")
        if not content_lines:
            item["content"] = [{"type": "paragraph", "lines": [u""]}]
        else:
            # Check if content is simple (single line, no block structure)
            # Try to parse as blocks
            sub_blocks, _ = _parse_blocks(content_lines, 0, nesting + 1)
            if sub_blocks:
                item["content"] = sub_blocks
            else:
                item["content"] = [{"type": "paragraph", "lines": content_lines}]

    return items, i - start


# ---------------------------------------------------------------------------
# Inline Markdown parser
# ---------------------------------------------------------------------------

# Returns a list of inline tokens.
# Token types:
#   ("text", u"content")
#   ("code", u"content")
#   ("link", [(token,...)], url)
#   ("image", alt_text, url_or_None)
#   ("autolink", url)
#   ("br",)
#   Style wrappers: ("bold", [(token,...)]), ("italic", [(token,...)]),
#                   ("bold_italic", [(token,...)]), ("strike", [(token,...)])


def _parse_inline(text):
    """Parse inline Markdown into token list."""
    tokens = []
    pos = 0
    text = _to_unicode(text)
    remaining = text

    # First pass: extract code spans (they protect content)
    code_spans = []
    code_positions = []
    code_processed = u""
    cp = 0
    while cp < len(remaining):
        # Find opening backtick(s)
        if remaining[cp] == u'`':
            start = cp
            backtick_count = 0
            while cp < len(remaining) and remaining[cp] == u'`':
                backtick_count += 1
                cp += 1
            # Find matching close
            close_pos = remaining.find(u'`' * backtick_count, cp)
            if close_pos != -1:
                inner = remaining[cp:close_pos]
                # Strip one leading/trailing space if both exist
                if len(inner) >= 2 and inner[0] == u' ' and inner[-1] == u' ':
                    inner = inner[1:-1]
                code_spans.append(inner)
                code_positions.append((len(code_processed), len(code_processed) + 4))
                code_processed += u"\x00CODE%d\x00" % (len(code_spans) - 1)
                cp = close_pos + backtick_count
            else:
                # Unclosed code span, treat as literal
                code_processed += remaining[start:cp]
        else:
            code_processed += remaining[cp]
            cp += 1

    # Second pass: link/image/autolink detection on code_processed
    # We use a stepwise approach
    segments = _parse_inline_core(code_processed)

    # Re-insert code spans
    result = []
    for seg in segments:
        if seg[0] == "text":
            t = seg[1]
            # Replace code placeholders
            while u"\x00CODE" in t:
                m = re.search(r'\x00CODE(\d+)\x00', t)
                if m:
                    idx = int(m.group(1))
                    before = t[:m.start()]
                    after = t[m.end():]
                    if before:
                        result.append(("text", before))
                    if idx < len(code_spans):
                        result.append(("code", code_spans[idx]))
                    t = after
                else:
                    break
            if t:
                result.append(("text", t))
        else:
            result.append(seg)

    return result


def _parse_inline_core(text):
    """Parse inline formatting in text (code spans already extracted)."""
    # Process: escapes, links, images, autolinks, emphasis, strikethrough
    # Use a character scanner approach

    tokens = []
    pos = 0
    len_text = len(text)

    while pos < len_text:
        ch = text[pos]

        # Hard line break: trailing spaces or backslash
        if ch == u'\\' and pos + 1 < len_text:
            next_ch = text[pos + 1]
            # Check if this is a hard line break
            if next_ch == u'\n':
                tokens.append(("br",))
                pos += 2
                continue
            # Escaped character
            escaped = _is_escapable(next_ch)
            if escaped:
                tokens.append(("text", next_ch))
                pos += 2
                continue
            else:
                tokens.append(("text", ch))
                pos += 1
                continue

        if ch == u'\n':
            tokens.append(("text", u"\n"))
            pos += 1
            continue

        # Autolink <url>
        if ch == u'<':
            # Check for autolink
            close = text.find(u'>', pos + 1)
            if close != -1:
                inner = text[pos + 1:close]
                # Check if it looks like a URL or email
                if re.match(r'^[a-zA-Z][a-zA-Z0-9+\-.]*:', inner):
                    # URL scheme
                    url = inner
                    if _validate_url(u"<" + inner + u">"):
                        tokens.append(("autolink", url))
                        pos = close + 1
                        continue
                elif u"@" in inner and u"." in inner:
                    tokens.append(("autolink", inner))
                    pos = close + 1
                    continue

        # Image ![alt](url)
        if ch == u'!' and pos + 1 < len_text and text[pos + 1] == u'[':
            close_bracket = text.find(u']', pos + 2)
            if close_bracket != -1 and close_bracket + 1 < len_text and text[close_bracket + 1] == u'(':
                close_paren = _find_paren_end(text, close_bracket + 1)
                if close_paren != -1:
                    alt = text[pos + 2:close_bracket]
                    link_text = text[close_bracket + 2:close_paren]
                    url = _parse_link_target(link_text)
                    if not alt:
                        alt = u"image"
                    tokens.append(("image", alt, url))
                    pos = close_paren + 1
                    continue

        # Link [text](url)
        if ch == u'[':
            close_bracket = text.find(u']', pos + 1)
            if close_bracket != -1 and close_bracket + 1 < len_text and text[close_bracket + 1] == u'(':
                close_paren = _find_paren_end(text, close_bracket + 1)
                if close_paren != -1:
                    inner_text = text[pos + 1:close_bracket]
                    link_text = text[close_bracket + 2:close_paren]
                    url = _parse_link_target(link_text)
                    if url:
                        # Parse inner text for inline formatting
                        inner_tokens = _parse_inline_core(inner_text)
                        tokens.append(("link", inner_tokens, url))
                    else:
                        # No valid URL, render as plain text
                        tokens.append(("text", u"[" + inner_text + u"]()"))
                    pos = close_paren + 1
                    continue

        # Strikethrough ~~text~~
        if ch == u'~' and pos + 1 < len_text and text[pos + 1] == u'~':
            close = text.find(u'~~', pos + 2)
            if close != -1:
                inner = text[pos + 2:close]
                inner_tokens = _parse_inline_core(inner)
                tokens.append(("strike", inner_tokens))
                pos = close + 2
                continue

        # Bold-italic ***text***
        if ch == u'*' and pos + 2 < len_text and text[pos + 1] == u'*' and text[pos + 2] == u'*':
            close = text.find(u'***', pos + 3)
            if close != -1:
                inner = text[pos + 3:close]
                inner_tokens = _parse_inline_core(inner)
                tokens.append(("bold_italic", inner_tokens))
                pos = close + 3
                continue

        # Bold **text** (not followed by *)
        if ch == u'*' and pos + 1 < len_text and text[pos + 1] == u'*' and (pos + 2 >= len_text or text[pos + 2] != u'*'):
            close = text.find(u'**', pos + 2)
            if close != -1 and (close + 2 >= len_text or text[close + 2] != u'*'):
                inner = text[pos + 2:close]
                inner_tokens = _parse_inline_core(inner)
                tokens.append(("bold", inner_tokens))
                pos = close + 2
                continue

        # Italic *text*
        if ch == u'*' and (pos + 1 >= len_text or text[pos + 1] != u'*'):
            # Check for word boundary: not between non-whitespace chars on both sides
            close = text.find(u'*', pos + 1)
            while close != -1:
                # Make sure it's not a ** start
                if close + 1 < len_text and text[close + 1] == u'*':
                    close = text.find(u'*', close + 1)
                    continue
                inner = text[pos + 1:close]
                if inner:
                    inner_tokens = _parse_inline_core(inner)
                    tokens.append(("italic", inner_tokens))
                    pos = close + 1
                    break
                close = text.find(u'*', close + 1)
            else:
                tokens.append(("text", ch))
                pos += 1
            continue

        # Bold __text__ (with word boundaries)
        if ch == u'_' and pos + 1 < len_text and text[pos + 1] == u'_':
            # Check word boundary before
            if pos > 0 and re.match(r'\w', text[pos - 1]):
                tokens.append(("text", ch))
                pos += 1
                continue
            close = text.find(u'__', pos + 2)
            if close != -1:
                # Check word boundary after
                if close + 2 < len_text and re.match(r'\w', text[close + 2]):
                    tokens.append(("text", ch))
                    pos += 1
                    continue
                inner = text[pos + 2:close]
                inner_tokens = _parse_inline_core(inner)
                tokens.append(("bold", inner_tokens))
                pos = close + 2
                continue

        # Italic _text_ (with word boundaries)
        if ch == u'_' and (pos + 1 >= len_text or text[pos + 1] != u'_'):
            if pos > 0 and re.match(r'\w', text[pos - 1]):
                tokens.append(("text", ch))
                pos += 1
                continue
            close = text.find(u'_', pos + 1)
            while close != -1:
                if close + 1 < len_text and text[close + 1] == u'_':
                    close = text.find(u'_', close + 1)
                    continue
                if close + 1 < len_text and re.match(r'\w', text[close + 1]):
                    close = text.find(u'_', close + 1)
                    continue
                inner = text[pos + 1:close]
                if inner:
                    inner_tokens = _parse_inline_core(inner)
                    tokens.append(("italic", inner_tokens))
                    pos = close + 1
                    break
                close = text.find(u'_', close + 1)
            else:
                tokens.append(("text", ch))
                pos += 1
            continue

        # Plain text
        tokens.append(("text", ch))
        pos += 1

    return tokens


def _is_escapable(ch):
    return ch in u"\\`*_{}[]()#+-.!>~|"


def _find_paren_end(text, start):
    """Find matching close paren, handling nested parens."""
    depth = 1
    pos = start + 1
    while pos < len(text) and depth > 0:
        if text[pos] == u'(':
            depth += 1
        elif text[pos] == u')':
            depth -= 1
        elif text[pos] == u'"' or text[pos] == u"'":
            # Skip quoted strings
            quote = text[pos]
            pos += 1
            while pos < len(text) and text[pos] != quote:
                if text[pos] == u'\\':
                    pos += 1
                pos += 1
        pos += 1
    if depth == 0:
        return pos - 1
    return -1


def _parse_link_target(text):
    """Parse URL from link target text, handling optional title."""
    text = text.strip()
    # Angle-bracket URL
    if text.startswith(u"<"):
        close = text.find(u">")
        if close != -1:
            url = text[1:close].strip()
            return url
        return None
    # Regular URL with optional title
    # Split on whitespace
    parts = text.split(None, 1)
    if parts:
        url = parts[0].strip()
        if url.startswith(u"<") and url.endswith(u">"):
            url = url[1:-1]
        return url
    return None


def _inline_tokens_to_flat(tokens):
    """Flatten nested inline tokens to a list of (text, style_bits, link_url)."""
    result = []

    def _normalize(flags):
        if not flags:
            return u""
        order = u"bisc"
        return u"".join(sorted(set(flags), key=lambda x: order.index(x) if x in order else 99))

    def _flatten(token_list, style_flags, link_url):
        for token in token_list:
            ttype = token[0]
            if ttype == "text":
                result.append((token[1], _normalize(style_flags), link_url))
            elif ttype == "code":
                result.append((token[1], _normalize(style_flags + u"c"), link_url))
            elif ttype == "br":
                result.append((u"\n", _normalize(style_flags), link_url))
            elif ttype == "link":
                _flatten(token[1], style_flags, token[2])
            elif ttype == "image":
                alt = token[1]
                img_url = token[2]
                nf = _normalize(style_flags)
                if img_url:
                    result.append((u"[image: " + alt + u"]", nf, img_url))
                else:
                    result.append((u"[image: " + alt + u"]", nf, None))
            elif ttype == "autolink":
                url = token[1]
                result.append((url, _normalize(style_flags), url))
            elif ttype == "bold":
                _flatten(token[1], style_flags + u"b", link_url)
            elif ttype == "italic":
                _flatten(token[1], style_flags + u"i", link_url)
            elif ttype == "bold_italic":
                _flatten(token[1], style_flags + u"bi", link_url)
            elif ttype == "strike":
                _flatten(token[1], style_flags + u"s", link_url)

    _flatten(tokens, u"", None)
    return result


# ---------------------------------------------------------------------------
# Application class
# ---------------------------------------------------------------------------

CONFIG_DIR_ENV = u"APPDATA"
CONFIG_SUBDIR = u"mdxp"
CONFIG_FILE = u"mdxp.ini"


class MdxpViewer(object):
    def __init__(self, initial_file=None):
        self.root = tk.Tk()
        self.root.title(u"mdxp")
        self.root.geometry(u"800x600")

        self.current_file = None
        self.file_content = None
        self.file_encoding = None
        self.current_encoding = "utf-8"
        self._link_tags = {}
        self._link_counter = 0
        self._tag_fonts = {}
        self._rendered_blocks = None
        self._scroll_pos = u"1.0"
        self._find_dialog = None
        self._last_find_pattern = None
        self._last_find_match_case = False
        self._recent_files = []
        self._press_x = 0
        self._press_y = 0
        self._config_loaded = False

        # Settings
        self._word_wrap = True
        self._toolbar_visible = True
        self._statusbar_visible = True
        self._font_size = 11
        self._base_family = None

        # Status bar info
        self._status_file = u"No file loaded"
        self._status_encoding = u""
        self._status_lines = u""
        self._status_chars = u""

        self._setup_fonts()
        self._create_widgets()
        self._create_menu()
        self._bind_keys()
        self._load_config()

        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)
        self.root.minsize(400, 200)

        if initial_file:
            self.open_file(initial_file)

    # -----------------------------------------------------------------------
    # Font setup
    # -----------------------------------------------------------------------

    def _setup_fonts(self):
        family = u"MS Sans Serif"
        size = self._font_size

        try:
            try:
                default_font = tkFont.nametofont("TkDefaultFont")
            except AttributeError:
                default_font = tkFont.Font(name="TkDefaultFont", exist=True)
            actual_family = default_font.actual("family")
            if actual_family:
                family = _to_unicode(actual_family)
        except Exception:
            pass

        if not family:
            family = u"MS Sans Serif"
        if not size or size < 6:
            size = 11

        self._base_family = family
        self._font_size = size
        self._init_tag_fonts()

    def _init_tag_fonts(self):
        """Create all tkFont.Font objects and configure tags."""
        family = self._base_family
        size = self._font_size
        code_family = u"Courier New"

        # Store font objects to prevent garbage collection
        self._tag_fonts = {}

        # Body font
        body_font = tkFont.Font(family=family, size=size)
        self._tag_fonts["body"] = body_font

        # Simple styles
        style_defs = {
            "b":      {"weight": "bold"},
            "i":      {"slant": "italic"},
            "bi":     {"weight": "bold", "slant": "italic"},
        }
        for tag, kw in style_defs.items():
            f = tkFont.Font(family=family, size=size, **kw)
            self._tag_fonts[tag] = f

        # Strikethrough - use overstrike if supported
        try:
            strike_font = tkFont.Font(family=family, size=size, overstrike=True)
            self._tag_fonts["s"] = strike_font
        except Exception:
            pass
        for combo in ["bs", "is", "bis"]:
            kw = {"weight": "bold"} if "b" in combo else {}
            kw.update({"slant": "italic"} if "i" in combo else {})
            try:
                f = tkFont.Font(family=family, size=size, overstrike=True, **kw)
                self._tag_fonts[combo] = f
            except Exception:
                pass

        # Code fonts
        code_sizes = [size, size, size, size]
        code_styles = [
            ("c", {}),
            ("cb", {"weight": "bold"}),
            ("ci", {"slant": "italic"}),
            ("cbi", {"weight": "bold", "slant": "italic"}),
        ]
        for (tag, kw) in code_styles:
            f = tkFont.Font(family=code_family, size=size, **kw)
            self._tag_fonts[tag] = f

        # Heading fonts - relative sizes
        h_offsets = [8, 6, 4, 2, 1, 0]
        for level in range(1, 7):
            h_size = max(6, size + h_offsets[level - 1])
            # hN (bold only)
            tag = u"h%d" % level
            f = tkFont.Font(family=family, size=h_size, weight="bold")
            self._tag_fonts[tag] = f
            # hN_i (bold + italic)
            tag_i = u"h%d_i" % level
            f_i = tkFont.Font(family=family, size=h_size, weight="bold", slant="italic")
            self._tag_fonts[tag_i] = f_i

        # Configure text widget tags
        self._configure_tags()

    def _configure_tags(self):
        """Set up all static tag configurations on the text widget."""
        t = getattr(self, 'text', None)
        if not t:
            return

        # Remove old dynamic tags
        for tag in list(self._tag_fonts.keys()):
            try:
                t.tag_delete(tag)
            except Exception:
                pass

        # Body
        if "body" in self._tag_fonts:
            t.tag_configure("body", font=self._tag_fonts["body"])

        # Style tags
        for tag in ["b", "i", "bi", "s", "bs", "is", "bis",
                     "c", "cb", "ci", "cbi"]:
            if tag in self._tag_fonts:
                t.tag_configure(tag, font=self._tag_fonts[tag])

        # Heading tags
        for level in range(1, 7):
            h_tag = u"h%d" % level
            h_i_tag = u"h%d_i" % level
            spacing1 = 14 - level
            spacing3 = 8 - level
            if spacing1 < 4:
                spacing1 = 4
            if spacing3 < 2:
                spacing3 = 2
            if h_tag in self._tag_fonts:
                t.tag_configure(h_tag, font=self._tag_fonts[h_tag],
                                spacing1=spacing1, spacing3=spacing3)
            if h_i_tag in self._tag_fonts:
                t.tag_configure(h_i_tag, font=self._tag_fonts[h_i_tag],
                                spacing1=spacing1, spacing3=spacing3)

        # Code block
        code_family = u"Courier New"
        cblock_font = tkFont.Font(family=code_family, size=self._font_size)
        t.tag_configure("codeblock", font=cblock_font,
                        background="#f5f5f5", foreground="#333333",
                        spacing1=1, spacing3=1,
                        lmargin1=24, lmargin2=24)
        self._tag_fonts["_codeblock_font"] = cblock_font

        # Horizontal rule
        t.tag_configure("hr", foreground="#aaaaaa")

        # Blockquote levels
        for level in range(1, 11):
            tag = u"quote%d" % level
            margin = 16 + level * 16
            color = u"#%02x%02x%02x" % (80 - level * 4, 80 - level * 4, 80 - level * 4)
            t.tag_configure(tag, lmargin1=margin, lmargin2=margin,
                            foreground=color)

        # Find match highlight
        t.tag_configure("find_match", background="#ffff00")

    def _update_fonts(self):
        """Recreate all fonts after font size change."""
        # Save visible view position before re-render
        view_fraction = None
        try:
            view_fraction = self.text.yview()[0]
        except Exception:
            pass

        self._init_tag_fonts()
        if hasattr(self, "text") and self.text:
            self._configure_tags()
            # Update Text widget default font so untagged text uses new size
            if "body" in self._tag_fonts:
                self.text.configure(font=self._tag_fonts["body"])
            if self._rendered_blocks:
                tw = self.text
                tw.config(state=tk.NORMAL)
                tw.delete(u"1.0", tk.END)

                # Clean up old link tags
                for tag_name in list(self._link_tags.keys()):
                    try:
                        tw.tag_delete(tag_name)
                    except Exception:
                        pass
                self._link_tags.clear()
                self._link_counter = 0

                # Re-render from stored blocks
                self._render_blocks(self._rendered_blocks)

                tw.config(state=tk.DISABLED)

                # Restore visible view position
                if view_fraction is not None:
                    try:
                        self.text.yview_moveto(view_fraction)
                    except Exception:
                        pass

    # -----------------------------------------------------------------------
    # Menu
    # -----------------------------------------------------------------------

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label=u"File", menu=file_menu)
        file_menu.add_command(label=u"Open...", command=self._prompt_open,
                              accelerator=u"Ctrl+O")
        file_menu.add_command(label=u"Reload", command=self._reload_file,
                              accelerator=u"F5")
        self._reopen_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label=u"Reopen with Encoding",
                              menu=self._reopen_menu)
        for enc in [u"UTF-8", u"CP1251", u"Latin-1", u"System ANSI"]:
            self._reopen_menu.add_command(
                label=enc,
                command=lambda e=enc: self._reopen_encoding(e))
        file_menu.add_separator()
        self._recent_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label=u"Recent Files", menu=self._recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label=u"Exit", command=self._on_exit,
                              accelerator=u"Alt+F4")

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label=u"Edit", menu=edit_menu)
        edit_menu.add_command(label=u"Copy", command=self._copy_selection,
                              accelerator=u"Ctrl+C")
        edit_menu.add_command(label=u"Select All", command=self._select_all,
                              accelerator=u"Ctrl+A")
        edit_menu.add_separator()
        edit_menu.add_command(label=u"Find...", command=self._show_find,
                              accelerator=u"Ctrl+F")
        edit_menu.add_command(label=u"Find Next", command=self._find_next,
                              accelerator=u"F3")
        edit_menu.add_command(label=u"Find Previous",
                              command=self._find_previous,
                              accelerator=u"Shift+F3")

        # View menu
        view_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label=u"View", menu=view_menu)
        self._toolbar_var = tk.BooleanVar(value=self._toolbar_visible)
        view_menu.add_checkbutton(label=u"Toolbar", onvalue=True,
                                  offvalue=False,
                                  variable=self._toolbar_var,
                                  command=self._toggle_toolbar)
        self._statusbar_var = tk.BooleanVar(value=self._statusbar_visible)
        view_menu.add_checkbutton(label=u"Status Bar", onvalue=True,
                                  offvalue=False,
                                  variable=self._statusbar_var,
                                  command=self._toggle_statusbar)
        view_menu.add_separator()
        self._wrap_var = tk.BooleanVar(value=self._word_wrap)
        view_menu.add_checkbutton(label=u"Word Wrap", onvalue=True,
                                  offvalue=False,
                                  variable=self._wrap_var,
                                  command=self._toggle_wrap,
                                  accelerator=u"Ctrl+W")
        view_menu.add_separator()
        view_menu.add_command(label=u"Increase Font Size",
                              command=self._font_zoom_in,
                              accelerator=u"Ctrl++")
        view_menu.add_command(label=u"Decrease Font Size",
                              command=self._font_zoom_out,
                              accelerator=u"Ctrl+-")
        view_menu.add_command(label=u"Reset Font Size",
                              command=self._font_reset,
                              accelerator=u"Ctrl+0")

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label=u"Help", menu=help_menu)
        help_menu.add_command(label=u"About", command=self._show_about)

    # -----------------------------------------------------------------------
    # Widgets
    # -----------------------------------------------------------------------

    def _create_widgets(self):
        # Main container with grid
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Toolbar
        self._toolbar_frame = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        self._toolbar_frame.grid(row=0, column=0, sticky="ew")
        self._create_toolbar()

        # Text area + vertical scrollbar
        text_frame = tk.Frame(self.root)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame, wrap=tk.WORD, state=tk.DISABLED,
            padx=10, pady=10,
            relief=tk.SUNKEN, bd=2,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.configure(font=self._tag_fonts["body"])

        v_scroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                command=self.text.yview)
        v_scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=v_scroll.set)
        self._v_scroll = v_scroll

        # Horizontal scrollbar (hidden by default)
        self._h_scroll_frame = tk.Frame(self.root)
        self._h_scroll_frame.grid(row=3, column=0, sticky="ew")
        h_scroll = tk.Scrollbar(self._h_scroll_frame, orient=tk.HORIZONTAL,
                                command=self.text.xview)
        h_scroll.pack(fill=tk.X)
        self.text.configure(xscrollcommand=h_scroll.set)
        self._h_scroll = h_scroll
        self._h_scroll_frame.grid_remove()

        # Status bar
        self._status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        self._status_frame.grid(row=4, column=0, sticky="ew")

        self._status_file_label = tk.Label(
            self._status_frame, text=u"No file loaded",
            anchor=tk.W, padx=4)
        self._status_file_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._status_extra_label = tk.Label(
            self._status_frame, text=u"", anchor=tk.E, padx=4)
        self._status_extra_label.pack(side=tk.RIGHT)

        # Set initial wrap
        self._apply_wrap()

        # Focus + events
        self.text.focus_set()
        self.text.bind("<Button-1>", self._on_button_press)
        self.text.bind("<ButtonRelease-1>", self._on_text_click)
        self.text.bind("<Button-3>", self._on_context_menu)
        if sys.platform == "win32":
            self.text.bind("<MouseWheel>", self._on_mousewheel)

        self._define_tags()

    def _create_toolbar(self):
        toolbar = self._toolbar_frame

        btn_open = tk.Button(toolbar, text=u"Open", command=self._prompt_open)
        btn_open.pack(side=tk.LEFT, padx=2, pady=2)

        self._btn_reload = tk.Button(toolbar, text=u"Reload",
                                     command=self._reload_file)
        self._btn_reload.pack(side=tk.LEFT, padx=2, pady=2)

        btn_find = tk.Button(toolbar, text=u"Find",
                             command=self._show_find)
        btn_find.pack(side=tk.LEFT, padx=2, pady=2)

        btn_wrap = tk.Button(toolbar, text=u"Word Wrap",
                             command=self._toggle_wrap)
        btn_wrap.pack(side=tk.LEFT, padx=2, pady=2)

    def _define_tags(self):
        self._configure_tags()

    def _get_or_create_style_tag(self, style_flags, default_tag=None):
        """Get or create a combined style tag name."""
        if not style_flags and not default_tag:
            return None
        if not style_flags and default_tag:
            return default_tag

        combined = style_flags
        if default_tag and default_tag != u"body":
            combined = default_tag + u"_" + combined if combined else default_tag

        if not combined:
            return None

        # Check if tag exists
        t = self.text
        try:
            existing = t.tag_cget(combined, "font")
            return combined
        except Exception:
            pass

        # Create combined font dynamically
        family = self._base_family
        size = self._font_size
        weight = "normal"
        slant = "roman"
        overstrike = False

        # Check if it's a heading combination
        heading_match = re.match(r'^h(\d+)(?:_(.*))?$', combined)
        if heading_match:
            level = int(heading_match.group(1))
            rest = heading_match.group(2) or u""
            h_offsets = [8, 6, 4, 2, 1, 0]
            h_size = max(6, size + h_offsets[level - 1])
            size = h_size
            weight = "bold"
            if u"i" in rest:
                slant = "italic"
            if u"b" in rest:
                weight = "bold"
            if u"s" in rest:
                overstrike = True
        elif combined.startswith(u"c"):
            family = u"Courier New"
            rest = combined[1:] if len(combined) > 1 else u""
            if u"b" in rest:
                weight = "bold"
            if u"i" in rest:
                slant = "italic"
        else:
            if u"b" in combined:
                weight = "bold"
            if u"i" in combined:
                slant = "italic"
            if u"s" in combined:
                overstrike = True

        try:
            font_kw = {"family": family, "size": size, "weight": weight,
                       "slant": slant}
            if overstrike:
                font_kw["overstrike"] = True
            f = tkFont.Font(**font_kw)
            self._tag_fonts[combined] = f
            self.text.tag_configure(combined, font=f)
        except Exception:
            pass

        return combined

    def _ensure_font_exists(self, tag_name, font_kw):
        """Create a font object if not already cached."""
        if tag_name in self._tag_fonts:
            return self._tag_fonts[tag_name]
        try:
            f = tkFont.Font(**font_kw)
            self._tag_fonts[tag_name] = f
            return f
        except Exception:
            return None

    # -----------------------------------------------------------------------
    # Key bindings
    # -----------------------------------------------------------------------

    def _bind_keys(self):
        self.root.bind(u"<Control-o>", lambda e: self._prompt_open())
        self.root.bind(u"<Control-O>", lambda e: self._prompt_open())
        self.root.bind(u"<F5>", lambda e: self._reload_file())
        self.root.bind(u"<Control-a>", lambda e: self._select_all())
        self.root.bind(u"<Control-A>", lambda e: self._select_all())
        self.root.bind(u"<Control-c>", lambda e: self._copy_selection())
        self.root.bind(u"<Control-C>", lambda e: self._copy_selection())
        self.root.bind(u"<Control-f>", lambda e: self._show_find())
        self.root.bind(u"<Control-F>", lambda e: self._show_find())
        self.root.bind(u"<F3>", lambda e: self._find_next())
        self.root.bind(u"<Shift-F3>", lambda e: self._find_previous())
        self.root.bind(u"<Control-w>", lambda e: self._toggle_wrap())
        self.root.bind(u"<Control-W>", lambda e: self._toggle_wrap())
        self.root.bind(u"<Control-plus>", lambda e: self._font_zoom_in())
        self.root.bind(u"<Control-equal>", lambda e: self._font_zoom_in())
        self.root.bind(u"<Control-KP_Add>", lambda e: self._font_zoom_in())
        self.root.bind(u"<Control-minus>", lambda e: self._font_zoom_out())
        self.root.bind(u"<Control-KP_Subtract>", lambda e: self._font_zoom_out())
        self.root.bind(u"<Control-0>", lambda e: self._font_reset())
        self.root.bind(u"<Control-Key-0>", lambda e: self._font_reset())

        # No editing key bindings needed; text widget state=DISABLED prevents editing
        # while still allowing selection and copy.

    # -----------------------------------------------------------------------
    # File operations
    # -----------------------------------------------------------------------

    def _prompt_open(self):
        initial_dir = None
        if self.current_file:
            initial_dir = os.path.dirname(self.current_file)
        path = tkFileDialog.askopenfilename(
            parent=self.root,
            title=u"Open Markdown File",
            initialdir=initial_dir,
            filetypes=[
                (u"Markdown files", u"*.md *.markdown *.mdown *.mdwn *.mkd"),
                (u"All files", u"*.*"),
            ],
        )
        if path:
            path = _to_unicode(path)
            self.open_file(path)

    def open_file(self, path):
        path = _sanitize_text(path)
        if not path or not os.path.isfile(path):
            tkMessageBox.showerror(u"Error", u"File not found:\n" + path)
            return

        # Save scroll position before reload
        try:
            self._scroll_pos = self.text.index(tk.INSERT)
        except Exception:
            self._scroll_pos = u"1.0"

        old_file = self.current_file
        self.current_file = path
        content = None
        self.current_encoding = u"utf-8"

        # Try encoding detection
        for enc in (u"utf-8-sig", u"utf-8", u"cp1251", u"latin-1"):
            try:
                with codecs.open(path, "r", encoding=enc) as f:
                    content = f.read()
                self.file_encoding = enc
                if enc == u"utf-8-sig":
                    self.file_encoding = u"utf-8-sig"
                    self.current_encoding = u"utf-8-sig"
                elif enc == u"utf-8":
                    self.current_encoding = u"utf-8"
                elif enc == u"cp1251":
                    self.current_encoding = u"cp1251"
                elif enc == u"latin-1":
                    self.current_encoding = u"latin-1"
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                tkMessageBox.showerror(
                    u"Error",
                    u"Could not read file:\n" + _sanitize_exception(e))
                self.current_file = old_file
                return

        if content is None:
            tkMessageBox.showerror(
                u"Error",
                u"Could not decode file.\n"
                u"Tried: UTF-8 (with/without BOM), CP1251, Latin-1.\n"
                u"Use File > Reopen with Encoding.")
            self.current_file = old_file
            return

        self.file_content = content
        self.root.title(u"mdxp - " + _sanitize_text(os.path.basename(path)))
        self._render_markdown(content)

        # Add to recent files
        self._add_recent(path)

        # Update reload button state
        self._update_ui_state()

    def _reload_file(self):
        if not self.current_file:
            return
        # Save visible view position before reload
        try:
            view_frac = self.text.yview()[0]
        except Exception:
            view_frac = None
        self.open_file(self.current_file)
        # Restore visible view position after reload
        if view_frac is not None:
            try:
                self.text.yview_moveto(view_frac)
            except Exception:
                pass

    def _reopen_encoding(self, enc_name):
        if not self.current_file:
            return
        path = self.current_file
        enc_map = {
            u"UTF-8": u"utf-8",
            u"CP1251": u"cp1251",
            u"Latin-1": u"latin-1",
            u"System ANSI": u"mbcs",
        }
        enc = enc_map.get(enc_name, u"utf-8")
        try:
            with codecs.open(path, "r", encoding=enc) as f:
                content = f.read()
        except (UnicodeDecodeError, UnicodeError) as e:
            tkMessageBox.showerror(
                u"Encoding Error",
                u"Could not decode file with " + enc_name + u":\n" +
                _sanitize_exception(e))
            return
        except Exception as e:
            tkMessageBox.showerror(
                u"Error",
                u"Could not read file:\n" + _sanitize_exception(e))
            return

        self.file_content = content
        self.file_encoding = enc
        self.current_encoding = enc
        self._render_markdown(content)
        self._update_status()

    def _add_recent(self, path):
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        if len(self._recent_files) > 5:
            self._recent_files = self._recent_files[:5]
        self._update_recent_menu()
        self._save_config()

    def _update_recent_menu(self):
        self._recent_menu.delete(0, tk.END)
        for path in self._recent_files:
            label = os.path.basename(path) if path else u"?"
            if len(label) > 50:
                label = label[:47] + u"..."
            self._recent_menu.add_command(
                label=label,
                command=lambda p=path: self._open_recent(p))

    def _open_recent(self, path):
        if not os.path.isfile(path):
            tkMessageBox.showerror(u"Error", u"File not found:\n" + path)
            if path in self._recent_files:
                self._recent_files.remove(path)
                self._update_recent_menu()
                self._save_config()
            return
        self.open_file(path)

    def _update_ui_state(self):
        state = tk.NORMAL if self.current_file else tk.DISABLED
        try:
            self._btn_reload.configure(state=state)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Markdown rendering
    # -----------------------------------------------------------------------

    def _render_markdown(self, text):
        tw = self.text
        tw.config(state=tk.NORMAL)
        start_time = time.time()

        try:
            tw.delete(u"1.0", tk.END)

            # Clean up old link tags
            for tag_name in list(self._link_tags.keys()):
                try:
                    tw.tag_delete(tag_name)
                except Exception:
                    pass
            self._link_tags.clear()
            self._link_counter = 0

            text = _sanitize_text(text)
            lines = text.splitlines(True)

            # Parse blocks
            blocks, _ = _parse_blocks(lines)

            # Store for potential re-render (e.g., font change)
            self._rendered_blocks = blocks

            # Render blocks
            self._render_blocks(blocks)

        finally:
            tw.config(state=tk.DISABLED)
            # Update status bar
            elapsed = int((time.time() - start_time) * 1000)
            self._update_status(elapsed)

            # Restore scroll position
            self._restore_scroll()

    def _render_blocks(self, blocks):
        tw = self.text
        for block in blocks:
            try:
                self._render_block(tw, block, 0)
            except Exception:
                pass

    def _render_block(self, tw, block, quote_level):
        btype = block.get(u"type")

        if btype == u"paragraph":
            self._render_paragraph(tw, block, quote_level)

        elif btype == u"heading":
            self._render_heading(tw, block, quote_level)

        elif btype == u"code_block":
            self._render_code_block(tw, block)

        elif btype == u"hr":
            tw.insert(tk.END, u"\u2500" * 40 + u"\n", u"hr")

        elif btype == u"blockquote":
            for sub in block.get(u"blocks", []):
                self._render_block(tw, sub, min(quote_level + 1, 10))

        elif btype == u"list":
            self._render_list(tw, block, quote_level)

        elif btype == u"blank":
            tw.insert(tk.END, u"\n")

    def _render_paragraph(self, tw, block, quote_level):
        lines = block.get(u"lines", [])
        if not lines:
            return

        # Process hard line breaks
        processed_lines = []
        for line in lines:
            stripped_line = line.rstrip(u"\n\r")
            # Check for hard break (trailing spaces or backslash)
            hard_break = False
            if stripped_line.endswith(u"  "):
                hard_break = True
                stripped_line = stripped_line.rstrip(u" ")
            elif stripped_line.endswith(u"\\"):
                hard_break = True
                stripped_line = stripped_line[:-1].rstrip()

            processed_lines.append(stripped_line)
            if hard_break:
                processed_lines.append(u"__HARD_BREAK__")

        # Join, handling hard breaks
        final_text = u""
        for i, pl in enumerate(processed_lines):
            if pl == u"__HARD_BREAK__":
                final_text += u"\n"
            elif i > 0 and processed_lines[i - 1] != u"__HARD_BREAK__":
                if final_text and not final_text.endswith(u"\n"):
                    final_text += u" "
                final_text += pl
            else:
                final_text += pl

        # Parse inline
        tokens = _parse_inline(final_text)
        flat = _inline_tokens_to_flat(tokens)

        base_tag = None
        if quote_level > 0:
            base_tag = u"quote%d" % quote_level

        self._emit_flat(tw, flat, base_tag)

        # End paragraph
        tw.insert(tk.END, u"\n\n")

    def _render_heading(self, tw, block, quote_level):
        level = block.get(u"level", 1)
        if level < 1:
            level = 1
        if level > 6:
            level = 6
        text = block.get(u"text", u"")

        tokens = _parse_inline(text)
        flat = _inline_tokens_to_flat(tokens)

        base_tag = u"h%d" % level
        self._emit_flat(tw, flat, base_tag)
        tw.insert(tk.END, u"\n\n")

    def _render_code_block(self, tw, block):
        code = block.get(u"code", [])
        if not code:
            tw.insert(tk.END, u"\n")
            return

        tw.insert(tk.END, u"\n")
        for line in code:
            # In code blocks, we escape < and > for safety but keep everything else
            safe_line = line.replace(u"\t", u"    ")
            tw.insert(tk.END, safe_line + u"\n", u"codeblock")
        tw.insert(tk.END, u"\n")

    def _render_list(self, tw, block, quote_level):
        ordered = block.get(u"ordered", False)
        items = block.get(u"items", [])
        start = block.get(u"start", 1)

        for idx, item in enumerate(items):
            task = item.get(u"task")
            content = item.get(u"content", [])

            prefix = u""
            if ordered:
                num = start + idx if start else idx + 1
                prefix = u"%d. " % num
            else:
                prefix = u"\u2022 "

            # Task prefix
            task_prefix = u""
            if task is not None:
                if task:
                    task_prefix = u"[x] "
                else:
                    task_prefix = u"[ ] "

            # Calculate indent for list (for nested lists inside items)
            list_indent = len(prefix) + len(task_prefix)

            # Insert the bullet/number + task prefix
            tag = None
            if quote_level > 0:
                tag = u"quote%d" % quote_level
            if tag:
                tw.insert(tk.END, prefix + task_prefix, tag)
            else:
                tw.insert(tk.END, prefix + task_prefix)

            # Render item content
            for sub in content:
                if sub.get(u"type") == u"paragraph":
                    lines = sub.get(u"lines", [])
                    text = u" ".join(l.rstrip(u"\n\r") for l in lines)
                    tokens = _parse_inline(text)
                    flat = _inline_tokens_to_flat(tokens)
                    self._emit_flat(tw, flat, tag)
                elif sub.get(u"type") == u"list":
                    # Nested list - indent more
                    self._render_list(tw, sub, quote_level)
                else:
                    self._render_block(tw, sub, quote_level)

            tw.insert(tk.END, u"\n")

        tw.insert(tk.END, u"\n")

    # -----------------------------------------------------------------------
    # Inline emission
    # -----------------------------------------------------------------------

    def _emit_flat(self, tw, flat_tokens, base_tag):
        for text, style_flags, link_url in flat_tokens:
            if not text:
                continue

            # Build tags list
            tags = []
            if base_tag:
                tags.append(base_tag)

            # Determine style tag
            style_tag = self._resolve_style_tag(style_flags, base_tag)
            if style_tag:
                tags.append(style_tag)

            # Link handling
            if link_url:
                self._link_counter += 1
                link_tag = u"lnk_%d" % self._link_counter
                self._link_tags[link_tag] = link_url
                try:
                    tw.tag_configure(link_tag, foreground=u"#0000cc",
                                     underline=True)
                except Exception:
                    pass
                tags.append(link_tag)

            # Insert if we have text
            if text:
                if tags:
                    tw.insert(tk.END, text, tuple(tags))
                else:
                    tw.insert(tk.END, text)

    def _resolve_style_tag(self, style_flags, base_tag):
        """Get a tag name for the given style flags and base context."""
        if not style_flags:
            return None

        # Determine tag name
        if base_tag and base_tag.startswith(u"h") and len(base_tag) < 4:
            # Heading context
            if style_flags == u"i":
                return base_tag + u"_i"
            if style_flags == u"c":
                return u"c"
            # For bold in heading (redundant) or bold-italic
            tag_name = self._get_or_create_style_tag(style_flags, base_tag)
            return tag_name

        if style_flags.startswith(u"c"):
            # Code style
            return self._get_or_create_style_tag(style_flags, None)

        # Body context - use style tag directly
        if style_flags in (u"b", u"i", u"bi", u"s", u"bs", u"is", u"bis",
                           u"c", u"cb", u"ci", u"cbi"):
            return style_flags

        # Dynamic combination
        return self._get_or_create_style_tag(style_flags, base_tag)

    # -----------------------------------------------------------------------
    # Scroll position
    # -----------------------------------------------------------------------

    def _restore_scroll(self):
        try:
            pos = self._scroll_pos
            if pos and pos != u"1.0":
                # Check if position still exists
                try:
                    self.text.see(pos)
                    self.text.mark_set(tk.INSERT, pos)
                except Exception:
                    # Position may be past end, scroll to fraction
                    try:
                        line_parts = pos.split(u".")
                        if line_parts:
                            line_num = int(line_parts[0])
                            total = int(self.text.index(tk.END).split(u".")[0])
                            if total > 0:
                                fraction = float(line_num) / float(total)
                                self.text.yview_moveto(fraction)
                    except Exception:
                        pass
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Status bar
    # -----------------------------------------------------------------------

    def _update_status(self, render_time=None):
        if not self._statusbar_visible:
            return

        if self.current_file:
            self._status_file = _sanitize_text(
                os.path.basename(self.current_file))
            # Count lines and chars
            try:
                content = self.file_content or u""
                lines = content.count(u"\n")
                chars = len(content)
                self._status_lines = u"%d lines" % lines
                self._status_chars = u"%d chars" % chars
            except Exception:
                self._status_lines = u""
                self._status_chars = u""
        else:
            self._status_file = u"No file loaded"
            self._status_lines = u""
            self._status_chars = u""

        extra_parts = []
        if self.file_encoding:
            enc_display = self.file_encoding
            if enc_display == u"utf-8-sig":
                enc_display = u"UTF-8 BOM"
            elif enc_display == u"cp1251":
                enc_display = u"CP1251"
            elif enc_display == u"latin-1":
                enc_display = u"Latin-1"
            elif enc_display == u"mbcs":
                enc_display = u"System ANSI"
            extra_parts.append(enc_display)
        if self._status_lines:
            extra_parts.append(self._status_lines)
        if self._status_chars:
            extra_parts.append(self._status_chars)
        if render_time is not None:
            extra_parts.append(u"%dms" % render_time)

        extra = u" | ".join(extra_parts) if extra_parts else u""

        self._status_file_label.configure(text=self._status_file)
        self._status_extra_label.configure(text=extra)

    # -----------------------------------------------------------------------
    # Find dialog
    # -----------------------------------------------------------------------

    def _show_find(self):
        if self._find_dialog is not None:
            try:
                self._find_dialog.lift()
                return
            except Exception:
                self._find_dialog = None

        dialog = tk.Toplevel(self.root)
        dialog.title(u"Find")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.protocol(u"WM_DELETE_WINDOW", lambda: self._close_find(dialog))

        frame = tk.Frame(dialog, padx=10, pady=10)
        frame.pack()

        # Entry
        tk.Label(frame, text=u"Find:").grid(row=0, column=0, sticky=tk.W)
        entry = tk.Entry(frame, width=30)
        entry.grid(row=0, column=1, columnspan=2, padx=5, pady=2)
        entry.focus_set()

        # Checkbox
        match_case_var = tk.BooleanVar()
        tk.Checkbutton(frame, text=u"Match case",
                       variable=match_case_var).grid(
            row=1, column=0, columnspan=2, sticky=tk.W)

        # Buttons
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=5)

        def do_find_next():
            self._last_find_pattern = entry.get()
            self._last_find_match_case = match_case_var.get()
            self._find_in_text(self._last_find_pattern,
                               self._last_find_match_case, forward=True)

        def do_find_prev():
            self._last_find_pattern = entry.get()
            self._last_find_match_case = match_case_var.get()
            self._find_in_text(self._last_find_pattern,
                               self._last_find_match_case, forward=False)

        tk.Button(btn_frame, text=u"Find Next", width=12,
                  command=do_find_next).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text=u"Find Previous", width=12,
                  command=do_find_prev).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text=u"Close", width=8,
                  command=lambda: self._close_find(dialog)).pack(
            side=tk.LEFT, padx=2)

        entry.bind(u"<Return>", lambda e: do_find_next())
        entry.bind(u"<Escape>", lambda e: self._close_find(dialog))

        self._find_dialog = dialog
        self._find_entry = entry
        self._find_match_case = match_case_var

        # If there's selection, pre-fill
        try:
            sel = self.text.selection_get()
            if sel:
                entry.delete(0, tk.END)
                entry.insert(0, sel[:100])
        except Exception:
            pass

    def _close_find(self, dialog):
        try:
            dialog.destroy()
        except Exception:
            pass
        self._find_dialog = None
        self._find_entry = None

    def _find_next(self):
        if self._find_entry and self._find_dialog:
            try:
                pattern = self._find_entry.get()
                match_case = self._find_match_case.get()
                self._last_find_pattern = pattern
                self._last_find_match_case = match_case
                self._find_in_text(pattern, match_case, forward=True)
            except Exception:
                pass
        elif self._last_find_pattern:
            try:
                self._find_in_text(self._last_find_pattern,
                                   self._last_find_match_case,
                                   forward=True)
            except Exception:
                pass
        else:
            self._show_find()

    def _find_previous(self):
        if self._find_entry and self._find_dialog:
            try:
                pattern = self._find_entry.get()
                match_case = self._find_match_case.get()
                self._last_find_pattern = pattern
                self._last_find_match_case = match_case
                self._find_in_text(pattern, match_case, forward=False)
            except Exception:
                pass
        elif self._last_find_pattern:
            try:
                self._find_in_text(self._last_find_pattern,
                                   self._last_find_match_case,
                                   forward=False)
            except Exception:
                pass
        else:
            self._show_find()

    def _find_in_text(self, pattern, match_case, forward=True):
        if not pattern:
            return

        tw = self.text
        tw.tag_remove(u"find_match", u"1.0", tk.END)

        # Use text.search
        if forward:
            start_pos = tw.index(tk.INSERT)
            if not start_pos or start_pos == u"":
                start_pos = u"1.0"

            # Search forward
            found = tw.search(pattern, start_pos, nocase=not match_case,
                              stopindex=tk.END)
            if not found:
                # Wrap around
                found = tw.search(pattern, u"1.0", nocase=not match_case,
                                  stopindex=start_pos)
        else:
            # Search backward
            start_pos = tw.index(tk.INSERT)
            if not start_pos or start_pos == u"":
                start_pos = tk.END

            found = tw.search(pattern, start_pos, nocase=not match_case,
                              backwards=True, stopindex=u"1.0")
            if not found:
                # Wrap around: search from end back to start_pos
                found = tw.search(pattern, tk.END, nocase=not match_case,
                                  backwards=True, stopindex=start_pos)

        if found:
            end = tw.index(u"%s + %d chars" % (found, len(pattern)))
            tw.tag_add(u"find_match", found, end)
            tw.see(found)
            tw.tag_raise(u"find_match")
            if forward:
                tw.mark_set(tk.INSERT, end)
            else:
                tw.mark_set(tk.INSERT, found)
        else:
            tkMessageBox.showinfo(u"Find", u"No match found.")

    # -----------------------------------------------------------------------
    # Selection and copy
    # -----------------------------------------------------------------------

    def _copy_selection(self):
        try:
            sel = self.text.selection_get()
            if sel:
                self.root.clipboard_clear()
                self.root.clipboard_append(sel)
        except Exception:
            pass

    def _select_all(self):
        try:
            self.text.tag_add(tk.SEL, u"1.0", tk.END)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Word wrap toggle
    # -----------------------------------------------------------------------

    def _toggle_wrap(self):
        self._word_wrap = not self._word_wrap
        self._wrap_var.set(self._word_wrap)
        self._apply_wrap()
        self._save_config()

    def _apply_wrap(self):
        if not hasattr(self, u"text"):
            return
        if self._word_wrap:
            self.text.configure(wrap=tk.WORD)
            self._h_scroll_frame.grid_remove()
        else:
            self.text.configure(wrap=tk.NONE)
            self._h_scroll_frame.grid()

    # -----------------------------------------------------------------------
    # Font zoom
    # -----------------------------------------------------------------------

    def _font_zoom_in(self):
        if self._font_size < 36:
            self._font_size += 1
            self._update_fonts()
            self._save_config()

    def _font_zoom_out(self):
        if self._font_size > 6:
            self._font_size -= 1
            self._update_fonts()
            self._save_config()

    def _font_reset(self):
        self._font_size = 11
        self._update_fonts()
        self._save_config()

    # -----------------------------------------------------------------------
    # Toolbar/Statusbar toggle
    # -----------------------------------------------------------------------

    def _toggle_toolbar(self):
        self._toolbar_visible = self._toolbar_var.get()
        if self._toolbar_visible:
            self._toolbar_frame.grid()
        else:
            self._toolbar_frame.grid_remove()
        self._save_config()

    def _toggle_statusbar(self):
        self._statusbar_visible = self._statusbar_var.get()
        if self._statusbar_visible:
            self._status_frame.grid()
            self._update_status()
        else:
            self._status_frame.grid_remove()
        self._save_config()

    # -----------------------------------------------------------------------
    # Context menu
    # -----------------------------------------------------------------------

    def _on_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label=u"Copy", command=self._copy_selection)
        menu.add_command(label=u"Select All", command=self._select_all)

        # Check if over a link
        try:
            index = self.text.index(u"@%d,%d" % (event.x, event.y))
            tags = self.text.tag_names(index)
            for tag in tags:
                if tag in self._link_tags:
                    url = self._link_tags[tag]
                    menu.add_command(
                        label=u"Copy Link Address",
                        command=lambda u=url: self._copy_url(u))
                    break
        except Exception:
            pass

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_url(self, url):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Link click handling
    # -----------------------------------------------------------------------

    def _on_button_press(self, event):
        self._press_x = event.x
        self._press_y = event.y

    def _on_text_click(self, event):
        # Only open link if this was a click (not a drag)
        try:
            if abs(event.x - self._press_x) > 5 or abs(event.y - self._press_y) > 5:
                return
            index = self.text.index(u"@%d,%d" % (self._press_x, self._press_y))
            tags = self.text.tag_names(index)
            for tag in tags:
                if tag in self._link_tags:
                    self._open_url(self._link_tags[tag])
                    break
        except Exception:
            pass

    def _open_url(self, url):
        url = _validate_url(_to_unicode(url))
        if not url:
            return

        try:
            webbrowser.open(url)
        except Exception as e:
            tkMessageBox.showerror(
                u"Error",
                u"Could not open URL:\n" + _sanitize_exception(e))

    # -----------------------------------------------------------------------
    # Mouse wheel
    # -----------------------------------------------------------------------

    def _on_mousewheel(self, event):
        try:
            self.text.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Configuration persistence
    # -----------------------------------------------------------------------

    def _get_config_path(self):
        try:
            appdata = os.environ.get(u"APPDATA", u"")
            if not appdata:
                return None
            config_dir = os.path.join(appdata, CONFIG_SUBDIR)
            return os.path.join(config_dir, CONFIG_FILE)
        except Exception:
            return None

    def _load_config(self):
        if self._config_loaded:
            return
        self._config_loaded = True

        cfg_path = self._get_config_path()
        if not cfg_path or not os.path.isfile(cfg_path):
            return

        try:
            import ConfigParser as cp
            parser = cp.RawConfigParser()
            with codecs.open(cfg_path, "r", encoding="utf-8") as f:
                parser.readfp(f)

            # Window geometry
            try:
                geo = parser.get(u"window", u"geometry")
                if geo:
                    self.root.geometry(geo)
            except Exception:
                pass

            # Word wrap
            try:
                self._word_wrap = parser.getboolean(u"view", u"word_wrap")
                self._wrap_var.set(self._word_wrap)
            except Exception:
                pass

            # Toolbar
            try:
                self._toolbar_visible = parser.getboolean(u"view", u"toolbar")
                self._toolbar_var.set(self._toolbar_visible)
            except Exception:
                pass

            # Status bar
            try:
                self._statusbar_visible = parser.getboolean(u"view",
                                                            u"statusbar")
                self._statusbar_var.set(self._statusbar_visible)
            except Exception:
                pass

            # Font size
            try:
                fs = parser.getint(u"view", u"font_size")
                if 6 <= fs <= 36:
                    self._font_size = fs
            except Exception:
                pass

            # Recent files
            try:
                recent = parser.get(u"files", u"recent")
                if recent:
                    paths = recent.split(u"\n")
                    self._recent_files = [p for p in paths if p]
                    if len(self._recent_files) > 5:
                        self._recent_files = self._recent_files[:5]
            except Exception:
                pass

        except Exception:
            pass

        # Apply settings
        self._update_recent_menu()
        self._setup_fonts()

    def _save_config(self):
        cfg_path = self._get_config_path()
        if not cfg_path:
            return

        try:
            import ConfigParser as cp
            config_dir = os.path.dirname(cfg_path)
            if not os.path.isdir(config_dir):
                try:
                    os.makedirs(config_dir)
                except Exception:
                    return

            parser = cp.RawConfigParser()

            parser.add_section(u"window")
            try:
                parser.set(u"window", u"geometry",
                           self.root.geometry())
            except Exception:
                pass

            parser.add_section(u"view")
            parser.set(u"view", u"word_wrap", str(self._word_wrap))
            parser.set(u"view", u"toolbar", str(self._toolbar_visible))
            parser.set(u"view", u"statusbar", str(self._statusbar_visible))
            parser.set(u"view", u"font_size", str(self._font_size))

            parser.add_section(u"files")
            parser.set(u"files", u"recent",
                       u"\n".join(self._recent_files))

            with codecs.open(cfg_path, "w", encoding="utf-8") as f:
                parser.write(f)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # About
    # -----------------------------------------------------------------------

    def _show_about(self):
        tkMessageBox.showinfo(
            u"About mdxp",
            u"mdxp v1.1\n"
            u"Markdown eXPerience Viewer\n\n"
            u"Python 2.7 / Tkinter\n"
            u"Windows XP target\n"
            u"Standard library only\n\n"
            u"Markdown features:\n"
            u"- ATX headings (# to ######)\n"
            u"- Setext headings (===, ---)\n"
            u"- Bold, italic, bold-italic\n"
            u"- Strikethrough\n"
            u"- Inline code, fenced/indented code blocks\n"
            u"- Ordered and unordered lists (nested)\n"
            u"- Task lists\n"
            u"- Blockquotes (nested)\n"
            u"- Links, autolinks, images (placeholder)\n"
            u"- Horizontal rules\n"
            u"- Escaped characters, hard line breaks\n\n"
            u"UI features:\n"
            u"- Find dialog, font zoom, word wrap\n"
            u"- Status bar, toolbar, context menu\n"
            u"- Recent files, config persistence\n"
            u"- Copy, Select All"
        )

    # -----------------------------------------------------------------------
    # Exit
    # -----------------------------------------------------------------------

    def _on_exit(self):
        try:
            self._save_config()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        # Apply initial toolbar/statusbar state
        if not self._toolbar_visible:
            self._toolbar_frame.grid_remove()
        if not self._statusbar_visible:
            self._status_frame.grid_remove()

        self._update_ui_state()
        self._update_status()

        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    path = None
    if len(sys.argv) > 1:
        args = [_to_unicode(a) for a in sys.argv[1:]]
        path = u" ".join(args).strip()
        if not path:
            path = None

    app = MdxpViewer(path)
    app.run()


if __name__ == "__main__":
    main()
