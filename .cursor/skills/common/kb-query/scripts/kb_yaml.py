#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal, dependency-free YAML subset parser for OKF frontmatter and .kb/manifest.yaml.

Supported: block mappings, block lists (incl. "- key: value" items with nested maps),
flow mappings / lists ({a: 1} / [a, b]), plain / single- / double-quoted scalars,
block scalars (| |- > >-), comments. Not supported: anchors, tags, multi-document streams.
Anything unparseable raises YamlError so the caller can report the file instead of guessing.
"""
from __future__ import annotations

import re

BLOCK_SCALAR = re.compile(r"^[|>][+-]?$")


class YamlError(ValueError):
    pass


def _strip_comment(line: str) -> str:
    out, q = [], None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'" and (i == 0 or line[i - 1] in " \t:[{,"):
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _split_flow(s: str) -> list[str]:
    parts, depth, q, cur = [], 0, None, []
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def scalar(s: str):
    s = s.strip()
    if s == "":
        return None
    if s.startswith("{") and s.endswith("}"):
        d = {}
        for p in _split_flow(s[1:-1]):
            k, _, v = p.partition(":")
            d[k.strip().strip("\"'")] = scalar(v)
        return d
    if s.startswith("[") and s.endswith("]"):
        return [scalar(p) for p in _split_flow(s[1:-1])]
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if s in ("null", "Null", "NULL", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _key_value(text: str):
    # Like real YAML, only ":" followed by whitespace / end-of-line separates key and value, so
    # values such as team:payment-core or kb://... survive.
    m = re.match(r"^([^\[\]{}\s\"'#-][^\[\]{}]*?|\"[^\"]*\"|'[^']*'):(?:\s+(.*))?$", text)
    if not m:
        return None
    return m.group(1).strip().strip("\"'"), (m.group(2) or "")


class _Parser:
    def __init__(self, text: str) -> None:
        self.raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.items: list[tuple[int, int, str]] = []  # (raw line no, indent, content)
        for n, r in enumerate(self.raw):
            if "\t" in r[: len(r) - len(r.lstrip())]:
                raise YamlError("line %d: tab indentation is not allowed" % (n + 1))
            c = _strip_comment(r)
            if c.strip():
                self.items.append((n, len(c) - len(c.lstrip(" ")), c.strip()))

    def parse(self):
        if not self.items:
            return {}
        val, i = self._block(0, self.items[0][1])
        if i < len(self.items):
            raise YamlError("line %d: unexpected content: %s" % (self.items[i][0] + 1, self.items[i][2]))
        return val

    def _block(self, i: int, indent: int):
        if self.items[i][2].startswith("- ") or self.items[i][2] == "-":
            return self._list(i, indent)
        return self._map(i, indent)

    def _block_scalar(self, i: int, ind: int, style: str):
        """i = index of the item holding the key; collect raw lines until a line indented <= ind."""
        start = self.items[i][0] + 1
        j = i + 1
        while j < len(self.items) and self.items[j][1] > ind:
            j += 1
        end = self.items[j][0] if j < len(self.items) else len(self.raw)
        lines = self.raw[start:end]
        while lines and not lines[-1].strip():
            lines.pop()
        body = [ln for ln in lines if ln.strip()]
        cut = min((len(ln) - len(ln.lstrip(" ")) for ln in body), default=0)
        lines = [ln[cut:] if ln.strip() else "" for ln in lines]
        if style.startswith("|"):
            text = "\n".join(lines)
        else:
            paras, cur = [], []
            for ln in lines:
                if ln.strip():
                    cur.append(ln.strip())
                else:
                    paras.append(" ".join(cur))
                    cur = []
            paras.append(" ".join(cur))
            text = "\n".join(paras)
        if not style.endswith("-"):
            text += "\n"
        return text, j

    def _map(self, i: int, indent: int):
        d = {}
        while i < len(self.items):
            _, ind, text = self.items[i]
            if ind < indent or text.startswith("- "):
                break
            if ind > indent:
                raise YamlError("line %d: bad indentation" % (self.items[i][0] + 1))
            kv = _key_value(text)
            if kv is None:
                raise YamlError("line %d: expected 'key: value', got: %s" % (self.items[i][0] + 1, text))
            k, v = kv
            if BLOCK_SCALAR.match(v):
                d[k], i = self._block_scalar(i, ind, v)
                continue
            i += 1
            if v == "":
                if i < len(self.items) and (self.items[i][1] > ind or
                                            (self.items[i][1] == ind and self.items[i][2].startswith("- "))):
                    d[k], i = self._block(i, self.items[i][1])
                else:
                    d[k] = None
            else:
                d[k] = scalar(v)
        return d, i

    def _list(self, i: int, indent: int):
        out = []
        while i < len(self.items):
            _, ind, text = self.items[i]
            if ind != indent or not (text.startswith("- ") or text == "-"):
                break
            rest = text[2:].strip() if text != "-" else ""
            kv = _key_value(rest) if rest and not rest.startswith(("{", "[")) else None
            if kv is not None:
                k, v = kv
                child = indent + 2
                item = {}
                i += 1
                if v == "" and i < len(self.items) and self.items[i][1] > child:
                    item[k], i = self._block(i, self.items[i][1])
                else:
                    item[k] = scalar(v)
                if i < len(self.items) and self.items[i][1] == child and not self.items[i][2].startswith("- "):
                    more, i = self._map(i, child)
                    item.update(more)
                out.append(item)
            elif rest == "":
                i += 1
                if i < len(self.items) and self.items[i][1] > indent:
                    val, i = self._block(i, self.items[i][1])
                else:
                    val = None
                out.append(val)
            else:
                out.append(scalar(rest))
                i += 1
        return out, i


def loads(text: str):
    return _Parser(text).parse()
