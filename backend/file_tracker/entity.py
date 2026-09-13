"""File Tracker — entities."""


class TrackedFile:
    def __init__(self, id, path, size_bytes, mtime, atime, last_active,
                 status='normal', scan_time=None, note=''):
        self.id = id
        self.path = path
        self.size_bytes = size_bytes
        self.mtime = mtime
        self.atime = atime
        self.last_active = last_active
        self.status = status
        self.scan_time = scan_time
        self.note = note

    def to_dict(self):
        return {
            'id': self.id,
            'path': self.path,
            'size_bytes': self.size_bytes,
            'mtime': self.mtime,
            'atime': self.atime,
            'last_active': self.last_active,
            'status': self.status,
            'scan_time': self.scan_time,
            'note': self.note,
        }

    @staticmethod
    def from_row(r):
        return TrackedFile(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8])
