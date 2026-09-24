import json


class Password:
    def __init__(self, id, value, note=''):
        self.id = id
        self.value = value
        self.note = note

    def to_dict(self):
        return {'id': self.id, 'value': self.value, 'note': self.note}

    @staticmethod
    def from_row(row):
        return Password(row[0], row[1], row[2] if len(row) > 2 else '')





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
    def __init__(self, id, name, steps, run_config=None):
        self.id = id
        self.name = name
        self.steps = steps  # JSON string
        self.run_config = run_config if isinstance(run_config, dict) else json.loads(run_config or '{}')

    def to_dict(self, include_steps=True):
        d = {'id': self.id, 'name': self.name}
        if include_steps:
            d['steps'] = self.steps
        return d

    @staticmethod
    def from_row(row):
        run_config = row[3] if len(row) > 3 else '{}'
        return Pipeline(row[0], row[1], row[2], run_config)
