
## Backend


## Intelligent Bank Receipt Claiming and AR Clearing

#### Python version management
```
brew install pyenv

pyenv install --list | grep 3.13
pyenv install 3.13.5

pyenv global 3.13.5

cd /path/to/project
pyenv local 3.13.5
```


#### Venv
python3 -m venv venv
source venv/bin/activate
deactivate

#### Requirment
pip3 install -r requirements.txt
pip3 freeze > requirements.txt


#### code checker
python -m py_compile your_file.py
python -m compileall .


#### for local test - Mysql
```
docker run --name my-mysql \
  -e MYSQL_ROOT_PASSWORD=secret \
  -e MYSQL_DATABASE=mydb \
  -e MYSQL_USER=myuser \
  -e MYSQL_PASSWORD=mypassword \
  -p 3306:3306 \
  -d mysql:latest
```



## Lesson Learn
#### send_from_directory vs HTTP 
| 方式                    | 访问方式                           | 安全控制            | 性能           | 用途           |
| --------------------- | ------------------------------ | --------------- | ------------ | ------------ |
| `send_from_directory` | Flask route `/files/<filename>`   | 可加认证、权限控制       | 受 Flask 进程限制 | 内部文件下载、受保护资源 |
| HTTP URL              | static URL `https://.../file.jpg` | 需额外机制（签名 URL 等） | 高，可用 CDN     | 公共资源、静态资源    |
