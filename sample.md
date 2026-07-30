# Heading 1

## Heading 2

### Heading 3

#### Heading 4

##### Heading 5

###### Heading 6

## Inline Formatting

Plain paragraph with **bold**, *italic*, ***bold italic***, ~~strikethrough~~,
`inline code`, and a [link](https://example.com).

Combined: **bold and *italic* together**, *italic with **bold** inside*.

Underscore emphasis: _italic_ and __bold__ but foo_bar_baz should stay plain.

Escaped characters: \*literal asterisks\* and \`literal backticks\`.

## Hard Line Breaks

First line with two spaces  
second line
third line with backslash\
fourth line

## Lists

### Unordered

- bullet one
- bullet two
  - nested bullet
  - nested bullet
- bullet three

### Ordered

1. first item
2. second item
   1. nested ordered
   2. nested ordered
3. third item

### Task Lists

- [ ] unchecked task
- [x] checked task
- [X] checked task too

## Blockquotes

> single level blockquote
>
> > nested blockquote
> > with multiple lines
>
> back to first level

> blockquote with **bold** and `code`

## Code

### Fenced code block

```
def hello():
    print("hello world")
```

With language tag:

```python
def hello():
    print("hello world")
```

### Indented code block

    This is an indented code block.
        With extra indentation preserved.

## Horizontal Rules

---

***

- - -

## Links and Autolinks

<https://example.com>

<user@example.com>

[link with title](https://example.com "Title")

## Images

![alt text](image.png)

## Setext Headings

Setext Heading 1
================

Setext Heading 2
----------------

## Malformed Markdown (should not crash)

#no space heading?

**unclosed bold

*unclosed italic

[broken link](

[broken link](unclosed

`unclosed code span

- 
-
* 
+
