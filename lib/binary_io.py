import io
import os
import struct
import sys

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
