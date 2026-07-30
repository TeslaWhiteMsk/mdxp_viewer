# mdxp v1.1 - Markdown eXPerience Viewer

A graphical Markdown file viewer for Windows XP using Python 2.7 and Tkinter.  
Standard library only. No external dependencies.

## Requirements

- Windows XP, 32-bit
- Python 2.7 (standard library only)
- Tkinter (included with Python 2.7)

## How to Run

Or double-click `mdxp.bat` (then use **File > Open…**).

## Keyboard Shortcuts

- `Ctrl+O` – Open file
- `F5` – Reload current file
- `Ctrl+C` – Copy selection
- `Ctrl+A` – Select All
- `Ctrl+F` – Find dialog
- `F3` – Find next
- `Shift+F3` – Find previous
- `Ctrl++` – Increase font size
- `Ctrl+-` – Decrease font size
- `Ctrl+0` – Reset font size
- `Ctrl+W` – Toggle word wrap
- `Alt+F4` – Exit

## UI Features

- **Toolbar** – Open, Reload, Find, Word Wrap buttons (toggle via View menu)
- **Status bar** – File name, encoding, line count, character count, render time
- **Find dialog** – Non-modal search with match case, wrap-around
- **Font zoom** – Increase, decrease, or reset font size
- **Word wrap** – Toggle on/off; horizontal scrollbar when off
- **Context menu** – Right-click: Copy, Select All, Copy Link Address
- **Recent files** – Last 5 files (persisted between sessions)
- **Reopen encoding** – File > Reopen with Encoding (UTF-8, CP1251, Latin-1, System ANSI)
- **Copy / Select All** via Edit menu or keyboard shortcuts
- **Configuration** – Window geometry and settings saved to `%APPDATA%\mdxp\mdxp.ini`

## Markdown Support

### Block-level features

- **ATX headings** – `#` to `######` (requiring space after `#`)
- **Setext headings** – `===` and `---` underlines
- **Paragraphs** – Consecutive lines joined, blank lines separate
- **Hard line breaks** – Trailing two spaces or backslash
- **Fenced code blocks** – ` ``` ` or `~~~` (language string ignored)
- **Indented code** – 4 spaces or 1 tab
- **Horizontal rules** – `---`, `***`, `___` (3+ characters)
- **Blockquotes** – `>` (nested up to 10 levels)
- **Unordered lists** – `-`, `*`, `+` (nested by indentation)
- **Ordered lists** – `1. 2. 3.` (nested, independent numbering)
- **Task lists** – `[ ]`, `[x]`, `[X]` (non-interactive)

### Inline features

- **Bold** – `**text**` or `__text__` (word-bounded)
- **Italic** – `*text*` or `_text_` (word-bounded)
- **Bold-italic** – `***text***`
- **Strikethrough** – `~~text~~`
- **Inline code** – `` `code` `` or ``` ``code with ` backtick`` ```
- **Links** – `[text](url)` or `[text](<url>)`
- **Autolinks** – `<https://...>`, `<user@example.com>`
- **Images** – `![alt](url)` rendered as `[image: alt]`
- **Escapes** – `\*`, `` \` ``, `\_`, etc.
- **Hard line break** – Two trailing spaces or backslash at line end

### URL handling

- Supported schemes: `http`, `https`, `mailto`, `ftp`
- Blocked schemes: `javascript`, `vbscript`, `file`, `data`
- Email autolinks automatically prefixed with `mailto:`
- Bare URLs like `www.example.com` or domain-like text are detected

## Limitations

- No image display (renders as placeholder text).
- No syntax highlighting.
- No full CommonMark compliance.
- No HTML tag rendering (rendered as plain text).
- No reference-style links.
- No footnotes, definition lists, or tables.
- No drag-and-drop support.
- No editing or saving of Markdown files.
- No plugin system.

## File Encoding

Auto-detects: UTF-8 with BOM, UTF-8, CP1251, Latin-1 (fallback).  
Manual: **File > Reopen with Encoding**.

## Files

- `mdxp.py` – Main application
- `mdxp.bat` – Windows launcher

## Version History

- **v1.1** – Improved Markdown parser (block/inline layers), nested lists and blockquotes, bold-italic combinations, strikethrough, autolinks, images placeholder, escaped characters, hard line breaks, find dialog, font zoom, word wrap toggle, status bar, toolbar, context menu, recent files, config persistence, encoding display and manual reopen.
- **v1.0** – Initial release.
