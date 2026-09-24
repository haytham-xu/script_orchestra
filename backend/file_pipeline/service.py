import json
import os
import re
import shlex
import shutil
import subprocess
from collections import defaultdict
from . import repository

_instance = None


def get_service():
    global _instance
    if _instance is None:
        _instance = FilePipelineService()
    return _instance


_BRANCH_TYPES = {'condition', 'is_file_or_dir', 'enter_folder'}


class FilePipelineService:

    def run_pipeline(self, pipeline_id, folder_path, run_vars=None, progress_cb=None):
        pipeline = repository.get_pipeline(pipeline_id)
        if not pipeline:
            raise ValueError(f'Pipeline {pipeline_id} not found')

        graph = json.loads(pipeline.steps)
        tools = {t.id: t for t in repository.get_tools()}

        if not os.path.isdir(folder_path):
            raise ValueError(f'Folder not found: {folder_path}')

        files = [os.path.join(folder_path, f) for f in os.listdir(folder_path)]

        run_vars = run_vars or {}
        total = len(files)
        if progress_cb:
            progress_cb({'phase': 'start', 'total_files': total})

        all_results = []
        for i, f in enumerate(files):
            if progress_cb:
                progress_cb({'phase': 'file_start', 'file': f, 'file_index': i, 'total_files': total})
            results = self._run_file(f, graph, tools, run_vars, progress_cb, i, total)
            all_results.extend(results)
            if progress_cb:
                progress_cb({'phase': 'file_done', 'file': f, 'file_index': i, 'total_files': total, 'results': results})

        if progress_cb:
            progress_cb({'phase': 'done', 'total_files': total})
        return all_results

    def _run_file(self, file_path, graph, tools, run_vars, progress_cb=None, file_index=0, total_files=1):
        nodes = {n['id']: n for n in graph.get('nodes', [])}
        edges = graph.get('edges', [])

        adj = defaultdict(list)
        for e in edges:
            adj[e['from']].append((e.get('label', ''), e['to']))

        start = next((n for n in nodes.values() if n['type'] == 'start'), None)
        if not start:
            return [{'file': file_path, 'status': 'error', 'error': 'No start node', 'steps_taken': []}]

        # ctx carries per-file execution state (recorded sizes/paths) along each branch
        work_items = [(file_path, start['id'], [], {})]
        results = []

        while work_items:
            cur_file, cur_node_id, steps_taken, ctx = work_items.pop(0)
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
                    work_items.append((cur_file, nid, steps_taken[:], dict(ctx)))
                continue

            step_num = len(steps_taken) + 1
            if progress_cb:
                progress_cb({
                    'phase': 'step',
                    'file': cur_file,
                    'file_index': file_index,
                    'total_files': total_files,
                    'step_num': step_num,
                    'node_type': node['type'],
                    'node_id': node['id'],
                })

            try:
                next_files, next_node_ids = self._execute_step(cur_file, node, adj, tools, run_vars, ctx, progress_cb, file_index, total_files)
                new_steps = steps_taken + [node['type']]

                if progress_cb and node['type'] in _BRANCH_TYPES and next_node_ids:
                    taken_id = next_node_ids[0]
                    branch_label = next(
                        (lbl for lbl, tid in adj[node['id']] if tid == taken_id),
                        '__end__',
                    )
                    progress_cb({
                        'phase': 'step_branch',
                        'file': cur_file,
                        'file_index': file_index,
                        'total_files': total_files,
                        'node_type': node['type'],
                        'branch': branch_label,
                    })

                for nf, nid in zip(next_files, next_node_ids):
                    work_items.append((nf, nid, new_steps[:], dict(ctx)))
            except Exception as ex:
                results.append({'file': cur_file, 'status': 'error', 'error': str(ex), 'steps_taken': steps_taken + [node['type']]})

        return results

    def _execute_step(self, cur_file, node, adj, tools, run_vars, ctx, progress_cb=None, file_index=0, total_files=1):
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
            new_basename = re.sub(r'(\.[^.]+)[' + '\u4e00-\u9fff\u3000-\u303f\uff00-\uffef' + r']+$', r'\1', basename)
            if new_basename != basename:
                new_path = os.path.join(dirname, new_basename)
                os.rename(cur_file, new_path)
                cur_file = new_path

        elif ntype == 'mkdir_and_move':
            dirname = os.path.dirname(cur_file)
            basename = os.path.basename(cur_file)
            name_no_ext = os.path.splitext(basename)[0]
            new_dir = os.path.join(dirname, name_no_ext)
            os.makedirs(new_dir, exist_ok=True)
            new_path = os.path.join(new_dir, basename)
            os.rename(cur_file, new_path)
            cur_file = new_path

        elif ntype == 'extract':
            cur_file = self._extract(cur_file, params, tools)

        elif ntype == 'move_to':
            output_path = run_vars.get('output_path') or params.get('output_path', '')
            output_path = output_path.strip()
            if not output_path:
                raise ValueError('move_to: output_path is not configured')
            os.makedirs(output_path, exist_ok=True)
            dest = os.path.join(output_path, os.path.basename(cur_file))
            os.rename(cur_file, dest)
            cur_file = dest

        elif ntype == 'record_size':
            key = params.get('key', 'x')
            ctx[key + '_path'] = cur_file
            ctx[key + '_size'] = self._path_size(cur_file)

        elif ntype == 'size_cleanup':
            cleaned = self._size_cleanup(cur_file, params, ctx, run_vars)
            if progress_cb:
                progress_cb({
                    'phase': 'size_cleanup',
                    'file': cur_file,
                    'file_index': file_index,
                    'total_files': total_files,
                    'cleaned': cleaned,
                    'x0_size': ctx.get('x0_size', 0),
                    'x1_size': ctx.get('x1_size', 0),
                    'x2_size': ctx.get('x2_size', 0),
                })

        elif ntype == 'find_part1':
            cur_file = self._find_part1(cur_file)

        elif ntype == 'strip_suffix':
            suffix = params.get('suffix', '').strip()
            if suffix and cur_file.endswith(suffix):
                new_path = cur_file[:-len(suffix)]
                os.rename(cur_file, new_path)
                cur_file = new_path

        elif ntype == 'is_file_or_dir':
            return self._is_file_or_dir(cur_file, node, adj)

        elif ntype == 'enter_folder':
            return self._enter_folder(cur_file, node, adj)

        elif ntype == 'condition':
            return self._condition(cur_file, node, adj)

        next_ids = [t for _, t in adj[node['id']]]
        if not next_ids:
            next_ids = ['__end__']
        return [cur_file] * len(next_ids), next_ids

    def _find_part1(self, folder_path):
        """Find the first part of a split archive (.001 / .part1.rar / .part01.rar) in folder."""
        if not os.path.isdir(folder_path):
            raise ValueError(f'find_part1: expected a directory, got {folder_path}')
        candidates = []
        for name in os.listdir(folder_path):
            if re.search(r'\.001$', name, re.IGNORECASE):
                candidates.append(os.path.join(folder_path, name))
            elif re.search(r'\.part0*1\.rar$', name, re.IGNORECASE):
                candidates.append(os.path.join(folder_path, name))
        if not candidates:
            raise ValueError(f'find_part1: no .001 / .part1.rar file found in {folder_path}')
        return sorted(candidates)[0]

    def _path_size(self, path):
        """Total size in bytes — works for both files and directories."""
        if not os.path.exists(path):
            return 0
        if os.path.isfile(path):
            return os.path.getsize(path)
        total = 0
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        return total

    def _size_cleanup(self, cur_file, params, ctx, run_vars):
        """If x0/x1/x2 sizes are all within threshold of each other:
        delete the archive (x0_path) and move first-extract output (x1_path) to delete_path."""
        threshold = params.get('threshold', 0.2)
        x0_size = ctx.get('x0_size', 0)
        x1_size = ctx.get('x1_size', 0)
        x2_size = ctx.get('x2_size', 0)

        if not x0_size or not x1_size or not x2_size:
            return False

        sizes = [x0_size, x1_size, x2_size]
        max_s, min_s = max(sizes), min(sizes)
        if max_s == 0 or (max_s - min_s) / max_s > threshold:
            return False  # sizes differ too much — keep everything

        delete_path = run_vars.get('delete_path', '').strip()

        # Delete the original file or folder (x0)
        x0_path = ctx.get('x0_path', '')
        if x0_path and os.path.exists(x0_path):
            if os.path.isdir(x0_path):
                shutil.rmtree(x0_path)
            else:
                os.remove(x0_path)
                # Remove parent folder if now empty (created by mkdir_and_move)
                parent = os.path.dirname(x0_path)
                try:
                    if parent and os.path.isdir(parent) and not os.listdir(parent):
                        os.rmdir(parent)
                except OSError:
                    pass

        # Move first-extract output (x1) to delete_path
        x1_path = ctx.get('x1_path', '')
        if x1_path and os.path.exists(x1_path) and delete_path:
            os.makedirs(delete_path, exist_ok=True)
            dest = os.path.join(delete_path, os.path.basename(x1_path))
            os.rename(x1_path, dest)

        return True

    def _extract(self, archive_path, params, tools):
        tool_id = params.get('tool_id')
        password = params.get('password', '')
        password_required = params.get('password_required', False)
        use_password_list = params.get('use_password_list', False)

        tool = tools.get(tool_id) if tool_id else None
        if not tool:
            raise ValueError(f'Tool {tool_id} not configured in toolbox')

        dest_dir = os.path.dirname(archive_path)

        passwords = []
        if password_required and password:
            passwords.append(password)
        if use_password_list:
            if None not in passwords:
                passwords.append(None)   # always try no-password before vault
            for p in repository.get_passwords():
                if p.value not in passwords:
                    passwords.append(p.value)
        if not passwords:
            passwords = [None]

        for pwd in passwords:
            new_items = self._try_extract(archive_path, tool, dest_dir, pwd)
            if new_items:
                if len(new_items) == 1:
                    item = new_items[0]
                    if os.path.isdir(item):
                        contents = os.listdir(item)
                        if len(contents) == 1:
                            return os.path.join(item, contents[0])
                        return item
                    return item
                # Multiple new items — prefer a directory (extracted folder),
                # otherwise pick the largest file
                dirs = [p for p in new_items if os.path.isdir(p)]
                if dirs:
                    return dirs[0]
                files_only = [p for p in new_items if os.path.isfile(p)]
                if files_only:
                    return max(files_only, key=lambda p: os.path.getsize(p))
                return new_items[0]

        raise RuntimeError(f'Extraction failed: tried {len(passwords)} password(s), no files produced')

    def _try_extract(self, archive_path, tool, dest_dir, password):
        # Snapshot: filename → mtime before extraction
        before = {
            f: os.path.getmtime(os.path.join(dest_dir, f))
            for f in os.listdir(dest_dir)
        }

        cmd = tool.args_template
        cmd = cmd.replace('{archive}', archive_path)
        cmd = cmd.replace('{dest}', dest_dir)
        if password:
            cmd = cmd.replace('{password}', password)
        else:
            # -p- tells WinRAR "no password" explicitly — prevents GUI password dialog
            cmd = re.sub(r'-p\{password\}', '-p-', cmd)
            cmd = re.sub(r'\{password\}', '', cmd)

        full_cmd = [tool.exe_path] + shlex.split(cmd)
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=600,            # large archives can take several minutes
            stdin=subprocess.DEVNULL,
        )

        # Detect new files OR files that were overwritten (mtime changed)
        after_files = os.listdir(dest_dir)
        new_or_modified = [
            os.path.join(dest_dir, f) for f in after_files
            if f not in before
            or os.path.getmtime(os.path.join(dest_dir, f)) != before[f]
        ]

        if result.returncode != 0 and not new_or_modified:
            return []
        return new_or_modified

    def _condition(self, cur_file, node, adj):
        basename = os.path.basename(cur_file)
        outgoing = adj[node['id']]
        default_target = None
        for label, target_id in outgoing:
            if label in ('default', ''):
                default_target = target_id
                continue
            if label and label in basename:
                return [cur_file], [target_id]
        if default_target:
            return [cur_file], [default_target]
        return [cur_file], ['__end__']

    def _is_file_or_dir(self, cur_file, node, adj):
        route = 'file' if os.path.isfile(cur_file) else 'dir'
        outgoing = adj[node['id']]
        default_target = None
        for label, target_id in outgoing:
            if label in ('default', ''):
                default_target = target_id
                continue
            if label == route:
                return [cur_file], [target_id]
        if default_target:
            return [cur_file], [default_target]
        return [cur_file], ['__end__']

    def _enter_folder(self, cur_file, node, adj):
        if not os.path.isdir(cur_file):
            raise ValueError(f'Not a directory: {cur_file}')
        files = [
            os.path.join(cur_file, f)
            for f in os.listdir(cur_file)
            if os.path.isfile(os.path.join(cur_file, f))
        ]
        if len(files) == 1:
            route, result_file = 'single', files[0]
        elif len(files) > 1:
            route, result_file = 'many', cur_file
        else:
            route, result_file = 'empty', cur_file
        outgoing = adj[node['id']]
        default_target = None
        for label, target_id in outgoing:
            if label in ('default', ''):
                default_target = target_id
                continue
            if label == route:
                return [result_file], [target_id]
        if default_target:
            return [result_file], [default_target]
        return [result_file], ['__end__']
