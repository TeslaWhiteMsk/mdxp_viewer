mdxp - Markdown eXPerience Viewer
====================================

A simple graphical Markdown file viewer for Windows XP
using Python 2.7 and Tkinter. No external dependencies.

HOW TO RUN
----------
  python mdxp.py [file.md]

Or double-click mdxp.bat (then use File > Open...).

USAGE
-----
  File > Open... (Ctrl+O)  Open a .md file
  File > Reload (F5)       Reload current file
  File > Exit   (Alt+F4)   Close the viewer
  Help > About             Show version info

MARKDOWN SUPPORT
----------------
  Headings     # ## ### (larger/bold fonts)
  Bold         **text** or __text__
  Italic       *text* or _text_
  Inline code  `code` (monospace + background)
  Code blocks  Fenced with ``` (monospace block, background)
  Lists        Bulleted (-, *) and numbered (1., 2., ...)
  Links        [text](url) -- click to open in browser
  Blockquotes  > text
  Horizontal   ---, ***, ___ (renders as line)

Unsupported Markdown is displayed as plain text (no crashes).

FILE ENCODING
-------------
Auto-detects: UTF-8 (with or without BOM), CP1251, Latin-1 (fallback).

LIMITATIONS
-----------
  No image display, tables, task lists, or syntax highlighting.
  Simple line-by-line renderer (no paragraph reflow).
  No drag-and-drop support.
  No horizontal scrollbar (word wrap is on by default).

REQUIREMENTS
------------
  Windows XP, 32-bit
  Python 2.7 (standard library only)
  Tkinter (included with Python 2.7)
