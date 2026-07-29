# -*- coding: utf-8 -*-
"""
mdxp - Markdown eXPerience Viewer
Simple graphical Markdown file viewer for Windows XP (Python 2.7 / Tkinter).
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


_CONTROL_RE = re.compile(
    u"[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]",
    re.UNICODE
)


def _sanitize_text(value):
    return _CONTROL_RE.sub(u"", _to_unicode(value))


INLINE_RE = re.compile(
    u"\\*\\*(.+?)\\*\\*|"
    u"(?<!\\w)__(.+?)__(?!\\w)|"
    u"\\*(.+?)\\*|"
    u"(?<!\\w)_(.+?)_(?!\\w)|"
    u"`(.+?)`|"
    u"\\[(.+?)\\]\\((.+?)\\)",
    re.UNICODE
)


class MdxpViewer(object):
    def __init__(self, initial_file=None):
        self.root = tk.Tk()
        self.root.title("mdxp")
        self.root.geometry("800x600")

        self.current_file = None
        self.file_content = None
        self._link_tags = {}
        self._link_counter = 0

        self._setup_fonts()
        self._create_menu()
        self._create_widgets()
        self._bind_keys()

        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)
        self.root.minsize(400, 200)

        if initial_file:
            self.open_file(initial_file)

    def _setup_fonts(self):
        family = "MS Sans Serif"
        size = 8

        try:
            try:
                default_font = tkFont.nametofont("TkDefaultFont")
            except AttributeError:
                default_font = tkFont.Font(name="TkDefaultFont", exists=True)

            actual_family = default_font.actual("family")
            actual_size = default_font.actual("size")

            if actual_family:
                family = _to_unicode(actual_family)

            if actual_size:
                size = int(actual_size)
        except Exception:
            pass

        if not family:
            family = "MS Sans Serif"

        if not size:
            size = 8

        self.font_body = (family, size)
        self.font_h1 = (family, 18, "bold")
        self.font_h2 = (family, 14, "bold")
        self.font_h3 = (family, 12, "bold")
        self.font_bold = (family, size, "bold")
        self.font_italic = (family, size, "italic")
        self.font_code = ("Courier New", size)

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open...", command=self._prompt_open, accelerator="Ctrl+O")
        file_menu.add_command(label="Reload", command=self._reload_file, accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit, accelerator="Alt+F4")

        help_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _create_widgets(self):
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            frame, wrap=tk.WORD, state=tk.DISABLED,
            padx=10, pady=10, font=self.font_body,
            relief=tk.SUNKEN, bd=2,
        )

        v_scroll = tk.Scrollbar(frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=v_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.text.focus_set()
        self.text.bind("<Button-1>", self._on_text_click)

        if sys.platform == "win32":
            self.text.bind("<MouseWheel>", self._on_mousewheel)
            frame.bind("<MouseWheel>", self._on_mousewheel)

        self._define_tags()

    def _define_tags(self):
        t = self.text
        t.tag_configure("h1", font=self.font_h1, spacing1=12, spacing3=6)
        t.tag_configure("h2", font=self.font_h2, spacing1=10, spacing3=4)
        t.tag_configure("h3", font=self.font_h3, spacing1=8, spacing3=3)
        t.tag_configure("bold", font=self.font_bold)
        t.tag_configure("italic", font=self.font_italic)
        t.tag_configure("code", font=self.font_code,
                        background="#f0f0f0", foreground="#333")
        t.tag_configure("codeblock", font=self.font_code,
                        background="#f5f5f5", foreground="#333",
                        spacing1=1, spacing3=1,
                        lmargin1=24, lmargin2=24)
        t.tag_configure("hr", foreground="#aaa")

    def _bind_keys(self):
        self.root.bind("<Control-o>", lambda e: self._prompt_open())
        self.root.bind("<Control-O>", lambda e: self._prompt_open())
        self.root.bind("<F5>", lambda e: self._reload_file())

        self.text.bind("<Up>", lambda e: self._scroll_text(-1, "units"))
        self.text.bind("<Down>", lambda e: self._scroll_text(1, "units"))
        self.text.bind("<Prior>", lambda e: self._scroll_text(-1, "pages"))
        self.text.bind("<Next>", lambda e: self._scroll_text(1, "pages"))
        self.text.bind("<Home>", lambda e: self._scroll_text("0.0", "moveto"))
        self.text.bind("<End>", lambda e: self._scroll_text("1.0", "moveto"))

    def _prompt_open(self):
        path = tkFileDialog.askopenfilename(
            parent=self.root,
            title=u"Open Markdown File",
            filetypes=[
                (u"Markdown files", "*.md *.markdown *.mdown *.mdwn *.mkd"),
                (u"All files", "*.*")
            ]
        )
        if path:
            path = _to_unicode(path)
            self.open_file(path)

    def open_file(self, path):
        path = _sanitize_text(path)

        if not path or not os.path.isfile(path):
            tkMessageBox.showerror(u"Error", u"File not found:\n" + path)
            return

        self.current_file = path
        content = self._read_file(path)

        if content is None:
            return

        self.file_content = content
        self.root.title(u"mdxp - " + _sanitize_text(os.path.basename(path)))
        self._render_markdown(content)

    def _read_file(self, path):
        for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
            try:
                with codecs.open(path, "r", encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                tkMessageBox.showerror(
                    u"Error",
                    u"Could not read file:\n" + _sanitize_text(e)
                )
                return None

        tkMessageBox.showerror(
            u"Error",
            u"Could not decode file. Tried: UTF-8, CP1251, Latin-1."
        )
        return None

    def _reload_file(self):
        if self.current_file:
            self.open_file(self.current_file)

    def _render_markdown(self, text):
        tw = self.text
        tw.config(state=tk.NORMAL)

        try:
            tw.delete("1.0", tk.END)

            for tag_name in self._link_tags.keys():
                tw.tag_delete(tag_name)

            self._link_tags.clear()
            self._link_counter = 0

            text = _sanitize_text(text)
            lines = text.splitlines()
            in_code = False
            code_lines = []
            i = 0

            while i < len(lines):
                line = lines[i]
                stripped = line.strip()

                if stripped.startswith("```"):
                    if not in_code:
                        in_code = True
                        code_lines = []
                    else:
                        in_code = False
                        self._emit_code_block(tw, code_lines)
                        code_lines = []
                    i += 1
                    continue

                if in_code:
                    code_lines.append(line)
                    i += 1
                    continue

                if not stripped:
                    tw.insert(tk.END, u"\n")
                    i += 1
                    continue

                if re.match(r"^[-*_]{3,}$", stripped):
                    tw.insert(tk.END, " " * 30 + u"\u2500" * 20 + u"\n", "hr")
                    i += 1
                    continue

                hm = re.match(r"^(#{1,3})\s+(.+)$", line)
                if hm:
                    level = len(hm.group(1))
                    self._emit_inline(tw, hm.group(2) + u"\n", "h%d" % level)
                    i += 1
                    continue

                hm = re.match(r"^#{4,6}\s+(.+)$", line)
                if hm:
                    self._emit_inline(tw, hm.group(1) + u"\n", "bold")
                    i += 1
                    continue

                lm = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
                if lm:
                    indent = lm.group(1)
                    content = lm.group(2)
                    prefix = "  " * (1 + len(indent) // 2) + u"\u2022 "
                    tw.insert(tk.END, prefix)
                    self._emit_inline(tw, content + u"\n")
                    i += 1
                    continue

                nm = re.match(r"^(\s*)(\d+)\.\s+(.+)$", line)
                if nm:
                    indent = nm.group(1)
                    num = nm.group(2)
                    content = nm.group(3)
                    prefix = "  " * (1 + len(indent) // 2) + num + ". "
                    tw.insert(tk.END, prefix)
                    self._emit_inline(tw, content + u"\n")
                    i += 1
                    continue

                bm = re.match(r"^>\s?(.*)$", line)
                if bm:
                    self._emit_inline(tw, bm.group(1) + u"\n", "italic")
                    i += 1
                    continue

                self._emit_inline(tw, line + u"\n")
                i += 1

            if in_code and code_lines:
                self._emit_code_block(tw, code_lines)

        finally:
            tw.config(state=tk.DISABLED)

    def _emit_code_block(self, tw, lines):
        if not lines:
            return

        tw.insert(tk.END, u"\n")

        for l in lines:
            tw.insert(tk.END, l + u"\n", "codeblock")

        tw.insert(tk.END, u"\n")

    def _emit_inline(self, tw, text, default_tag=None):
        if not text:
            return

        text = _to_unicode(text)

        parts = []
        pos = 0

        for m in INLINE_RE.finditer(text):
            s, e = m.start(), m.end()

            if s > pos:
                parts.append((text[pos:s], None))

            if m.group(1) is not None:
                parts.append((m.group(1), "bold"))
            elif m.group(2) is not None:
                parts.append((m.group(2), "bold"))
            elif m.group(3) is not None:
                parts.append((m.group(3), "italic"))
            elif m.group(4) is not None:
                parts.append((m.group(4), "italic"))
            elif m.group(5) is not None:
                parts.append((m.group(5), "code"))
            elif m.group(6) is not None and m.group(7) is not None:
                parts.append((m.group(6), ("link", m.group(7))))

            pos = e

        if pos < len(text):
            parts.append((text[pos:], None))

        for content, fmt in parts:
            if fmt is None:
                if default_tag:
                    tw.insert(tk.END, content, default_tag)
                else:
                    tw.insert(tk.END, content)
            elif isinstance(fmt, tuple) and fmt[0] == "link":
                url = fmt[1]
                self._link_counter += 1
                tag_name = "lnk_%d" % self._link_counter
                self._link_tags[tag_name] = url
                tw.tag_configure(tag_name, foreground="#0000cc", underline=True)
                if default_tag:
                    tw.insert(tk.END, content, (default_tag, tag_name))
                else:
                    tw.insert(tk.END, content, tag_name)
            else:
                if default_tag:
                    tw.insert(tk.END, content, (default_tag, fmt))
                else:
                    tw.insert(tk.END, content, fmt)

    def _on_mousewheel(self, event):
        self.text.yview_scroll(-1 * (event.delta / 120), "units")

    def _scroll_text(self, amount, what):
        if what == "moveto":
            self.text.yview_moveto(amount)
        else:
            self.text.yview_scroll(amount, what)

    def _on_text_click(self, event):
        try:
            index = self.text.index("@%d,%d" % (event.x, event.y))
            tags = self.text.tag_names(index)

            for tag in tags:
                if tag in self._link_tags:
                    self._open_url(self._link_tags[tag])
                    break
        except Exception:
            pass

    def _open_url(self, url):
        url = _to_unicode(url).strip()

        if not url:
            return

        try:
            webbrowser.open(url)
        except Exception as e:
            tkMessageBox.showerror(
                u"Error",
                u"Could not open URL:\n" + _sanitize_text(e)
            )

    def _show_about(self):
        tkMessageBox.showinfo(
            u"About mdxp",
            u"mdxp v1.0\n"
            u"Markdown eXPerience Viewer\n\n"
            u"Python 2.7 / Tkinter\n"
            u"Windows XP\n\n"
            u"Supported: headings, bold, italic,\n"
            u"code, code blocks, lists, links,\n"
            u"blockquotes, horizontal rules."
        )

    def _on_exit(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


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
