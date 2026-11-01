"""The things drawn on a page (lines, shapes, text, pictures) read straight from its content stream,
so they can be moved or removed.

A page's content stream is a list of drawing instructions. Each "object" here is one painted
thing: a path with its paint instruction, a run of text, or a picture. Moving one wraps it in a
shift ("q 1 0 0 1 dx dy cm ... Q"), or for text inside a text block, re-positions it with "Tm";
removing one cuts it out. Nothing else in the stream is touched, so colours, line widths and
everything that isn't moved stay exactly as they were.
"""
import re

import pymupdf

_TOKEN = re.compile(rb"""
    (?P<ws>[\x00\t\n\x0c\r ]+|%[^\r\n]*)
  | (?P<str>\()
  | (?P<dopen><<) | (?P<dclose>>>)
  | (?P<hex><[0-9A-Fa-f\x00\t\n\x0c\r ]*>)
  | (?P<aopen>\[) | (?P<aclose>\])
  | (?P<name>/[^\x00\t\n\x0c\r /\[\]()<>{}%]*)
  | (?P<num>[+-]?(?:\d+\.?\d*|\.\d+))
  | (?P<op>[^\x00\t\n\x0c\r /\[\]()<>{}%]+)
  | (?P<other>.)
""", re.X | re.S)

_EI = re.compile(rb"[\x00\t\n\x0c\r ]EI(?=[\x00\t\n\x0c\r /\[<(%]|$)")

PATH_BUILD = {b"m", b"l", b"c", b"v", b"y", b"h", b"re"}
PATH_PAINT = {b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"n"}
SHOWS = {b"Tj", b"TJ", b"'", b'"'}
TEXT_MOVES = {b"Td", b"TD", b"Tm", b"T*", b"'", b'"', b"ET", b"BT"}  # end a text run


def _string_end(data, i):
    """data[i] is '(': index just past the matching ')'."""
    depth, n = 0, len(data)
    while i < n:
        ch = data[i]
        if ch == 0x5C:  # backslash: skip the escaped character
            i += 2
            continue
        if ch == 0x28:
            depth += 1
        elif ch == 0x29:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _string_len(raw):
    """Rough character count of a literal or hex string token (for estimating text width)."""
    if raw.startswith(b"<"):
        return max(1, len(re.sub(rb"\s", b"", raw[1:-1])) // 2)
    return max(1, len(re.sub(rb"\\(\d{1,3}|.)", b"x", raw[1:-1], flags=re.S)))


def operations(data):
    """Yield (operator, operands, start, end) for each instruction; operands are raw tokens
    (numbers as floats, others as bytes) and start..end spans the operands and the operator."""
    pos, n = 0, len(data)
    operands, start, depth = [], None, 0
    while pos < n:
        m = _TOKEN.match(data, pos)
        kind = m.lastgroup
        if kind == "ws":
            pos = m.end()
            continue
        if start is None:
            start = m.start()
        if kind == "str":
            end = _string_end(data, pos)
            if depth == 0:
                operands.append(data[pos:end])
            pos = end
            continue
        pos = m.end()
        if kind in ("dopen", "aopen"):
            depth += 1
            if kind == "aopen" and depth == 1:
                operands.append([])  # TJ arrays: collect their strings and numbers
            continue
        if kind in ("dclose", "aclose"):
            depth = max(0, depth - 1)
            continue
        value = m.group()
        if depth:
            if operands and isinstance(operands[-1], list) and depth == 1:
                operands[-1].append(float(value) if kind == "num" else value)
            continue
        if kind == "num":
            operands.append(float(value))
        elif kind in ("name", "hex", "other"):
            operands.append(value)
        elif value in (b"true", b"false", b"null"):
            operands.append(value)
        else:
            if value == b"ID":  # inline picture: its data runs up to "EI"
                e = _EI.search(data, pos)
                pos = e.end() if e else n
                value = b"EI"
            yield value, operands, start, pos
            operands, start = [], None


class Obj:
    """One painted thing on the page."""
    __slots__ = ("kind", "start", "end", "bbox", "ctm", "shows", "tm", "tlm_end", "index", "hidden", "geom", "filled", "origins")

    def __init__(self, kind, start, end, bbox, ctm):
        self.kind, self.start, self.end, self.bbox, self.ctm = kind, start, end, bbox, ctm
        self.shows = None  # text: [(start, end, operator, operands)]
        self.tm = None  # text: the matrix to shift (Tm, or the line matrix for ' and ")
        self.tlm_end = None  # text: line matrix to put back after the run
        self.hidden = False  # invisible text (the searchable layer of scans and drawings)
        self.geom = None  # path: list of point lists (one per piece), in user space
        self.filled = False
        self.origins = None  # text: where each piece of text starts, in user space


def _num(v, default=0.0):
    return v if isinstance(v, float) else default


def _bounds(points):
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))


def parse(data, xobjects=None):
    """The objects in a content stream, in order. bbox is in PDF user space (y up).
    xobjects: name -> (is_form, bbox Rect, matrix) for pictures and forms the page uses."""
    xobjects = xobjects or {}
    objs = []
    ctm, stack = pymupdf.Matrix(1, 0, 0, 1, 0, 0), []
    path, path_start, clip, pieces = [], None, False, []
    in_text = False
    tm = tlm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    fs, tl, tz, rise, mode = 0.0, 0.0, 1.0, 0.0, 0
    run = None  # the text object being collected

    def end_run():
        nonlocal run
        if run is not None:
            run.tlm_end = pymupdf.Matrix(tlm)
            objs.append(run)
            run = None

    def text_box(n):
        """Corners of n characters at the current text position, in user space; advances tm."""
        nonlocal tm
        w = n * 0.5 * fs * tz
        m = tm * ctm
        pts = [pymupdf.Point(x, y + rise) * m for x, y in ((0, -0.22 * fs), (w, -0.22 * fs), (0, 0.8 * fs),
                                                           (w, 0.8 * fs))]
        tm = pymupdf.Matrix(1, 0, 0, 1, w, 0) * tm
        return pts

    for op, args, start, end in operations(data):
        if op in PATH_BUILD:
            if path_start is None:
                path_start = start
            nums = [_num(a) for a in args]
            if op == b"re" and len(nums) >= 4:
                x, y, w, h = nums[:4]
                corners = [pymupdf.Point(px, py) * ctm for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))]
                path += corners
                pieces.append(corners + [corners[0]])
            elif op == b"h":
                if pieces and pieces[-1]:
                    pieces[-1].append(pieces[-1][0])
            elif len(nums) >= 2:
                pts = [pymupdf.Point(nums[i], nums[i + 1]) * ctm for i in range(0, len(nums) - 1, 2)]
                path += pts
                if op == b"m" or not pieces:
                    pieces.append([])
                pieces[-1] += pts
            continue
        if op in (b"W", b"W*"):
            clip = True
            continue
        if op in PATH_PAINT:
            if path_start is not None and path and not clip and op != b"n":
                o = Obj("path", path_start, end, _bounds(path), pymupdf.Matrix(ctm))
                o.geom = pieces
                o.filled = op not in (b"S", b"s")
                objs.append(o)
            path, path_start, clip, pieces = [], None, False, []
            continue
        if op == b"q":
            stack.append((pymupdf.Matrix(ctm), fs, tl, tz, rise, mode, start, len(objs)))
        elif op == b"Q":
            if stack:
                ctm, fs, tl, tz, rise, mode, q_start, n0 = stack.pop()
                # A q ... Q block holding just one thing (often with its own clip) moves as a whole,
                # so its clip goes with it.
                if len(objs) == n0 + 1 and objs[n0].kind != "text" and not in_text:
                    o = objs[n0]
                    o.start, o.end, o.ctm = q_start, end, pymupdf.Matrix(ctm)
        elif op == b"cm" and len(args) >= 6:
            ctm = pymupdf.Matrix(*[_num(a) for a in args[:6]]) * ctm
        elif op == b"BT":
            in_text = True
            tm = tlm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
        elif op == b"ET":
            end_run()
            in_text = False
        elif op == b"Tf" and args:
            fs = _num(args[-1], fs)
        elif op == b"TL" and args:
            tl = _num(args[0])
        elif op == b"Tz" and args:
            tz = _num(args[0], 100) / 100
        elif op == b"Ts" and args:
            rise = _num(args[0])
        elif op == b"Tr" and args:
            mode = int(_num(args[0]))
        elif op in (b"Do", b"EI"):
            info = xobjects.get(args[0] if args else None) if op == b"Do" else None
            if info and info[0]:
                corners = [p * info[2] * ctm for p in (info[1].tl, info[1].tr, info[1].bl, info[1].br)]
            else:
                corners = [pymupdf.Point(x, y) * ctm for x, y in ((0, 0), (1, 0), (0, 1), (1, 1))]
            if not in_text:
                objs.append(Obj("xobj", start, end, _bounds(corners), pymupdf.Matrix(ctm)))
            continue

        if not in_text:
            continue
        if op in TEXT_MOVES:
            end_run()
        if op == b"Td" and len(args) >= 2:
            tlm = pymupdf.Matrix(1, 0, 0, 1, _num(args[0]), _num(args[1])) * tlm
            tm = pymupdf.Matrix(tlm)
        elif op == b"TD" and len(args) >= 2:
            tl = -_num(args[1])
            tlm = pymupdf.Matrix(1, 0, 0, 1, _num(args[0]), _num(args[1])) * tlm
            tm = pymupdf.Matrix(tlm)
        elif op == b"Tm" and len(args) >= 6:
            tlm = pymupdf.Matrix(*[_num(a) for a in args[:6]])
            tm = pymupdf.Matrix(tlm)
        elif op == b"T*":
            tlm = pymupdf.Matrix(1, 0, 0, 1, 0, -tl) * tlm
            tm = pymupdf.Matrix(tlm)
        if op in SHOWS:
            if run is None:
                run = Obj("text", start, end, None, pymupdf.Matrix(ctm))
                run.shows = []
                run.hidden = mode in (3, 7)
                run.origins = []
                # ' and " move to the next line first, so for those it's the line matrix that shifts.
                run.tm = pymupdf.Matrix(tlm if op in (b"'", b'"') else tm)
            if op in (b"'", b'"'):
                tlm = pymupdf.Matrix(1, 0, 0, 1, 0, -tl) * tlm
                tm = pymupdf.Matrix(tlm)
            s = args[-1] if args else b""
            if op == b"TJ" and isinstance(s, list):
                n = sum(_string_len(x) for x in s if isinstance(x, bytes))
                n += sum(-x / 1000 / 0.5 for x in s if isinstance(x, float))
            else:
                n = _string_len(s) if isinstance(s, bytes) else 1
            run.origins.append(pymupdf.Point(0, rise) * tm * ctm)
            pts = text_box(max(0.5, n))
            b = _bounds(pts)
            run.bbox = b if run.bbox is None else run.bbox | b
            run.end = end
            run.shows.append((start, end, op, args))
    end_run()
    objs.sort(key=lambda o: o.start)
    for i, o in enumerate(objs):
        o.index = i
    return objs


def _seg_dist(p, a, b):
    dx, dy = b.x - a.x, b.y - a.y
    length = dx * dx + dy * dy
    t = 0 if length == 0 else max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length))
    return ((p.x - a.x - t * dx) ** 2 + (p.y - a.y - t * dy) ** 2) ** 0.5


def _inside(p, pts):
    hit = False
    for a, b in zip(pts, pts[1:] + pts[:1]):
        if (a.y > p.y) != (b.y > p.y) and p.x < a.x + (p.y - a.y) * (b.x - a.x) / (b.y - a.y):
            hit = not hit
    return hit


def _fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def _mat(m):
    return " ".join(_fmt(v) for v in (m.a, m.b, m.c, m.d, m.e, m.f)).encode()


def local_shift(obj, dx, dy):
    """A shift of (dx, dy) in user space, expressed in the object's own drawing coordinates."""
    m = pymupdf.Matrix(obj.ctm.a, obj.ctm.b, obj.ctm.c, obj.ctm.d, 0, 0)
    if abs(m.a * m.d - m.b * m.c) < 1e-12:
        return 0.0, 0.0
    p = pymupdf.Point(dx, dy) * ~m
    return p.x, p.y


def as_matrix(move):
    """A move as a matrix in user space: a plain shift (dx, dy), or a whole matrix (moved, turned, resized)."""
    return pymupdf.Matrix(1, 0, 0, 1, *move) if len(move) == 2 else pymupdf.Matrix(*move)


def local_matrix(obj, move):
    """A change made in user space, expressed in the object's own drawing coordinates (for a cm before it)."""
    c = pymupdf.Matrix(obj.ctm)
    if abs(c.a * c.d - c.b * c.c) < 1e-12:
        return pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    return c * as_matrix(move) * ~c


def rewrite(data, objs, moves, removed):
    """The content stream with objects moved (moves: index -> a move, see as_matrix) and removed."""
    out, pos = [], 0
    for o in objs:
        shift = moves.get(o.index)
        gone = o.index in removed
        if not gone and not shift:
            continue
        out.append(data[pos:o.start])
        if o.kind == "text":
            out.append(_rewrite_text(data, o, shift, gone))
        elif not gone:
            out.append(b"q " + _mat(local_matrix(o, shift)) + b" cm\n")
            out.append(data[o.start:o.end])
            out.append(b"\nQ")
        pos = o.end
        out.append(b"\n")
    out.append(data[pos:])
    return b"".join(out)


def _rewrite_text(data, o, shift, gone):
    parts, pos = [], o.start
    if gone:
        for s, e, op, args in o.shows:
            parts.append(data[pos:s])
            if op == b"'":
                parts.append(b"T*")
            elif op == b'"' and len(args) >= 3:
                parts.append(_fmt(_num(args[0])).encode() + b" Tw " + _fmt(_num(args[1])).encode() + b" Tc T*")
            pos = e
        parts.append(data[pos:o.end])
        return b"".join(parts)
    m = pymupdf.Matrix(o.tm) * local_matrix(o, shift)
    return (_mat(m) + b" Tm\n" + data[o.start:o.end] + b"\n" + _mat(o.tlm_end) + b" Tm")


class PageContent:
    """A page's content stream, its objects, and the moves and removals made to them."""

    def __init__(self, page):
        doc = page.parent
        self.xrefs = page.get_contents()
        self.data = b"\n".join(doc.xref_stream(x) or b"" for x in self.xrefs)
        xobjects = {}
        for xref, name, _invoker, bbox in page.get_xobjects():
            try:
                kind, value = doc.xref_get_key(xref, "Matrix")
                nums = [float(v) for v in value.strip("[]").split()] if kind == "array" else []
                matrix = pymupdf.Matrix(*nums) if len(nums) == 6 else pymupdf.Matrix(1, 0, 0, 1, 0, 0)
            except Exception:
                matrix = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
            xobjects[b"/" + name.encode()] = (True, pymupdf.Rect(bbox), matrix)
        self.objs = parse(self.data, xobjects)
        # From PDF user space to the page as shown (turned pages included).
        self.to_view = page.transformation_matrix * page.rotation_matrix
        self.from_view = ~self.to_view
        self.boxes = [o.bbox * self.to_view for o in self.objs]  # as shown on screen, in points
        self._measure_text(page)
        self.moves = {}  # object index -> its move in user space (see as_matrix)
        self.removed = set()

    def view_matrix(self, i):
        """Object i's move as seen on screen (page points as shown), or None if it hasn't moved."""
        move = self.moves.get(i)
        return self.from_view * as_matrix(move) * self.to_view if move else None

    def view_box(self, i):
        """Where object i is now, in page points as shown."""
        m = self.view_matrix(i)
        return self.boxes[i] if m is None else self.boxes[i] * m

    def add_view_change(self, keys, m):
        """Move, turn or resize objects by a matrix in page points as shown."""
        user = self.to_view * m * self.from_view
        for k in keys:
            old = as_matrix(self.moves[k]) if k in self.moves else pymupdf.Matrix(1, 0, 0, 1, 0, 0)
            new = old * user
            self.moves[k] = tuple(round(v, 6) for v in (new.a, new.b, new.c, new.d, new.e, new.f))

    def _measure_text(self, page):
        """Use the real size of text where it can be found (the box from parse() is a guess)."""
        try:
            trace = page.get_texttrace()
        except Exception:
            return
        starts = {}
        for span in trace:
            if span.get("chars"):
                x, y = span["chars"][0][2]
                starts.setdefault((round(x), round(y)), []).append(((x, y), pymupdf.Rect(span["bbox"])))
        tm, rot = page.transformation_matrix, page.rotation_matrix
        for o in self.objs:
            if o.kind != "text" or not o.origins:
                continue
            box = None
            for org in o.origins:
                q = org * tm
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for (x, y), b in starts.get((round(q.x) + dx, round(q.y) + dy), ()):
                            if abs(x - q.x) < 0.6 and abs(y - q.y) < 0.6:
                                box = b if box is None else box | b
            if box is not None and not box.is_empty:
                self.boxes[o.index] = box * rot

    def touches(self, i, x, y, tol):
        """Whether object i (where it is now) is under the point (page points as shown): near one of
        its lines, or inside it if it is filled. Text and pictures count their whole box."""
        o = self.objs[i]
        if o.kind != "path" or not o.geom:
            return True
        m = self.to_view
        moved = self.view_matrix(i)
        p = pymupdf.Point(x, y) * (~moved if moved is not None else pymupdf.Matrix(1, 0, 0, 1, 0, 0))
        for piece in o.geom:
            pts = [q * m for q in piece]
            if len(pts) == 1 and abs(pts[0] - p) <= tol:
                return True
            for a, b in zip(pts, pts[1:]):
                if _seg_dist(p, a, b) <= tol:
                    return True
            if o.filled and len(pts) > 2 and _inside(p, pts):
                return True
        return False

    def view_delta(self, dx, dy):
        m = self.to_view
        p = pymupdf.Point(dx, dy) * pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
        return p.x, p.y

    def user_delta(self, vx, vy):
        m = self.from_view
        p = pymupdf.Point(vx, vy) * pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
        return p.x, p.y

    def changed(self):
        return bool(self.moves or self.removed)

    def stream(self, moves=None, removed=None):
        return rewrite(self.data, self.objs, self.moves if moves is None else moves,
                       self.removed if removed is None else removed)

    def state(self):
        return dict(self.moves), set(self.removed)

    def set_state(self, state):
        self.moves, self.removed = dict(state[0]), set(state[1])


def set_page_stream(page, data):
    """Give the page a new content stream (a fresh object, so nothing shared is changed)."""
    doc = page.parent
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, data)
    page.set_contents(xref)
