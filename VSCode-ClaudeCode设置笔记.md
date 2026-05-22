# VS Code Claude Code 扩展设置笔记

## 配置文件路径

```
C:\Users\Administrator\AppData\Roaming\Code\User\settings.json
```

## 修改项

### 1. 跳过权限确认（自动执行操作）

```json
"claudeCode.allowDangerouslySkipPermissions": true
```

### 2. 指定 Python 环境路径

```json
"claudeCode.usePythonEnvironment": "E:\\AiCode\\eaglepy310\\python.exe"
```

## 完整 settings.json 示例

```json
{
    "[python]": {
        "diffEditor.ignoreTrimWhitespace": false,
        "editor.defaultColorDecorators": "never"
    },
    "claudeCode.preferredLocation": "panel",
    "claudeCode.allowDangerouslySkipPermissions": true,
    "claudeCode.usePythonEnvironment": "E:\\AiCode\\eaglepy310\\python.exe"
}
```

## 注意事项

- 路径用双反斜杠 `\\` 或原始字符串
- 修改后需重启 VS Code 生效
- 也可通过 VS Code 设置界面搜索 `claudeCode` 手动勾选

## Python 脚本方式（快速修复）

```python
import json
import os

settings_path = os.path.expandvars(r"%APPDATA\Code\User\settings.json")

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

settings['claudeCode.allowDangerouslySkipPermissions'] = True
settings['claudeCode.usePythonEnvironment'] = r'E:\AiCode\eaglepy310\python.exe'

with open(settings_path, 'w', encoding='utf-8') as f:
    json.dump(settings, f, indent=4, ensure_ascii=False)

print('Done! Restart VS Code.')
```
