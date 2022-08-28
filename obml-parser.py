#!/usr/bin/env python3
# Converter of Opera Mini OBML saved pages into HTML
#
# (c) 2014–2022 Mantas Mikulėnas <grawity@gmail.com>
# Released under the MIT License
#
# Originally intended to extract original URLs from saved pages, after Opera
# dropped binary compatibilty between minor releases and left me with a bunch
# of unreadable saved pages in v15.

import argparse
import base64
import glob
import io
import itertools
import os
import struct
import sys
import urllib.parse

from pprint import pprint

font_sizes = {
    0: "11px", # medium (default)
    2: "12px", # large
    4: "13px", # extra large
    6: "10px", # small
}

line_height = "1.1"

class BinaryReader():
    def __init__(self, fh):
        self.fh = fh
        self.url_base = "\0"
        self.last_x = 0
        self.last_y = 0

    def debug(self, typ, data):
        if os.environ.get("DEBUG"):
            c_on = "\033[33m" if sys.stdout.isatty() else ""
            c_off = "\033[m" if sys.stdout.isatty() else ""
            print(c_on, "#", typ, repr(data), c_off)
        return data

    @classmethod
    def from_path(self, path):
        return self(open(path, "rb"))

    @classmethod
    def from_bytes(self, buf):
        return self(io.BytesIO(buf))

    # primitives

    def tell(self):
        return self.fh.tell()

    def read(self, length):
        buf = self.fh.read(length)
        if len(buf) < length:
            raise IOError("Hit EOF after %d/%d bytes" % (len(buf), length))
        return self.debug("raw[%d]" % length, buf)

    def read_byte(self):
        length = 1
        buf = self.fh.read(length)
        if len(buf) < length:
            raise IOError("Hit EOF after %d/%d bytes" % (len(buf), length))

        data, = struct.unpack('>B', buf)
        return self.debug("byte", data)

    def read_short(self):
        length = 2
        buf = self.fh.read(length)
        if len(buf) < length:
            raise IOError("Hit EOF after %d/%d bytes" % (len(buf), length))

        data, = struct.unpack('>H', buf)
        return self.debug("short", data)

    def read_medium(self):
        length = 3
        buf = self.fh.read(length)
        if len(buf) < length:
            raise IOError("Hit EOF after %d/%d bytes" % (len(buf), length))

        data_hi, data_lo = struct.unpack('>BH', buf)
        return self.debug("medium", (data_hi << 16) | data_lo)

    def read_blob(self):
        length = self.read_short()
        buf = self.fh.read(length)
        if len(buf) < length:
            raise IOError("Hit EOF after %d/%d bytes" % (len(buf), length))

        return self.debug("chunk[%d]" % length, buf)

    # other data types

    def read_string(self):
        buf = self.read_blob()
        buf = buf.decode('utf-8')
        return self.debug("-> str[%d]" % len(buf), buf)

    def read_url(self, base=None):
        buf = self.read_string()
        if buf and buf[0] == "\0":
            if not base:
                base = self.url_base
            buf = base + buf[1:]
        return self.debug("-> url[%d]" % len(buf), buf)

    def read_color(self):
        a = self.read_byte()
        r = self.read_byte()
        g = self.read_byte()
        b = self.read_byte()
        return self.debug("-> color[argb]", (a, r, g, b))

    def read_coords(self, rel_to_abs=False):
        x = self.read_short()
        y = self.read_medium()
        if rel_to_abs:
            self.last_x = x = (self.last_x + x) & 0xFFFF
            self.last_y = y = (self.last_y + y) & 0xFFFFFF
        else:
            # in v15+, all positions are relative and never depend on
            # earlier absolute coordinates (which are only used for sizes)
            pass
        return self.debug("-> coords[%s]" % ("rel" if rel_to_abs else "abs"), (x, y))

def strhex(buf):
    return " ".join(["%02X" % x for x in buf])

def rgba(argb_tuple):
    a, r, g, b = argb_tuple
    if a == 0 or a == 255:
        return "rgb(%d, %d, %d)" % (r, g, b)
    else:
        return "rgba(%d, %d, %d, %.3f)" % (r, g, b, a/255)

def data_url(buf):
    if buf.startswith(b"\x89PNG\r\n"):
        img_type = "image/png"
    elif buf.startswith(b"\xff\xd8"):
        img_type = "image/jpeg"
    else:
        img_type = "application/octet-stream"
    encoded = base64.b64encode(buf)
    encoded = urllib.parse.quote(encoded)
    return "data:%s;base64,%s" % (img_type, encoded)

def css_imgdata(buf):
    return "url('%s')" % data_url(buf)

def parse_file(arg):
    print("file =", arg)
    f = BinaryReader.from_path(arg)

    expected_size = f.read_medium()
    total_start = f.tell()
    version = f.read_byte()
    print("version =", version)

    if version == 16:
        assert(expected_size == 0x02d355)
        expected_size = f.read_medium()
        version = f.read_byte()
        print("real version =", version)
        exp_total_bytes = expected_size + 7
    elif version == 15:
        raise ValueError("bad header for version %r" % version)
    else:
        exp_total_bytes = expected_size + 3

    exp_links_bytes = 0

    if version not in {6, 12, 13, 15, 16}:
        raise ValueError("unknown version %r" % version)

    page_size = f.read_coords()
    if version == 16:
        assert(f.read(2) in {b'\x00\x00', b'\xff\xff'})
    else:
        assert(f.read(5) == b'S\x00\x00\xff\xff')
    page_title = f.read_string()
    x = f.read_blob() # 'C\x10\x10...' on v15, nil elsewhere
    #print("Ignoring unknown header field:", repr(x))
    f.url_base = f.read_string()
    page_url = f.read_url()
    yield {"_type": "head",
           "title": page_title,
           "url": page_url,
           "dimensions": page_size}

    if version >= 15:
        x = f.read(6)
        print("Ignoring unknown header fields:", repr(x))
    elif version == 6:
        x = f.read(1)
        print("Ignoring unknown header fields:", repr(x))
    else:
        x1 = f.read_short()
        x2 = f.read_medium()
        print("Ignoring unknown header fields:", repr(x1), repr(x2))

    # metadata section

    while True:
        print("--- metadata [%d] ---" % f.tell(), end=" ")
        type = f.read(1)
        print(type)
        if None:
            pass
        elif type == b"C":
            # Unknown.
            if version >= 15:
                x = f.read(23)
                print("Ignoring unknown chunk:", repr(type), repr(x))
            else:
                raise ValueError("unhandled metadata chunk %r/v%r" % (type, version))
        elif type == b"M":
            # Unknown metadata. Types b'C\x00' and b'u\x00' seen here.
            x1 = f.read(2)
            x2 = f.read_blob()
            print("Ignoring unknown chunk:", repr(type), repr(x1), repr(x2))
        elif type == b"S":
            # Embedded link target data. Might be meant as a "skip" marker,
            # with a later "L"-chunk referencing the data stored here.
            exp_links_bytes = f.read_medium()
            break
        else:
            raise ValueError("unknown metadata chunk %r" % type)

    print("section 1 ends at %d" % f.tell())

    # link sub-section
    #
    # This is *not* the same types as toplevel metadata/content chunks (e.g.
    # the "C" and "L" definitions conflict).
    #
    # Instead, it should perhaps be handled as part of the "S"-chunk, just like
    # it is done for embedded image data later in the content section.
    #
    # The content "L"-chunk appears to point back to this subsection.

    links_start = f.tell()
    links_end = f.tell() + exp_links_bytes

    while f.tell() < links_end:
        print("--- links [%d] ---" % f.tell(), end=" ")
        type = f.read(1)
        print(type)
        if None:
            pass
        elif type == b"\x00":
            # <option> selections
            _ = f.read(1)
            n = f.read_byte()
            options = []
            for j in range(n):
                opt_val = f.read_string()
                opt_text = f.read_string()
                options.append((opt_val, opt_text))
            yield {"_type": "option_list",
                   "data": options}
        elif type in {b"i", b"L", b"P", b"w", b"W"}:
            # 'i' - links to image original URLs
            # 'L' - standard text links
            # 'P' - "platform" (mailto) links
            # 'w' - "image download" links
            # 'W' - links to open images in the native browser
            # All follow the common 'region' format.
            n = f.read_byte()
            boxes = []
            for j in range(n):
                pos = f.read_coords()
                size = f.read_coords()
                boxes.append((pos, size))
            if version >= 15 or version == 13:
                link_url = f.read_url()
                _ = f.read(2) # Usually "\x01t" in v15
                link_type = f.read_string()
            elif version in {12, 6}:
                link_type = f.read_string()
                link_url = f.read_url()
            if type == b"i":
                for pos, size in boxes:
                    if size[0] > 16 and size[1] > 16:
                        yield {"_type": "link",
                               "kind": "image",
                               "href": link_url,
                               "type": link_type,
                               "pos": pos,
                               "size": size}
            else:
                if not link_url.startswith("b:"):
                    for pos, size in boxes:
                        yield {"_type": "link",
                               "href": link_url,
                               "type": link_type,
                               "pos": pos,
                               "size": size}
        elif type in {b"C", b"I", b"N", b"S"} and version >= 15:
            # Unknown link types.
            # All follow the common 'region' format.
            n = f.read_byte()
            boxes = []
            for j in range(n):
                pos = f.read_coords()
                size = f.read_coords()
                boxes.append((pos, size))
            x1 = f.read_blob()
            x2 = f.read(2) # Usually b"\x01t"
            x3 = f.read_blob()
            print("Ignoring unknown link chunk:", repr(type), boxes, repr(x1), repr(x2), repr(x3))
        elif type in {b"S"} and version == 13:
            # Unknown link types.
            # All follow the common 'region' format.
            n = f.read_byte()
            boxes = []
            for j in range(n):
                pos = f.read_coords()
                size = f.read_coords()
                boxes.append((pos, size))
            x1 = f.read_blob()
            x2 = f.read(2)
            x3 = f.read_blob()
            print("Ignoring unknown link chunk:", repr(type), boxes, repr(x1), repr(x2), repr(x3))
        elif type == b"N" and version == 12:
            # Anchor link.
            # Follows the common 'region' format.
            n = f.read_byte()
            boxes = []
            for j in range(n):
                pos = f.read_coords()
                size = f.read_coords()
                boxes.append((pos, size))
            link_type = f.read_blob() # Usually empty
            link_target = f.read_blob()
            g = BinaryReader.from_bytes(link_target)
            target_coords = g.read_coords()
            target_anchor = g.read_string()
            for pos, size in boxes:
                yield {"_type": "link",
                       "kind": "anchor",
                       "href": "javascript:window.scroll(%d, %d)" % target_coords,
                       "type": link_type,
                       "pos": pos,
                       "size": size}
        elif type in {b"C", b"I", b"N", b"S"} and version in {12, 6}:
            # Unknown link types.
            # All follow the common <=12 'region' format.
            n = f.read_byte()
            boxes = []
            for j in range(n):
                pos = f.read_coords()
                size = f.read_coords()
                boxes.append((pos, size))
            x1 = f.read_blob()
            x2 = f.read_blob()
            print("Ignoring unknown link chunk:", repr(type), boxes, repr(x1), repr(x2))
            #if type in {}:
            #    for pos, size in boxes:
            #        yield {"_type": "link",
            #               "kind": "unknown",
            #               "href": "",
            #               "type": link_type,
            #               "pos": pos,
            #               "size": size}
        else:
            raise ValueError("unknown link chunk %r/v%r" % (type, version))

    print("section 2 ends at %d" % f.tell())
    if f.tell() != links_end:
        raise ValueError("link section ended at %d, expected %d" % (f.tell(), links_end))

    # content section
    #
    # If we move link chunk handling to a nested parser, then there's a
    # possibility for content & metadata to be merged into a single toplevel
    # parser... assuming I figure out the correct way to distinguish the two
    # "S"-chunks.

    content_start = f.tell()
    content_end = exp_total_bytes

    while f.tell() < content_end:
        print("--- content [%d] ---" % f.tell(), end=" ")
        type = f.read(1)
        print(type)
        if None:
            pass
        elif type == b"B":
            # Filled rectangle (box or line)
            if version >= 15:
                pos = f.read_coords(rel_to_abs=True)
                size = f.read_coords()
                color = f.read_color()
            else:
                pos = f.read_coords()
                size = f.read_coords()
                color = f.read_color()
            yield {"_type": "box",
                   "pos": pos,
                   "size": size,
                   "fill": color}
        elif type == b"F":
            # Form field
            if version >= 15:
                pos = f.read_coords(rel_to_abs=True)
                size = f.read_coords()
                color = f.read_color()
            else:
                pos = f.read_coords()
                size = f.read_coords()
                color = f.read_color()
            field_type = f.read(1)
            f.read(1)
            field_id = f.read_string()
            field_value = f.read_string()
            if version >= 15:
                f.read(5)
            else:
                f.read(3)
            if field_type in {b"c", b"r"}:
                # hack
                pos = (pos[0] - 8, pos[1] - 8)
                size = (size[0] + 8, size[1] + 8)
            yield {"_type": "input",
                   "kind": {
                       b"a": "textarea",
                       b"c": "checkbox",
                       b"r": "radio",
                       b"s": "select",
                       b"x": "text",
                   }.get(field_type),
                   "value": field_value,
                   "pos": pos,
                   "size": size,
                   "color": color}
        elif type == b"I":
            # Image area (pointer to a PNG blob)
            addr = 0
            if version == 16:
                pos = f.read_coords(rel_to_abs=True)
                size = f.read_coords()
                color = f.read_color()
                addr = f.read_medium()
                n = f.read_byte()       # Seems to always be 1 or 2
                for j in range(n):
                    x1 = f.read(1)      # Seems to always be 'c' first, 'o' second (if present)
                    x2 = f.read_blob()  # Seems to be 4-byte, unknown for 'c', all-zero for 'o'
                    #print("Ignoring unknown image fields:", repr(x1), repr(x2))
            elif version == 15:
                pos = f.read_coords(rel_to_abs=True)
                size = f.read_coords()
                color = f.read_color()
                _x = f.read(14)
                print("Ignoring unknown image fields:", repr(type), repr(_x))
                # XXX: 'addr' is missing in v15!
                # The format is probably the same as v16 though.
                raise Exception("XXX: v15 'I'-chunk parsing is incomplete (address is missing)!")
            else:
                pos = f.read_coords()
                size = f.read_coords()
                color = f.read_color()
                _x = f.read(3) # medium_int (usually 0, 2, 4)
                #print("Ignoring unknown image fields:", repr(type), repr(_x))
                addr = f.read_medium()
            yield {"_type": "box",
                   "kind": "image",
                   "pos": pos,
                   "size": size,
                   "fill": color,
                   "blob": addr}
        elif type == b"L":
            # Unknown. Looks like 3x medium_ints, might be a pointer to the link-subsection.
            x1 = f.read_medium()
            x2 = f.read_medium()
            x3 = f.read_medium()
            # It seems that total_start+x2 is the pointer to the links S-chunk
            # while total_start+x3 is approximately the end.
            print("Ignoring unknown chunk:", repr(type), repr(x1), repr(x2), repr(x3))
            print("XXX", repr(total_start+x1), repr(total_start+x2), repr(total_start+x3))
        elif type == b"M":
            # Unknown, probably the same as in "metadata" area.
            # Type b'T\x00' seen here - the blob looks like it consists entirely of medium_ints.
            x1 = f.read(2)
            x2 = f.read_blob()
            #print("Ignoring unknown chunk:", repr(type), repr(x1), repr(x2))
        elif type == b"S":
            # Embedded image data. Always last chunk in this section. Might be
            # meant as a "skip" marker, with individual "I"-chunks referencing
            # the data stored here.
            exp_files_bytes = f.read_medium()
            files_start = f.tell()
            files_end = f.tell() + exp_files_bytes
            while f.tell() < files_end:
                if version == 6:
                    addr = f.tell() - total_start
                else:
                    addr = f.tell() - files_start
                buf = f.read_blob()
                yield {"_type": "file",
                       "addr": addr,
                       "data": buf}
            print("files started at %d, ends at %d" % (files_start, f.tell()))
            if f.tell() != files_end:
                raise ValueError("content.files section ended at %d, expected %d" % (f.tell(), files_end))
            break
        elif type == b"T":
            # Text
            if version == 16:
                pos = f.read_coords(rel_to_abs=True)
                size = f.read_coords()
                color = f.read_color()
                f.read(1)
                font = 4 | (f.read_byte() & 1)
                n = f.read_byte()       # Might be 0 or 1
                for j in range(n):
                    x1 = f.read(1)      # Seems to always contain 'c'
                    x2 = f.read_blob()  # Seems to contain 1 short, sometimes negative
                    print("Ignoring unknown text fields:", repr(x1), repr(x2))
                text = f.read_string()
            elif version == 15:
                pos = f.read_coords(rel_to_abs=True)
                size = f.read_coords()
                color = f.read_color()
                font = f.read_byte()
                text = f.read_string()
            else:
                pos = f.read_coords()
                size = f.read_coords()
                color = f.read_color()
                font = f.read_byte()
                text = f.read_string()
            yield {"_type": "text",
                   "text": text,
                   "font": font,
                   "color": color,
                   "pos": pos,
                   "size": size}
        elif type == b"z":
            # Unknown.
            if version == 16:
                f.read(6)
            else:
                raise ValueError("unhandled content chunk %r/v%r" % (type, version))
        else:
            raise ValueError("unknown content chunk %r/v%r" % (type, version))

    print("section 3 started at %d, ends at %d" % (content_start, f.tell()))
    if f.tell() != content_end:
        raise ValueError("content section ended at %d, expected %d" % (f.tell(), content_end))


def process_one_file(arg):
    with open("%s.html" % arg, "w", encoding="utf-8") as fout:
        id_alloc = itertools.count()
        boxes_by_fileaddr = {}
        empty_boxes = set()
        option_lists = {}
        n_option_lists = itertools.count()
        n_select_fields = itertools.count()

        fout.write('<!DOCTYPE html>\n')
        fout.write('<meta charset="utf-8">\n')
        fout.write('<style>\n'
                   'html {\n'
                   '  background: #ddd;\n'
                   '}\n'
                   '.item {\n'
                   '  position: absolute;\n'
                   '}\n'
                   '.body {\n'
                   '  background: white;\n'
                   '  z-index: -200;\n'
                   '}\n'
                   '.box {\n'
                   '  z-index: -100;\n'
                   '}\n'
                   '.img {\n'
                   '  z-index: -50;\n'
                   '  background-size: contain;\n'
                   '}\n'
                   '.link {\n'
                   '  display: block;\n'
                   '  text-decoration: none;\n'
                   '  z-index: 100;\n'
                   '}\n'
                   '.link:hover {\n'
                   '  outline: 1px solid blue;\n'
                   '}\n'
                   '.imglink {\n'
                   '  color: gray;\n'
                   '  z-index: 150;\n'
                   '}\n'
                   '.unknownlink {\n'
                   '  background: orange;\n'
                   '  z-index: 150;\n'
                   '}\n'
                   '.text, .field {\n'
                   '  font-family: sans-serif;\n'
                   '  font-size: %s;\n'
                   '  line-height: %s;\n'
                   '  white-space: pre;\n'
                   '}\n'
                   '.form {\n'
                   '  border: none;\n'
                   '  padding: none;\n'
                   '}\n'
                   '</style>\n' % (font_sizes[0], line_height))
        for item in parse_file(arg):
            type = item["_type"]
            #pprint(item)
            if type == "head":
                fout.write('<!-- origin: %s -->\n' % item["url"])
                fout.write('<title>%s</title>\n' % item["title"])
                page_w, page_h = item["dimensions"]
                style = [
                    "left: %dpx" % 0,
                    "top: %dpx" % 0,
                    "width: %dpx" % page_w,
                    "height: %dpx" % page_h,
                ]
                style = "; ".join(style)
                fout.write('<div class="item body" style="%s"></div>' % style)
            elif type == "text":
                item_x, item_y = item["pos"]
                item_w, item_h = item["size"]
                font_size = item["font"] & ~1
                font_weight = item["font"] & 1
                style = [
                    "font-size: %s" % font_sizes[font_size],
                    "font-weight: %s" % ("bold" if font_weight else "normal"),
                    "color: %s" % rgba(item["color"]),
                    "left: %dpx" % item_x,
                    "top: %dpx" % item_y,
                    "width: %dpx" % item_w,
                    "height: %dpx" % item_h,
                ]
                style = "; ".join(style)
                fout.write('<div class="item text" style="%s">' % style)
                fout.write(item["text"])
                fout.write('</div>\n')
            elif type == "box":
                item_x, item_y = item["pos"]
                item_w, item_h = item["size"]
                style = [
                    "background-color: %s" % rgba(item["fill"]),
                    "left: %dpx" % item_x,
                    "top: %dpx" % item_y,
                    "width: %dpx" % item_w,
                    "height: %dpx" % item_h,
                ]
                style = "; ".join(style)
                if item.get("kind") == "image":
                    box_id = "imgbox_%d" % next(id_alloc)
                    fout.write('<div class="item img" style="%s" id="%s"></div>\n' % (style, box_id))
                    empty_boxes.add(box_id)
                    boxes_by_fileaddr.setdefault(item["blob"], []).append(box_id)
                else:
                    fout.write('<div class="item box" style="%s"></div>\n' % style)
            elif type == "option_list":
                list_id = next(n_option_lists)
                option_lists[list_id] = item["data"]
            elif type == "input":
                item_x, item_y = item["pos"]
                item_w, item_h = item["size"]
                style = [
                    "color: %s" % rgba(item["color"]),
                    "left: %dpx" % item_x,
                    "top: %dpx" % item_y,
                    "width: %dpx" % item_w,
                    "height: %dpx" % item_h,
                ]
                style = "; ".join(style)
                if item["kind"] == "textarea":
                    fout.write('<textarea class="item form field" style="%s">%s</textarea>\n' % (style, item["value"]))
                elif item["kind"] == "text":
                    fout.write('<input class="item form field" style="%s" type="text" value="%s">\n' % (style, item["value"]))
                elif item["kind"] in {"checkbox", "radio"}:
                    fout.write('<input class="item form" style="%s" type="%s" value="%s">\n' % (style, item["kind"], item["value"]))
                elif item["kind"] == "select":
                    list_id = next(n_select_fields)
                    fout.write('<select class="item field" style="%s">\n' % style)
                    for opt_id, opt_text in option_lists[list_id]:
                        fout.write('<option>%s</option>\n' % opt_text)
                    fout.write('</select>\n')
            elif type == "link":
                item_x, item_y = item["pos"]
                item_w, item_h = item["size"]
                if item.get("kind") == "image":
                    klass = "link imglink"
                    style = [
                        "left: %dpx" % item_x,
                        "top: %dpx" % item_y,
                    ]
                    text = "↖"
                elif item.get("kind") == "unknown":
                    klass = "link unknownlink"
                    style = []
                    text = "?????"
                else:
                    klass = "link"
                    style = [
                        "left: %dpx" % item_x,
                        "top: %dpx" % item_y,
                        "width: %dpx" % item_w,
                        "height: %dpx" % item_h,
                    ]
                    text = ""
                style = "; ".join(style)
                fout.write('<a class="item %s" href="%s" style="%s">%s</a>\n' % (klass, item["href"], style, text))
            elif type == "file":
                fout.write('<script>\n')
                box_ids = boxes_by_fileaddr.get(item["addr"])
                if box_ids:
                    fout.write('var bg = "%s";\n' % css_imgdata(item["data"]))
                    for box_id in box_ids:
                        empty_boxes.remove(box_id)
                        fout.write('var div = document.getElementById("%s");\n' % box_id)
                        fout.write('div.style.backgroundImage = bg;\n')
                        fout.write('div.style.backgroundColor = "";\n')
                else:
                    fout.write('/* file @ %r not referenced by any image */\n' % item["addr"])
                    print("warning: file @ %r was not referenced by any image" % item["addr"], file=sys.stderr)
                fout.write('</script>\n')
        for box_id in sorted(empty_boxes):
            print("warning: image box %r is missing a file" % box_id, file=sys.stderr)


parser = argparse.ArgumentParser()
parser.add_argument("obml_file", nargs="*")
args = parser.parse_args()

if not args.obml_file:
    args.obml_file = glob.glob("*.obml*")

for arg in args.obml_file:
    process_one_file(arg)
