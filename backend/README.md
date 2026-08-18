## Backend

Flask backend for Script Orchestra. Runs on `http://localhost:5001`.

### Python version management (optional, via pyenv)

```bash
brew install pyenv

pyenv install --list | grep 3.13
pyenv install 3.13.5
pyenv global 3.13.5

cd /path/to/project
pyenv local 3.13.5
```

### Virtual environment

```bash
# create
python3 -m venv venv

# activate — macOS / Linux
source venv/bin/activate
# activate — Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# deactivate (any OS)
deactivate
```

### Dependencies

```bash
# install everything (run inside the activated venv)
pip install -r requirements.txt

# regenerate the lock file after adding a dependency
pip freeze > requirements.txt
```

### Run

```bash
python app.py
```

### Code checks

```bash
python -m py_compile your_file.py
python -m compileall .
```

## Lesson Learn

#### send_from_directory vs HTTP

| 方式                    | 访问方式                           | 安全控制            | 性能           | 用途           |
| --------------------- | ------------------------------ | --------------- | ------------ | ------------ |
| `send_from_directory` | Flask route `/files/<filename>`   | 可加认证、权限控制       | 受 Flask 进程限制 | 内部文件下载、受保护资源 |
| HTTP URL              | static URL `https://.../file.jpg` | 需额外机制（签名 URL 等） | 高，可用 CDN     | 公共资源、静态资源    |
