# CLAUDE.md — Gemini Image Generator

## 项目概述
基于 Google Gemini API 的 AI 图片生成与编辑 GUI 工具。

## 技术栈
- Python 3.12+ / PySide6 (Qt6) / google-genai / Pillow / cryptography
- PyInstaller 打包为 exe（约 90MB，Qt6 体积大是正常的）

## 文件结构
```
gemini_imggen.py              # 主程序
run_gemini.vbs                # 静默启动（自动探测 Python 路径）
debug_gemini.vbs              # 调试启动（带控制台）
gemini_imggen.spec            # PyInstaller 打包配置
gemini_imggen_20260327.spec   # 旧版打包配置
backups/                      # 版本备份
```

## 功能要点
- 文生图 / 图片编辑 / 多轮对话式创作
- 结构化提示词构建器（主体、场景、动作、风格、光照等）
- API Key 加密存储（Windows DPAPI + Fernet）
- 会话保存/加载（JSON 格式）
- 双模型切换（Nano Banana 2 / Pro）

## 规则
- **每次大改前必须备份到 `backups/`**，命名：`gemini_imggen_{YYYYMMDD}_{HHMMSS}.py`
- **未经用户明确许可，不得擅自重建 exe**
- API Key 相关代码修改需谨慎，涉及加密逻辑

## Approach
- Think before acting. Read existing files before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read unless the file may have changed.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.
