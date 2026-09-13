import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from . import repository

_instance = None


def get_service():
    global _instance
    if _instance is None:
        _instance = FilePipelineService()
    return _instance


class FilePipelineService:

    def run_pipeline(self, pipeline_id, folder_path):
        pipeline = repository.get_pipeline(pipeline_id)
        if not pipeline:
            raise ValueError(f'Pipeline {pipeline_id} not found')

        graph = json.loads(pipeline.steps)
        tools = {t.id: t for t in repository.get_tools()}

        if not os.path.isdir(folder_path):
            raise ValueError(f'Folder not found: {folder_path}')

        files = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
        ]

        all_results = []
        for f in files:
            results = self._run_file(f, graph, tools)
            all_results.extend(results)
        return all_results

    def _run_file(self, file_path, graph, tools):
        nodes = {n['id']: n for n in graph.get('nodes', [])}
        edges = graph.get('edges', [])

        adj = defaultdict(list)
        for e in edges:
            adj[e['from']].append((e.get('label', ''), e['to']))

        start = next((n for n in nodes.values() if n['type'] == 'start'), None)
        if not start:
            return [{'file': file_path, 'status': 'error', 'error': 'No start node', 'steps_taken': []}]

        work_items = [(file_path, start['id'], [])]
        results = []

        while work_items:
            cur_file, cur_node_id, steps_taken = work_items.pop(0)
            node = nodes.get(cur_node_id)
            if not node:
                results.append({'file': cur_file, 'status': 'error', 'error': f'Node {cur_node_id} missing', 'steps_taken': steps_taken})
                continue

            if node['type'] == 'end':
                results.append({'file': cur_file, 'status': 'done', 'steps_taken': steps_taken, 'error': ''})
                continue

            if node['type'] == 'start':
                next_ids = [t for _, t in adj[cur_node_id]]
                for nid in next_ids:
                    work_items.append((cur_file, nid, steps_taken[:]))
                continue

            try:
                next_files, next_node_ids = self._execute_step(cur_file, node, adj, tools)
                new_steps = steps_taken + [node['type']]
                for nf, nid in zip(next_files, next_node_ids):
                    work_items.append((nf, nid, new_steps[:]))
            except Exception as ex:
                results.append({'file': cur_file, 'status': 'error', 'error': str(ex), 'steps_taken': steps_taken + [node['type']]})

        return results

    def _execute_step(self, cur_file, node, adj, tools):
        ntype = node['type']
        params = node.get('params', {})

        if ntype == 'rename_ext':
            new_ext = params.get('new_ext', '').strip().lstrip('.')
            base = os.path.splitext(cur_file)[0]
            new_path = f'{base}.{new_ext}'
            os.rename(cur_file, new_path)
            cur_file = new_path

        elif ntype == 'strip_cjk':
            dirname = os.path.dirname(cur_file)
            basename = os.path.basename(cur_file)
            new_basename = re.sub(r'(\.[^.]+)[一-鿿　-〿＀-￯]+$', r'\1', basename)
            if new_basename != basename:
                new_path = os.path.join(dirname, new_basename)
                os.rename(cur_file, new_path)
                cur_file = new_path

        elif ntype == 'extract':
            cur_file = self._extract(cur_file, params, tools)

        elif ntype == 'condition':
            return self._condition(cur_file, node, adj)

        # default: follow all outgoing edges with the current file
        next_ids = [t for _, t in adj[node['id']]]
        if not next_ids:
            next_ids = ['__end__']
        return [cur_file] * len(next_ids), next_ids

    def _extract(self, archive_path, params, tools):
        tool_id = params.get('tool_id')
        password = params.get('password', '')
        password_required = params.get('password_required', False)

        tool = tools.get(tool_id) if tool_id else None
        if not tool:
            raise ValueError(f'Tool {tool_id} not configured in toolbox')

        dest_dir = os.path.dirname(archive_path)

        before = set(os.listdir(dest_dir))

        cmd = tool.args_template
        cmd = cmd.replace('{archive}', archive_path)
        cmd = cmd.replace('{dest}', dest_dir)
        if password and password_required:
            cmd = cmd.replace('{password}', password)
        else:
            cmd = re.sub(r'-p\{password\}', '', cmd)
            cmd = re.sub(r'\{password\}', '', cmd)

        full_cmd = [tool.exe_path] + cmd.split()
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f'Extraction failed: {result.stderr or result.stdout}')

        after = set(os.listdir(dest_dir))
        new_items = [os.path.join(dest_dir, x) for x in (after - before)]

        if not new_items:
            raise RuntimeError('No files produced by extraction')

        if len(new_items) == 1:
            item = new_items[0]
            if os.path.isdir(item):
                contents = os.listdir(item)
                if len(contents) == 1:
                    return os.path.join(item, contents[0])
                return item
            return item

        return new_items[0]

    def _condition(self, cur_file, node, adj):
        basename = os.path.basename(cur_file)
        outgoing = adj[node['id']]  # list of (label, target_id)

        default_target = None
        for label, target_id in outgoing:
            if label == 'default' or label == '':
                default_target = target_id
                continue
            if label and label in basename:
                return [cur_file], [target_id]

        if default_target:
            return [cur_file], [default_target]

        return [cur_file], ['__end__']
