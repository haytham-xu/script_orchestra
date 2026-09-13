class Tool:
    def __init__(self, id, name, exe_path, args_template):
        self.id = id
        self.name = name
        self.exe_path = exe_path
        self.args_template = args_template

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'exe_path': self.exe_path,
            'args_template': self.args_template,
        }

    @staticmethod
    def from_row(row):
        return Tool(row[0], row[1], row[2], row[3])


class Pipeline:
    def __init__(self, id, name, steps):
        self.id = id
        self.name = name
        self.steps = steps  # JSON string

    def to_dict(self, include_steps=True):
        d = {'id': self.id, 'name': self.name}
        if include_steps:
            d['steps'] = self.steps
        return d

    @staticmethod
    def from_row(row):
        return Pipeline(row[0], row[1], row[2])
