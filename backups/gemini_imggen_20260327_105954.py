"""
Gemini 图像生成工具
支持 Nano Banana 2 / Nano Banana Pro
- 加密存储 API Key
- 结构化提示词构建器
- 参考图片上传
- 多风格预设
"""

import os
import sys
import io
import json
import base64
import ctypes
import ctypes.wintypes as wintypes
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

import google.generativeai as _old_genai  # 仅 call_gemini 兼容用
from google import genai
from google.genai import types as genai_types

# ─────────────────────────────────────────────
# 应用根目录（打包为 exe 时取 exe 所在目录，否则取脚本目录）
# ─────────────────────────────────────────────
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

CONFIG_PATH  = APP_DIR / "config.json"
SESSIONS_DIR = APP_DIR / "sessions"
OUTPUT_DIR   = APP_DIR / "output"

# ─────────────────────────────────────────────
# 模型定义
# ─────────────────────────────────────────────
MODELS = {
    "Nano Banana 2 (快速)":  "gemini-3.1-flash-image-preview",
    "Nano Banana Pro (高质)": "gemini-3.1-pro-image-preview",
}

NO_TEXT = (
    "图像中请勿包含任何文字、字母、词语、数字、水印、"
    "标签、说明文字、标志或任何形式的字体排版。"
)

RESOLUTIONS = ["1K", "2K", "4K"]

# ─────────────────────────────────────────────
# 分辨率 / 比例
# ─────────────────────────────────────────────
ASPECT_RATIOS = [
    "1:1  正方形",
    "16:9  横屏宽屏",
    "9:16  竖屏",
    "4:3  标准横",
    "3:4  标准竖",
    "3:2  摄影横",
    "2:3  摄影竖",
    "21:9  超宽屏",
    "4:1  超宽横幅",
    "1:4  超长竖幅",
]

OUTPUT_FORMATS = ["PNG", "JPEG", "WebP"]

# ─────────────────────────────────────────────
# 风格预设库
# ─────────────────────────────────────────────
STYLE_PRESETS = {

    # ── 3D 渲染 ──────────────────────────────
    "3D｜Pixar 动画风格": (
        "皮克斯3D动画风格，圆润光滑表面，角色表情丰富，"
        "温暖三点式工作室灯光，鲜艳饱和色彩，皮肤次表面散射，"
        "浅景深，电影级构图"
    ),
    "3D｜UE5 写实渲染": (
        "虚幻引擎5超写实渲染，全局光照，纳米级几何细节，"
        "光线追踪反射与阴影，体积雾效果，电影级色彩校正，"
        "次世代游戏画质，超高精度纹理细节"
    ),
    "3D｜Blender 简洁风": (
        "Blender渲染，基于物理的材质，柔和区域光源，"
        "简洁干净的几何造型，产品可视化风格，白色工作室环境，"
        "全局照明，细腻环境光遮蔽"
    ),
    "3D｜Cinema 4D 商业级": (
        "Cinema4D渲染，光泽反射材质，商业摄影美感，"
        "渐变工作室背景，完美产品打光，顶级渲染品质，"
        "高对比度，广告级就绪效果"
    ),
    "3D｜迪士尼 3D 卡通": (
        "迪士尼3D动画风格，夸张圆润的比例，大眼睛富有表情，"
        "魔幻温暖的氛围，柔和轮廓光，色彩丰富的奇幻环境，"
        "主角英雄构图，电影画面感"
    ),
    "3D｜低多边形 Low Poly": (
        "低多边形3D艺术，几何面状表面，纯色无纹理着色，"
        "晶体状棱角造型，粉彩或霓虹色调，"
        "等距或透视视角，干净的数字艺术美感"
    ),
    "3D｜KeyShot 产品渲染": (
        "产品级精细渲染，工作室灯光，完美反射表面，"
        "45度旋转台视角，干净白色或渐变背景，"
        "物理精准材质，商业产品摄影效果"
    ),

    # ── 2D 插画 ──────────────────────────────
    "2D｜扁平设计 Flat Design": (
        "扁平化插画设计，几何简约图形，无渐变无阴影，"
        "粗体主色调与辅助色，现代图标风格，"
        "干净矢量美感，设计平台级作品质量"
    ),
    "2D｜水彩手绘": (
        "水彩插画，柔和湿染边缘，可见纸张纹理，"
        "松散富有表现力的笔触，粉彩与暗哑色调，"
        "手绘感，轻盈通透构图，自然流淌的颜色"
    ),
    "2D｜油画质感": (
        "油画风格，厚重可见的堆色笔触，浓郁饱和色彩，"
        "古典构图，温暖的明暗对比光影，"
        "博物馆级精美艺术品，传统油画布纹理"
    ),
    "2D｜钢笔素描": (
        "钢笔素描插画，精细交叉排线，纯黑白色调，"
        "详细的建筑线条风格，手绘美感，"
        "编辑插画风格，图像小说感"
    ),
    "2D｜矢量插画 Vector": (
        "矢量插画，清晰干净的边缘，平面粗体色彩，"
        "现代平面设计风格，可无限缩放的精准图稿，"
        "编辑或信息图表品质，专业图标设计感"
    ),
    "2D｜中国水墨画": (
        "中国传统水墨画，极简构图，"
        "流畅自发的笔墨，刻意留白，"
        "单色墨色层次，宣纸纹理，禅意美学"
    ),
    "2D｜像素艺术 Pixel Art": (
        "经典像素艺术，精灵图比例，"
        "有限调色板，清晰可见的单个像素，"
        "复古游戏角色美感，无抗锯齿"
    ),

    # ── 游戏风格 ─────────────────────────────
    "游戏｜HD-2D 像素风 (八方旅人)": (
        "高清像素混合艺术风格，2D像素角色精灵叠加在3D渲染环境上，"
        "戏剧性浅景深，温暖泛光效果，"
        "前景与背景之间的选择性对焦，"
        "方块游戏级高清2D视觉风格"
    ),
    "游戏｜16位 SNES 像素": (
        "16位像素艺术，超级任天堂时代美感，"
        "每个精灵有限调色板，经典角色扮演游戏地图风格，"
        "复古透视感，复古日式角色扮演游戏风格"
    ),
    "游戏｜8位 FC 像素": (
        "8位像素艺术，任天堂红白机时代，粗大像素块，"
        "每图块3到4色限制，横版卷轴平台跳跃美感，"
        "早期电子游戏魅力，怀旧复古感"
    ),
    "游戏｜等距像素 Isometric": (
        "等距像素艺术，精确菱形网格，"
        "俯视45度角，详细的格子游戏世界，"
        "策略游戏地图美感，干净的等角投影"
    ),
    "游戏｜Chibi 萌系": (
        "Q版超变形风格，头身比例夸张，"
        "圆鼓鼓的脸颊，小小的四肢，大而闪亮的眼睛，"
        "柔和粉彩色调，可爱卡哇伊美感，"
        "手游角色风格"
    ),
    "游戏｜暗黑地牢风": (
        "黑暗地牢探险美感，哥特式恐怖氛围，"
        "冷石头映衬下的摇曳火炬暖光，"
        "粗犷手绘纹理，高对比深邃阴影，"
        "压抑幽闭的画面构图"
    ),
    "游戏｜赛博朋克 Cyberpunk": (
        "赛博朋克美感，霓虹灯映照雨夜城市街道，"
        "全息广告屏幕，金属与霓虹色调，"
        "密集城市垂直层叠，雾霾中透射的体积光柱"
    ),
    "游戏｜魔幻奇幻 Fantasy": (
        "高度奇幻史诗插画，戏剧性魔法氛围，"
        "英雄主角构图，体积魔法粒子特效，"
        "绘画感精细环境，神话般的宏伟感"
    ),
    "游戏｜蒸汽朋克 Steampunk": (
        "蒸汽朋克维多利亚美感，精致黄铜铜质机械齿轮，"
        "蒸汽管道和压力表，土黄与琥珀色调，"
        "煤气灯暖光，工业革命遇见奇幻"
    ),

    # ── 动漫 / 卡通 ──────────────────────────
    "动漫｜日式动漫 Anime": (
        "日本动漫插画风格，干净有力的线条，"
        "大眼睛富有表情，动态动作构图，"
        "赛璐璐着色干净阴影，鲜艳饱和色彩，"
        "顶级动画公司视觉品质"
    ),
    "动漫｜吉卜力 Studio Ghibli": (
        "宫崎骏吉卜力手绘动画风格，"
        "郁郁葱葱详细的自然环境，柔和漫射光线，"
        "怀旧温暖氛围，宫崎骏式人物设计，"
        "背景美术具有令人惊叹的深度和纹理，平静和谐的构图"
    ),
    "动漫｜迪士尼经典卡通": (
        "经典迪士尼2D动画风格，流畅富有表情的角色动态，"
        "干净墨线轮廓，明亮原色调，"
        "黄金时代迪士尼美感，夸张表演感，"
        "绘本插画品质"
    ),
    "动漫｜漫威漫画风": (
        "美式漫画插画风格，粗犷动感的墨线轮廓，"
        "戏剧性网点阴影，动作英雄构图，"
        "高对比原色调，跨页冲击感"
    ),
    "动漫｜韩漫 Webtoon": (
        "韩国条漫风格，干净现代的线条，"
        "全彩柔和渲染，当代时尚与生活方式场景，"
        "竖向滚动构图优化，"
        "柔和浪漫光线，干净白色高光"
    ),

    # ── 写实摄影 ─────────────────────────────
    "摄影｜电影质感 Cinematic": (
        "电影摄影感，变形镜头桶状畸变，"
        "横向镜头光晕，胶片颗粒感，"
        "电影感青橙色彩分级，宽荧幕画幅，"
        "浅景深，大师级打光"
    ),
    "摄影｜商业广告大片": (
        "商业广告摄影，三点式工作室打光，"
        "纯白或渐变无缝背景，"
        "产品锐利对焦，高对比度专业修图，"
        "杂志封面品质，广告就绪效果"
    ),
    "摄影｜时尚大片 Editorial": (
        "高端时尚编辑摄影，戏剧性明暗对比光影，"
        "前卫造型，奢华美感，"
        "顶级时尚杂志品质，艺术总监视角，"
        "大胆图形构图"
    ),
    "摄影｜街头纪实": (
        "街头纪实摄影风格，手持抓拍感，"
        "自然可用光线，决定性瞬间构图，"
        "城市环境背景，原生真实情感，报道摄影美感"
    ),

    # ── 特殊艺术风格 ──────────────────────────
    "艺术｜新艺术 Art Nouveau": (
        "新艺术运动装饰风格，有机流动的自然曲线，"
        "花卉与植物图案，装饰性边框，"
        "穆夏海报风格，淡金与鼠尾草绿调色板，"
        "优雅女性形象，装饰性构图感"
    ),
    "艺术｜包豪斯 Bauhaus": (
        "包豪斯现代主义设计，严格几何基本图形，"
        "仅用红黄蓝黑白色调，"
        "功能优先装饰，网格化构图，"
        "理性极简主义"
    ),
    "艺术｜波普艺术 Pop Art": (
        "波普艺术风格，粗犷加粗黑色轮廓，"
        "平面饱和原色，网点图案，"
        "丝网印刷美感，"
        "高对比度图形冲击力"
    ),
    "艺术｜超现实主义 Surrealism": (
        "超现实主义梦幻场景，不可能的物理并置，"
        "荒诞场景的写实渲染，"
        "达利融化时钟美感，"
        "神秘氛围，超详细不可能建筑"
    ),
    "艺术｜故障艺术 Glitch": (
        "故障艺术美感，色彩通道分离扭曲，"
        "数字损坏伪影，扫描线干扰，"
        "像素位移噪波，磁带追踪错误，"
        "压缩失真块，霓虹赛博朋克色调"
    ),
    "艺术｜复古海报 Retro Poster": (
        "复古老式海报设计，五六十年代广告美感，"
        "限定石版印刷色调，"
        "做旧纸张纹理，粗体字风格，"
        "手绘感，怀旧魅力"
    ),
}

# ─────────────────────────────────────────────
# 加密工具
# ─────────────────────────────────────────────

# ── Windows DPAPI（绑定当前 Windows 用户，自动加解密）──

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

def _dpapi_encrypt(data: bytes) -> bytes:
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    b_in  = _BLOB(len(data), buf)
    b_out = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(b_in), None, None, None, None, 0, ctypes.byref(b_out)):
        raise RuntimeError(f"DPAPI 加密失败: {ctypes.GetLastError()}")
    result = bytes(b_out.pbData[:b_out.cbData])
    ctypes.windll.kernel32.LocalFree(b_out.pbData)
    return result

def _dpapi_decrypt(data: bytes) -> bytes:
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    b_in  = _BLOB(len(data), buf)
    b_out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(b_in), None, None, None, None, 0, ctypes.byref(b_out)):
        raise RuntimeError(f"DPAPI 解密失败: {ctypes.GetLastError()}")
    result = bytes(b_out.pbData[:b_out.cbData])
    ctypes.windll.kernel32.LocalFree(b_out.pbData)
    return result

# ── Fernet（密码保护，用于查看明文 key）──

def _derive_fernet_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def save_api_key(api_key: str, password: str):
    """双重加密保存 API Key：
    - dpapi_key：Windows DPAPI 加密，启动时自动解密，无需密码
    - salt + encrypted_key：Fernet 加密，需要密码才能查看明文
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # DPAPI
    dpapi_blob = _dpapi_encrypt(api_key.encode("utf-8"))
    # Fernet
    salt = os.urandom(16)
    fernet = Fernet(_derive_fernet_key(password, salt))
    fernet_blob = fernet.encrypt(api_key.encode("utf-8"))
    data = {
        "dpapi_key":    base64.b64encode(dpapi_blob).decode("utf-8"),
        "salt":         salt.hex(),
        "encrypted_key": fernet_blob.decode("utf-8"),
    }
    CONFIG_PATH.write_text(json.dumps(data), encoding="utf-8")


def load_api_key_auto() -> str | None:
    """用 DPAPI 自动加载 API Key，无需密码"""
    if not CONFIG_PATH.exists():
        return None
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    try:
        blob = base64.b64decode(data["dpapi_key"])
        return _dpapi_decrypt(blob).decode("utf-8")
    except Exception:
        return None


def load_api_key_with_password(password: str) -> str | None:
    """用密码解密 API Key（仅用于查看明文），密码错误返回 None"""
    if not CONFIG_PATH.exists():
        return None
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    salt = bytes.fromhex(data["salt"])
    fernet = Fernet(_derive_fernet_key(password, salt))
    try:
        return fernet.decrypt(data["encrypted_key"].encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def has_saved_key() -> bool:
    return CONFIG_PATH.exists()


# ─────────────────────────────────────────────
# 会话记录
# ─────────────────────────────────────────────

def save_session(turns: list, meta: dict) -> Path:
    """
    turns: [{"role":"user"|"ai", "text":str|None, "img_bytes":bytes|None}, ...]
    meta:  {"model":str, "style_key":str, "ratio":str, "fmt":str, ...}
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts = meta.get("timestamp") or datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_turns = []
    img_counter = 0
    for turn in turns:
        st = {"role": turn["role"]}
        if turn.get("text"):
            st["text"] = turn["text"]
        if turn.get("img_bytes"):
            img_name = f"{ts}_{img_counter}.png"
            Image.open(io.BytesIO(turn["img_bytes"])).save(
                SESSIONS_DIR / img_name, format="PNG")
            st["image_file"] = img_name
            img_counter += 1
        saved_turns.append(st)
    session = {"timestamp": ts, "turns": saved_turns,
               **{k: v for k, v in meta.items() if k != "timestamp"}}
    json_path = SESSIONS_DIR / f"{ts}.json"
    json_path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def list_sessions() -> list[dict]:
    """返回所有对话会话，按时间倒序"""
    if not SESSIONS_DIR.exists():
        return []
    sessions = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["_json_path"] = str(p)
            # 找第一张 AI 图片用于预览
            data["image_path"] = None
            for turn in data.get("turns", []):
                if turn.get("image_file"):
                    data["image_path"] = str(SESSIONS_DIR / turn["image_file"])
                    break
            # 兼容旧格式
            if data["image_path"] is None and data.get("image_file"):
                data["image_path"] = str(SESSIONS_DIR / data["image_file"])
            sessions.append(data)
        except Exception:
            pass
    return sessions


def load_session(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


# ─────────────────────────────────────────────
# Gemini API 调用
# ─────────────────────────────────────────────

def build_prompt(subject: str, location: str, action: str,
                 style_desc: str, extra: str) -> str:
    parts = []
    if subject:
        parts.append(subject)
    if action:
        parts.append(action)
    if location:
        parts.append(f"in {location}")
    base = ", ".join(parts) if parts else ""
    prompt = f"{base}. {style_desc}" if base else style_desc
    if extra:
        prompt += f". {extra}"
    return prompt.strip()


EXT_MIME = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def call_gemini(api_key: str, prompt: str, model_name: str,
                ref_images: list[dict] | None = None) -> bytes | None:
    """
    ref_images: [{"path": str, "type": str}, ...]
    type 用于在 prompt 里说明该图的用途
    """
    _old_genai.configure(api_key=api_key)
    model = _old_genai.GenerativeModel(model_name)
    content = []

    if ref_images:
        type_labels = {
            "主体 / 角色一致性": "subject/character consistency reference",
            "风格参考":          "style reference",
            "场景 / 环境参考":   "scene/environment reference",
            "通用参考":          "general reference",
        }
        for ref in ref_images:
            path = ref["path"]
            ref_type = ref.get("type", "通用参考")
            ext = Path(path).suffix.lower()
            mime = EXT_MIME.get(ext, "image/jpeg")
            with open(path, "rb") as f:
                img_data = f.read()
            content.append({
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(img_data).decode("utf-8"),
                }
            })
            content.append(f"[{type_labels.get(ref_type, 'reference')}]")
        content.append(f"Using the above reference images, generate: {prompt}")
    else:
        content.append(prompt)

    response = model.generate_content(content)
    for part in response.parts:
        if part.inline_data:
            return part.inline_data.data   # 已是原始字节，无需 base64 解码
    return None


# ─────────────────────────────────────────────
# GUI：登录 / 设置 API Key
# ─────────────────────────────────────────────

class AuthDialog(tk.Toplevel):
    """首次设置 API Key 对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("首次设置 API Key")
        self.resizable(False, False)
        self.grab_set()
        self.result_key: str | None = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build(self):
        f = ttk.Frame(self, padding=20)
        f.pack()
        ttk.Label(f, text="Gemini API Key：").grid(row=0, column=0, sticky="e", pady=4)
        self._key_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._key_var, width=46, show="*").grid(row=0, column=1, pady=4)

        ttk.Label(f, text="设置密码（用于查看 Key）：").grid(row=1, column=0, sticky="e", pady=4)
        self._pw_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw_var, width=46, show="*").grid(row=1, column=1, pady=4)

        ttk.Label(f, text="确认密码：").grid(row=2, column=0, sticky="e", pady=4)
        self._pw2_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw2_var, width=46, show="*").grid(row=2, column=1, pady=4)

        ttk.Label(f, text="密码仅在查看/修改 Key 时需要，\n日常使用自动解锁。",
                  foreground="gray").grid(row=3, column=0, columnspan=2, pady=4)

        ttk.Button(f, text="保存并进入", command=self._confirm).grid(
            row=4, column=0, columnspan=2, pady=(8, 0))

    def _confirm(self):
        key = self._key_var.get().strip()
        pw  = self._pw_var.get().strip()
        pw2 = self._pw2_var.get().strip()
        if not key:
            messagebox.showwarning("提示", "API Key 不能为空", parent=self); return
        if not pw:
            messagebox.showwarning("提示", "密码不能为空", parent=self); return
        if pw != pw2:
            messagebox.showwarning("提示", "两次密码不一致", parent=self); return
        save_api_key(key, pw)
        self.result_key = key
        self.destroy()


# ─────────────────────────────────────────────
# GUI：主界面
# ─────────────────────────────────────────────

class _PasswordDialog(tk.Toplevel):
    """输入密码以验证身份"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("验证密码")
        self.resizable(False, False)
        self.grab_set()
        self.result_password: str | None = None
        f = ttk.Frame(self, padding=16)
        f.pack()
        ttk.Label(f, text="请输入密码以查看 API Key：").pack(anchor="w", pady=(0, 6))
        self._pw = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw, show="*", width=36).pack()
        ttk.Button(f, text="确认", command=self._ok).pack(pady=(10, 0))
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _ok(self):
        pw = self._pw.get().strip()
        if pw:
            self.result_password = pw
        self.destroy()


class _EditKeyDialog(tk.Toplevel):
    """显示并修改 API Key（密码验证通过后才打开）"""
    def __init__(self, parent, current_key: str):
        super().__init__(parent)
        self.title("查看 / 修改 API Key")
        self.resizable(False, False)
        self.grab_set()
        self.result: tuple | None = None   # (new_key, new_password)
        f = ttk.Frame(self, padding=16)
        f.pack()
        ttk.Label(f, text="API Key：").grid(row=0, column=0, sticky="e", pady=4)
        self._key = tk.StringVar(value=current_key)
        ttk.Entry(f, textvariable=self._key, width=48).grid(row=0, column=1, pady=4)
        ttk.Label(f, text="新密码（留空则保持原密码不变）：").grid(row=1, column=0, sticky="e", pady=4)
        self._pw = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw, show="*", width=48).grid(row=1, column=1, pady=4)
        ttk.Label(f, text="确认新密码：").grid(row=2, column=0, sticky="e", pady=4)
        self._pw2 = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw2, show="*", width=48).grid(row=2, column=1, pady=4)
        ttk.Button(f, text="保存", command=self._save).grid(row=3, column=0, columnspan=2, pady=(10, 0))
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _save(self):
        key = self._key.get().strip()
        pw  = self._pw.get().strip()
        pw2 = self._pw2.get().strip()
        if not key:
            messagebox.showwarning("提示", "API Key 不能为空", parent=self); return
        if pw and pw != pw2:
            messagebox.showwarning("提示", "两次密码不一致", parent=self); return
        # 如果不填新密码，传空字符串，调用方自行判断是否需要重新 save
        self.result = (key, pw)
        self.destroy()


class _HistoryDialog(tk.Toplevel):
    """历史会话浏览器"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("历史记录")
        self.geometry("720x480")
        self.grab_set()
        self.result: dict | None = None
        self._sessions = list_sessions()
        self._thumb_cache: dict[str, ImageTk.PhotoImage] = {}
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build(self):
        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # 左：会话列表
        left = ttk.Frame(main, width=340)
        main.add(left, weight=1)
        ttk.Label(left, text=f"共 {len(self._sessions)} 条记录").pack(anchor="w")
        self._tree = ttk.Treeview(left, columns=("time", "prompt"), show="headings")
        self._tree.heading("time",   text="时间")
        self._tree.heading("prompt", text="提示词摘要")
        self._tree.column("time",   width=130, anchor="w")
        self._tree.column("prompt", width=200, anchor="w")
        sb = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for s in self._sessions:
            ts = s.get("timestamp", "")
            turns = s.get("turns", [])
            first_user = next((t for t in turns if t.get("role") == "user"), None)
            subj = (first_user.get("text") if first_user else None) \
                   or s.get("prompt") or s.get("style_key") or "（无标题）"
            img_count = sum(1 for t in turns if t.get("image_file"))
            label = f"{subj[:30]}  [{img_count}图]" if img_count else subj[:40]
            self._tree.insert("", "end", iid=s["_json_path"],
                              values=(ts, label))
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # 右：预览
        right = ttk.Frame(main, width=340)
        main.add(right, weight=1)
        self._preview_img  = ttk.Label(right, text="选择一条记录预览", anchor="center")
        self._preview_img.pack(fill="both", expand=True)
        self._preview_info = tk.Text(right, height=5, state="disabled",
                                     wrap="word", font=("Consolas", 9))
        self._preview_info.pack(fill="x", pady=(4, 0))

        ttk.Button(self, text="加载此会话", command=self._load).pack(pady=(0, 8))

    def _on_select(self, _=None):
        sel = self._tree.selection()
        if not sel:
            return
        json_path = sel[0]
        s = next((x for x in self._sessions if x["_json_path"] == json_path), None)
        if not s:
            return
        # 图片预览
        img_path = s.get("image_path")
        if img_path and Path(img_path).exists():
            if img_path not in self._thumb_cache:
                img = Image.open(img_path)
                img.thumbnail((300, 300))
                self._thumb_cache[img_path] = ImageTk.PhotoImage(img)
            self._preview_img.configure(image=self._thumb_cache[img_path], text="")
        else:
            self._preview_img.configure(image="", text="无图片")
        # 信息预览
        turns = s.get("turns", [])
        user_turns = [t for t in turns if t.get("role") == "user"]
        ai_turns   = [t for t in turns if t.get("role") == "ai"]
        first_prompt = user_turns[0].get("text", "") if user_turns else s.get("prompt", "")
        info = (
            f"时间:    {s.get('timestamp', '')}\n"
            f"模型:    {s.get('model', '')}\n"
            f"轮次:    {len(user_turns)} 问 / {len(ai_turns)} 答\n"
            f"首条:    {first_prompt[:60]}\n"
            f"风格:    {s.get('style_key', '')}\n"
            f"分辨率:  {s.get('resolution', '')}  比例: {s.get('ratio', '')}"
        )
        self._preview_info.configure(state="normal")
        self._preview_info.delete("1.0", "end")
        self._preview_info.insert("1.0", info)
        self._preview_info.configure(state="disabled")

    def _load(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一条记录", parent=self)
            return
        json_path = sel[0]
        s = next((x for x in self._sessions if x["_json_path"] == json_path), None)
        if s:
            self.result = s
        self.destroy()


class _RefTypeDialog(tk.Toplevel):
    """选择参考图类型的小对话框"""
    def __init__(self, parent, types: list[str]):
        super().__init__(parent)
        self.title("选择参考类型")
        self.resizable(False, False)
        self.grab_set()
        self.result: str | None = None
        f = ttk.Frame(self, padding=16)
        f.pack()
        ttk.Label(f, text="这批图片的参考用途：").pack(anchor="w", pady=(0, 6))
        self._var = tk.StringVar(value=types[0])
        for t in types:
            ttk.Radiobutton(f, text=t, variable=self._var, value=t).pack(anchor="w", pady=2)
        ttk.Button(f, text="确定", command=self._ok).pack(pady=(10, 0))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _ok(self):
        self.result = self._var.get()
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gemini 图像生成工具")
        self.resizable(True, True)
        self.geometry("980x700")
        self.minsize(780, 560)
        self._api_key: str | None = None
        self._ref_images: list[dict] = []
        self._last_image_bytes: bytes | None = None
        self._chat_session = None          # Gemini ChatSession（多轮）
        self._chat_image_refs: list = []   # 防止 PhotoImage 被 GC
        self._current_turns: list[dict] = []   # 当前对话所有轮次
        self._session_ts: str = ""             # 当前会话时间戳
        self._prompt_history: list[str] = []   # 已发送的提示词历史
        self._history_idx: int = -1            # 当前浏览位置，-1 = 新输入
        self._saved_input: str = ""            # 浏览历史时暂存当前未发送的内容

        self._build()
        self.after(100, self._authenticate)

    # ── 认证流程 ──────────────────────────────
    def _authenticate(self):
        if has_saved_key():
            # 已有保存的 key，DPAPI 自动解密，无需密码
            key = load_api_key_auto()
            if key:
                self._api_key = key
                self._log("API Key 已自动加载，就绪", "ok")
                self._status("就绪")
                self._restore_last_session()
                return
            # DPAPI 失败（换了 Windows 用户等），回退到首次设置
            self._log("DPAPI 自动解密失败，请重新输入 API Key", "warn")

        # 首次设置
        dlg = AuthDialog(self)
        self.wait_window(dlg)
        if dlg.result_key:
            self._api_key = dlg.result_key
            self._status("已设置，可以开始生成图片")
            self._log("API Key 设置成功，就绪", "ok")
            self._restore_last_session()
        else:
            self.destroy()

    # ── 界面构建 ──────────────────────────────
    def _build(self):
        self._build_menu()
        # 使用 tk.PanedWindow（非 ttk）：add() 的 width 参数直接控制初始宽度
        main = tk.PanedWindow(self, orient="horizontal",
                              sashwidth=5, sashpad=1,
                              sashrelief="flat", background="#c0c0c0")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        left  = ttk.Frame(main)
        right = ttk.Frame(main)
        # width=374 ≈ 980 × 0.382；右侧拿走剩余全部空间
        main.add(left,  width=374, minsize=240, stretch="never")
        main.add(right, minsize=360, stretch="always")

        self._build_left(left)
        self._build_right(right)

        # 状态栏
        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self._status_var, anchor="w",
                  relief="sunken").pack(fill="x", side="bottom")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self):
        menubar = tk.Menu(self)
        setting_menu = tk.Menu(menubar, tearoff=0)
        setting_menu.add_command(label="修改 API Key", command=self._change_key)
        menubar.add_cascade(label="设置", menu=setting_menu)
        menubar.add_command(label="历史记录", command=self._open_history)
        self.config(menu=menubar)

    # ── 左侧：参考图 + 风格 + 参数 + 日志 ─────
    def _build_left(self, parent):
        # 上下黄金比例分割：控件区 0.618 / 日志区 0.382
        vpane = ttk.PanedWindow(parent, orient="vertical")
        vpane.pack(fill="both", expand=True)

        ctrl = ttk.Frame(vpane)
        vpane.add(ctrl, weight=618)

        log_frame = ttk.LabelFrame(vpane, text="运行日志", padding=4)
        vpane.add(log_frame, weight=382)

        # ── 参考图片 ──
        ref_frame = ttk.LabelFrame(ctrl, text="参考图片（可选，最多 14 张）", padding=6)
        ref_frame.pack(fill="x", padx=4, pady=(4, 2))
        tree_frame = ttk.Frame(ref_frame)
        tree_frame.pack(fill="x")
        self._ref_tree = ttk.Treeview(tree_frame, columns=("type", "file"),
                                       show="headings", height=5)
        self._ref_tree.heading("type", text="参考类型")
        self._ref_tree.heading("file", text="文件名")
        self._ref_tree.column("type", width=100, anchor="w")
        self._ref_tree.column("file", width=150, anchor="w")
        sb_ref = ttk.Scrollbar(tree_frame, command=self._ref_tree.yview)
        self._ref_tree.configure(yscrollcommand=sb_ref.set)
        self._ref_tree.pack(side="left", fill="x", expand=True)
        sb_ref.pack(side="right", fill="y")
        btn_ref = ttk.Frame(ref_frame)
        btn_ref.pack(fill="x", pady=(3, 0))
        self._ref_count_var = tk.StringVar(value="0 / 14")
        ttk.Label(btn_ref, textvariable=self._ref_count_var).pack(side="left")
        ttk.Button(btn_ref, text="添加",   command=self._add_ref_image).pack(side="right", padx=2)
        ttk.Button(btn_ref, text="删除选中", command=self._remove_ref_image).pack(side="right", padx=2)
        ttk.Button(btn_ref, text="清空",   command=self._clear_ref).pack(side="right", padx=2)

        # ── 画面风格 ──
        style_frame = ttk.LabelFrame(ctrl, text="画面风格", padding=6)
        style_frame.pack(fill="x", padx=4, pady=2)
        self._style_var = tk.StringVar(value="(无风格)")
        style_values = ["(无风格)"] + list(STYLE_PRESETS.keys())
        ttk.Combobox(style_frame, textvariable=self._style_var,
                     values=style_values, state="readonly", width=34).pack(fill="x")
        self._style_label = ttk.Label(style_frame, text="不附加任何风格提示词",
                                      foreground="gray", wraplength=280, justify="left")
        self._style_label.pack(anchor="w", pady=(3, 0))
        self._style_var.trace_add("write", self._on_style_change)

        # ── 生成参数 ──
        param_frame = ttk.LabelFrame(ctrl, text="生成参数", padding=6)
        param_frame.pack(fill="x", padx=4, pady=2)
        params = [
            ("模型",     "_model_var",  list(MODELS.keys())),
            ("分辨率",   "_res_var",    RESOLUTIONS),
            ("比例",     "_ratio_var",  ASPECT_RATIOS),
            ("格式",     "_format_var", OUTPUT_FORMATS),
            ("生成数量", "_count_var",  ["1 张", "2 张", "3 张", "4 张"]),
        ]
        for i, (label, attr, values) in enumerate(params):
            ttk.Label(param_frame, text=label + "：").grid(
                row=i, column=0, sticky="e", pady=2, padx=4)
            var = tk.StringVar(value=values[0])
            setattr(self, attr, var)
            ttk.Combobox(param_frame, textvariable=var, values=values,
                         state="readonly", width=24).grid(
                row=i, column=1, sticky="ew", pady=2)
        param_frame.columnconfigure(1, weight=1)

        # ── 日志文本 ──
        self._log_text = tk.Text(log_frame, state="disabled", wrap="word",
                                 background="#1e1e1e", foreground="#d4d4d4",
                                 font=("Consolas", 11))
        sb_log = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb_log.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        sb_log.pack(side="right", fill="y")
        self._log_text.tag_configure("info",  foreground="#9cdcfe")
        self._log_text.tag_configure("ok",    foreground="#4ec9b0")
        self._log_text.tag_configure("warn",  foreground="#dcdcaa")
        self._log_text.tag_configure("error", foreground="#f48771")
        self._log_text.tag_configure("time",  foreground="#6a9955")

    # ── 右侧：对话界面 ────────────────────────
    def _build_right(self, parent):
        # 进度条（固定在最上方）
        self._progress = ttk.Progressbar(parent, mode="indeterminate")
        self._progress.pack(fill="x", padx=4, pady=(4, 2))

        # 底部按钮行（固定）
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill="x", padx=4, pady=(2, 4), side="bottom")
        ttk.Button(btn_row, text="保存最新图片",
                   command=self._save_image).pack(side="right")
        ttk.Button(btn_row, text="新对话", width=8,
                   command=self._new_chat).pack(side="right", padx=(0, 4))
        self._send_btn = ttk.Button(btn_row, text="发送 (Enter)", width=12,
                                    command=self._send_message)
        self._send_btn.pack(side="right", padx=(0, 4))

        # 可拖拽垂直分割：上方对话历史 / 下方输入区
        vpane = ttk.PanedWindow(parent, orient="vertical")
        vpane.pack(fill="both", expand=True, padx=4, pady=(0, 2))

        # ── 上方：对话历史 ──
        chat_frame = ttk.LabelFrame(vpane, text="对话", padding=4)
        vpane.add(chat_frame, weight=618)   # 0.618 黄金比例

        self._chat_text = tk.Text(chat_frame, state="disabled", wrap="word",
                                  background="#fafafa", cursor="arrow")
        sb_chat = ttk.Scrollbar(chat_frame, command=self._chat_text.yview)
        self._chat_text.configure(yscrollcommand=sb_chat.set)
        self._chat_text.pack(side="left", fill="both", expand=True)
        sb_chat.pack(side="right", fill="y")
        # 对话气泡标签
        self._chat_text.tag_configure("user_name", foreground="#0078d4", font=("", 9, "bold"))
        self._chat_text.tag_configure("user_msg",  foreground="#1a1a1a", lmargin1=16, lmargin2=16)
        self._chat_text.tag_configure("ai_name",   foreground="#107c10", font=("", 9, "bold"))
        self._chat_text.tag_configure("ai_msg",    foreground="#555",    lmargin1=16, lmargin2=16)
        self._chat_text.tag_configure("divider",   foreground="#ccc")
        self._chat_text.tag_configure("img_hint",  foreground="#999", font=("", 8))

        # ── 下方：输入区（可拉伸）──
        input_frame = ttk.LabelFrame(vpane, text="输入（Enter 发送，Shift+Enter 换行）", padding=4)
        vpane.add(input_frame, weight=382)  # 0.382 黄金比例

        self._input_text = tk.Text(input_frame, wrap="word", font=("", 10))
        sb_input = ttk.Scrollbar(input_frame, command=self._input_text.yview)
        self._input_text.configure(yscrollcommand=sb_input.set)
        self._input_text.pack(side="left", fill="both", expand=True)
        sb_input.pack(side="right", fill="y")
        self._input_text.bind("<Return>",       self._on_enter)
        self._input_text.bind("<Shift-Return>", lambda e: None)
        self._input_text.bind("<Up>",           self._on_history_up)
        self._input_text.bind("<Down>",         self._on_history_down)

    # ── 事件处理 ──────────────────────────────
    def _on_style_change(self, *_):
        key = self._style_var.get()
        if key and key != "(无风格)":
            preview = STYLE_PRESETS.get(key, "")
            self._style_label.configure(
                text=preview[:80] + ("..." if len(preview) > 80 else ""),
                foreground="#555")
        else:
            self._style_label.configure(text="不附加任何风格提示词", foreground="gray")

    def _on_enter(self, event):
        """Enter 发送；Shift+Enter 换行"""
        if event.state & 0x1:   # Shift 按住 → 换行
            return
        self._send_message()
        return "break"

    def _on_history_up(self, event):
        """↑ 键：仅在光标处于第一行时向前翻历史（同终端行为）"""
        if not self._prompt_history:
            return
        cursor_line = int(self._input_text.index("insert").split(".")[0])
        if cursor_line > 1:
            return  # 多行文本内正常上移，不拦截
        # 第一次按 ↑：暂存当前未发送内容
        if self._history_idx == -1:
            self._saved_input = self._input_text.get("1.0", "end-1c")
            self._history_idx = len(self._prompt_history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        self._input_text.delete("1.0", "end")
        self._input_text.insert("1.0", self._prompt_history[self._history_idx])
        self._input_text.mark_set("insert", "end")
        return "break"

    def _on_history_down(self, event):
        """↓ 键：仅在光标处于最后一行时向后翻历史，到底时恢复暂存内容"""
        if self._history_idx == -1:
            return  # 已在最新位置，正常下移
        last_line = int(self._input_text.index("end-1c").split(".")[0])
        cursor_line = int(self._input_text.index("insert").split(".")[0])
        if cursor_line < last_line:
            return  # 多行文本内正常下移，不拦截
        self._history_idx += 1
        if self._history_idx >= len(self._prompt_history):
            self._history_idx = -1
            self._input_text.delete("1.0", "end")
            if self._saved_input:
                self._input_text.insert("1.0", self._saved_input)
        else:
            self._input_text.delete("1.0", "end")
            self._input_text.insert("1.0", self._prompt_history[self._history_idx])
        self._input_text.mark_set("insert", "end")
        return "break"

    def _send_message(self):
        if not self._api_key:
            messagebox.showwarning("未解锁", "请先完成 API Key 设置", parent=self)
            return
        user_text = self._input_text.get("1.0", "end").strip()
        if not user_text:
            return
        self._input_text.delete("1.0", "end")
        # 存入历史（去重：与最后一条相同则跳过）
        if not self._prompt_history or self._prompt_history[-1] != user_text:
            self._prompt_history.append(user_text)
        self._history_idx  = -1
        self._saved_input  = ""

        # 完整 prompt = 用户文本 + 风格（静默）+ 比例/分辨率提示 + NO_TEXT
        style_key  = self._style_var.get()
        if style_key == "(无风格)":
            style_key = ""
        style_desc = STYLE_PRESETS.get(style_key, "") if style_key else ""
        full_prompt = user_text
        if style_desc:
            full_prompt += f"\n\n风格要求：{style_desc}"
        ratio_text = self._ratio_var.get().split()[0]
        res_text   = self._res_var.get().split()[0]          # "1K" "2K" "4K"
        full_prompt += f"\n\n{NO_TEXT}"

        model_key  = self._model_var.get()
        model_name = MODELS[model_key]
        count      = int(self._count_var.get().split()[0])

        # 初始化会话时间戳
        if not self._session_ts:
            self._session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 记录用户轮次
        self._current_turns.append({"role": "user", "text": user_text,
                                    "img_bytes": None})

        self._append_user_msg(user_text)
        self._send_btn.configure(state="disabled")
        self._progress.start(12)
        self._status(f"正在生成，共 {count} 张，请稍候...")
        self._log(f"模型: {model_key}", "info")
        self._log(f"提示词: {user_text[:80]}{'...' if len(user_text) > 80 else ''}", "info")
        if style_key:
            self._log(f"风格: {style_key}（静默附加）", "info")
        self._log(f"比例: {ratio_text}  分辨率: {res_text}  数量: {count} 张", "info")
        if self._ref_images:
            self._log(f"参考图: {len(self._ref_images)} 张", "info")
        self._log("正在连接 Gemini API...", "warn")

        threading.Thread(
            target=self._run_chat,
            args=(full_prompt, model_name, list(self._ref_images), user_text, count,
                  ratio_text, res_text),
            daemon=True
        ).start()

    def _new_chat(self):
        # 若当前有对话，自动保存
        if self._current_turns:
            try:
                meta = self._capture_state()
                meta["timestamp"] = self._session_ts
                save_session(self._current_turns, meta)
                self._log("对话已自动保存", "ok")
            except Exception as e:
                self._log(f"自动保存失败: {e}", "warn")

        self._chat_session = None
        self._chat_image_refs.clear()
        self._current_turns.clear()
        self._session_ts = ""
        self._last_image_bytes = None
        self._chat_text.configure(state="normal")
        self._chat_text.delete("1.0", "end")
        self._chat_text.configure(state="disabled")
        self._log("已开始新对话", "info")
        self._status("新对话已开始")

    def _append_user_msg(self, text: str):
        self._chat_text.configure(state="normal")
        self._chat_text.insert("end", "你：\n", "user_name")
        self._chat_text.insert("end", text + "\n\n", "user_msg")
        self._chat_text.see("end")
        self._chat_text.configure(state="disabled")

    def _append_ai_response(self, text: str | None, img_bytes: bytes | None):
        self._chat_text.configure(state="normal")
        self._chat_text.insert("end", "Gemini：\n", "ai_name")
        if text:
            self._chat_text.insert("end", text + "\n", "ai_msg")
        if img_bytes:
            try:
                img = Image.open(io.BytesIO(img_bytes))
                display = img.copy()
                display.thumbnail((480, 480))
                photo = ImageTk.PhotoImage(display)
                self._chat_image_refs.append(photo)

                # 用 Label 嵌入图片（Label 原生支持 cursor / 鼠标事件）
                img_lbl = tk.Label(self._chat_text, image=photo,
                                   background="#fafafa", cursor="hand2",
                                   relief="flat", borderwidth=0)
                img_lbl.bind("<Button-1>",
                             lambda e, b=img_bytes: self._preview_image(b))
                img_lbl.bind("<Button-3>",
                             lambda e, b=img_bytes: self._show_img_menu(e, b))
                self._chat_text.window_create("end", window=img_lbl)
                self._chat_text.insert("end", "  单击预览，右键菜单\n", "img_hint")
            except Exception as e:
                self._chat_text.insert("end", f"[图片显示失败: {e}]\n", "ai_msg")
        self._chat_text.insert("end", "─" * 40 + "\n", "divider")
        self._chat_text.see("end")
        self._chat_text.configure(state="disabled")

    REF_TYPES = [
        "主体 / 角色一致性",
        "风格参考",
        "场景 / 环境参考",
        "通用参考",
    ]
    MAX_REF_IMAGES = 14
    REF_EXTS = [
        ("图片文件", "*.png *.jpg *.jpeg *.webp *.heic *.heif"),
        ("PNG",  "*.png"),
        ("JPEG", "*.jpg *.jpeg"),
        ("WebP", "*.webp"),
        ("HEIC / HEIF", "*.heic *.heif"),
    ]
    EXT_MIME = {
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }

    def _add_ref_image(self):
        if len(self._ref_images) >= self.MAX_REF_IMAGES:
            messagebox.showwarning("已达上限", f"最多只能添加 {self.MAX_REF_IMAGES} 张参考图", parent=self)
            return

        # 选文件
        paths = filedialog.askopenfilenames(
            title="选择参考图片（可多选）",
            filetypes=self.REF_EXTS,
            parent=self,
        )
        if not paths:
            return

        # 选类型
        type_dlg = _RefTypeDialog(self, self.REF_TYPES)
        self.wait_window(type_dlg)
        if not type_dlg.result:
            return
        ref_type = type_dlg.result

        added = 0
        for path in paths:
            if len(self._ref_images) >= self.MAX_REF_IMAGES:
                messagebox.showwarning("已达上限",
                    f"已添加至上限 {self.MAX_REF_IMAGES} 张，剩余文件未添加", parent=self)
                break
            self._ref_images.append({"path": path, "type": ref_type})
            self._ref_tree.insert("", "end",
                                  values=(ref_type, Path(path).name))
            added += 1

        self._ref_count_var.set(f"{len(self._ref_images)} / {self.MAX_REF_IMAGES}")
        self._log(f"已添加 {added} 张参考图（{ref_type}）", "info")

    def _remove_ref_image(self):
        selected = self._ref_tree.selection()
        if not selected:
            return
        for item in selected:
            idx = self._ref_tree.index(item)
            self._ref_tree.delete(item)
            if idx < len(self._ref_images):
                self._ref_images.pop(idx)
        self._ref_count_var.set(f"{len(self._ref_images)} / {self.MAX_REF_IMAGES}")

    def _clear_ref(self):
        self._ref_images.clear()
        for item in self._ref_tree.get_children():
            self._ref_tree.delete(item)
        self._ref_count_var.set(f"0 / {self.MAX_REF_IMAGES}")

    def _run_chat(self, full_prompt: str, model_name: str,
                 ref_images: list, user_text: str, count: int = 1,
                 ratio_text: str = "1:1", res_text: str = "1K"):
        def log(msg, level="info"):
            self.after(0, self._log, msg, level)
        try:
            log("已发送请求，等待模型响应...", "warn")

            # 新 SDK：构建 image_config（原生分辨率 + 比例）
            # 4K 超出 API 支持范围，API 层用 2K，后续由 _on_one_image 再放大
            api_size = {"1K": "1K", "2K": "2K", "4K": "2K"}.get(res_text, "1K")
            img_cfg = genai_types.ImageConfig(
                image_size=api_size,
                aspect_ratio=ratio_text,
            )
            gen_cfg = genai_types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=img_cfg,
            )

            if self._chat_session is None:
                client = genai.Client(api_key=self._api_key)
                self._chat_session = client.chats.create(
                    model=model_name, config=gen_cfg)

            # 构建消息内容
            content: list = []
            if ref_images:
                type_labels = {
                    "主体 / 角色一致性": "主体/角色一致性参考图",
                    "风格参考":          "风格参考图",
                    "场景 / 环境参考":   "场景/环境参考图",
                    "通用参考":          "通用参考图",
                }
                for ref in ref_images:
                    path = ref["path"]
                    ext  = Path(path).suffix.lower()
                    mime = self.EXT_MIME.get(ext, "image/jpeg")
                    with open(path, "rb") as f:
                        img_data = f.read()
                    content.append(
                        genai_types.Part.from_bytes(data=img_data, mime_type=mime))
                    content.append(f"[{type_labels.get(ref['type'], '通用参考图')}]")
                content.append(f"请根据以上参考图生成：{full_prompt}")
            else:
                content.append(full_prompt)

            for idx in range(count):
                if count > 1:
                    log(f"正在生成第 {idx + 1}/{count} 张...", "warn")

                if idx == 0:
                    response = self._chat_session.send_message(content)
                else:
                    follow = f"请再生成一张，风格主题与上面相同。{NO_TEXT}"
                    response = self._chat_session.send_message(follow)

                log(f"收到第 {idx + 1} 张响应，正在解析...", "warn")

                img_bytes = None
                response_text = None
                parts = response.candidates[0].content.parts if response.candidates else []
                for i, part in enumerate(parts):
                    if part.inline_data:
                        mime = part.inline_data.mime_type
                        size = len(part.inline_data.data)
                        log(f"  Part[{i}]: inline_data  mime={mime}  size={size} bytes", "info")
                        if img_bytes is None:
                            img_bytes = part.inline_data.data
                    elif part.text:
                        log(f"  Part[{i}]: text → {part.text[:120]}", "info")
                        response_text = part.text
                    else:
                        log(f"  Part[{i}]: 未知类型 {part}", "warn")

                if img_bytes is None:
                    try:
                        fb = response.prompt_feedback
                        if fb:
                            log(f"  prompt_feedback: {fb}", "error")
                    except Exception:
                        pass

                is_last = (idx == count - 1)
                self.after(0, self._on_one_image,
                           img_bytes, response_text, None, user_text, idx + 1, count, is_last)

        except Exception as e:
            self.after(0, self._on_one_image, None, None, str(e), user_text, -1, count, True)

    def _on_one_image(self, img_bytes: bytes | None, text: str | None,
                      error: str | None, user_text: str,
                      index: int, total: int, is_last: bool):
        if is_last or error:
            self._progress.stop()
            self._send_btn.configure(state="normal")

        if error:
            self._log(f"生成失败: {error}", "error")
            self._status(f"生成失败：{error}")
            self._append_ai_response(f"[错误] {error}", None)
            return
        if not img_bytes and not text:
            self._log(f"第 {index}/{total} 张未返回图像数据，可能原因：", "error")
            self._log("  · 当前模型不支持图像输出", "error")
            self._log("  · API Key 无图像生成权限", "error")
            self._status("未返回图像数据")
            self._append_ai_response("[未返回图像数据]", None)
            return
        if img_bytes:
            try:
                img = Image.open(io.BytesIO(img_bytes))
            except Exception as e:
                self._log(f"图像解码失败: {e}  大小: {len(img_bytes)} bytes", "error")
                self._status("图像解码失败")
                return
            # 按用户所选分辨率档位对长边进行上采样
            target_long = {"1K": 1024, "2K": 2048, "4K": 3840}.get(self._res_var.get(), 0)
            long_side = max(img.width, img.height)
            if target_long > 0 and long_side != target_long:
                scale = target_long / long_side
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
                self._log(f"已将图像从 {long_side}px 上采样至 {target_long}px（长边，{self._res_var.get()}）")
            self._last_image_bytes = img_bytes
            # 记录 AI 轮次（仅 img_bytes，text 可为 None）
            self._current_turns.append({"role": "ai", "text": text, "img_bytes": img_bytes})
            tag = f"[{index}/{total}] " if total > 1 else ""
            self._log(f"{tag}图像生成成功，尺寸: {img.width}×{img.height}，大小: {len(img_bytes)//1024} KB", "ok")

            # 自动保存到 exe/脚本同目录下的 output 子目录
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fmt = self._format_var.get()
            ext_map = {"PNG": ".png", "JPEG": ".jpg", "WebP": ".webp"}
            ext = ext_map.get(fmt, ".png")
            save_path = OUTPUT_DIR / f"output_{ts}{ext}"
            save_img = img.convert("RGB") if fmt == "JPEG" else img
            save_img.save(save_path, format=fmt)
            self._log(f"已自动保存: {save_path.name}", "ok")

            self._append_ai_response(text, img_bytes)
            self._status(f"{tag}生成完成  尺寸: {img.width}×{img.height}  →  {save_path.name}")
        else:
            self._append_ai_response(text, None)
            self._status("收到文本响应")

    def _do_save_image(self, img_bytes: bytes):
        """弹出保存对话框，保存指定图片"""
        fmt = self._format_var.get()
        ext_map = {"PNG": ".png", "JPEG": ".jpg", "WebP": ".webp"}
        ext = ext_map.get(fmt, ".png")
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[(fmt, f"*{ext}"), ("所有文件", "*.*")],
            initialfile=f"output{ext}",
            parent=self,
        )
        if not path:
            return
        img = Image.open(io.BytesIO(img_bytes))
        if fmt == "JPEG":
            img = img.convert("RGB")
        img.save(path, format=fmt)
        self._status(f"已保存：{path}")

    def _save_image(self):
        """保存最新生成的图片（保留按钮兼容）"""
        if not self._last_image_bytes:
            messagebox.showinfo("提示", "还没有生成图片", parent=self)
            return
        self._do_save_image(self._last_image_bytes)

    def _preview_image(self, img_bytes: bytes):
        """左键单击：在独立窗口中全屏预览图片，点击或按 Esc 关闭"""
        win = tk.Toplevel(self)
        win.title("图片预览")
        win.configure(background="#000")
        img = Image.open(io.BytesIO(img_bytes))
        # 缩放至屏幕 90% 以内
        sw = int(self.winfo_screenwidth()  * 0.9)
        sh = int(self.winfo_screenheight() * 0.9)
        img.thumbnail((sw, sh), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(win, image=photo, background="#000", cursor="hand2")
        lbl.image = photo
        lbl.pack(expand=True)
        # 信息栏
        orig = Image.open(io.BytesIO(img_bytes))
        info = tk.Label(win,
            text=f"{orig.width}×{orig.height}  {len(img_bytes)//1024} KB  —  点击图片或按 Esc 关闭",
            background="#111", foreground="#aaa", font=("", 9))
        info.pack(fill="x")
        win.bind("<Escape>",   lambda e: win.destroy())
        lbl.bind("<Button-1>", lambda e: win.destroy())
        win.update_idletasks()
        wx = self.winfo_x() + (self.winfo_width()  - win.winfo_width())  // 2
        wy = self.winfo_y() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{max(0, wx)}+{max(0, wy)}")
        win.focus_set()

    def _show_img_menu(self, event, img_bytes: bytes):
        """右键单击：弹出图片操作菜单"""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="预览图片",
                         command=lambda: self._preview_image(img_bytes))
        menu.add_command(label="另存为…",
                         command=lambda: self._do_save_image(img_bytes))
        menu.add_separator()
        menu.add_command(label="复制图片到剪贴板",
                         command=lambda: self._copy_image_to_clipboard(img_bytes))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_image_to_clipboard(self, img_bytes: bytes):
        """将图片以 DIB 格式写入 Windows 剪贴板"""
        try:
            import win32clipboard
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="BMP")
            dib = buf.getvalue()[14:]   # 去掉 BMP 文件头，保留 DIB 数据
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
            win32clipboard.CloseClipboard()
            self._status("图片已复制到剪贴板")
        except ImportError:
            messagebox.showinfo("提示",
                "需要安装 pywin32 才能使用剪贴板功能\n"
                "运行：pip install pywin32")
        except Exception as e:
            self._log(f"复制剪贴板失败: {e}", "error")

    def _change_key(self):
        # 先要求输密码验证身份才能查看/修改
        pw_dlg = _PasswordDialog(self)
        self.wait_window(pw_dlg)
        if not pw_dlg.result_password:
            return
        current_key = load_api_key_with_password(pw_dlg.result_password)
        if current_key is None:
            messagebox.showerror("密码错误", "密码不正确，无法查看 API Key")
            return
        # 密码正确，弹出修改对话框并显示当前 key
        dlg = _EditKeyDialog(self, current_key)
        self.wait_window(dlg)
        if dlg.result:
            new_key, new_pw = dlg.result
            # 密码留空则沿用验证时输入的原密码
            final_pw = new_pw if new_pw else pw_dlg.result_password
            save_api_key(new_key, final_pw)
            self._api_key = new_key
            self._log("API Key 已更新", "ok")
            self._status("API Key 已更新")

    # ── 会话 ──────────────────────────────────
    def _capture_state(self, prompt: str = "") -> dict:
        return {
            "prompt":     prompt,
            "style_key":  self._style_var.get(),
            "model":      self._model_var.get(),
            "resolution": self._res_var.get(),
            "ratio":      self._ratio_var.get(),
            "fmt":        self._format_var.get(),
            "ref_images": list(self._ref_images),
        }

    def _restore_session(self, state: dict):
        """从历史数据恢复会话（仅显示，不恢复 ChatSession 上下文）"""
        self._style_var.set(state.get("style_key", ""))
        if state.get("model") in list(MODELS.keys()):
            self._model_var.set(state["model"])
        if state.get("resolution") in RESOLUTIONS:
            self._res_var.set(state["resolution"])
        if state.get("ratio") in ASPECT_RATIOS:
            self._ratio_var.set(state["ratio"])
        if state.get("fmt") in OUTPUT_FORMATS:
            self._format_var.set(state["fmt"])
        self._clear_ref()
        for r in state.get("ref_images", []):
            if Path(r["path"]).exists():
                self._ref_images.append(r)
                self._ref_tree.insert("", "end", values=(r["type"], Path(r["path"]).name))
        self._ref_count_var.set(f"{len(self._ref_images)} / {self.MAX_REF_IMAGES}")

        # 清空聊天窗口，重放历史轮次
        self._chat_text.configure(state="normal")
        self._chat_text.delete("1.0", "end")
        self._chat_text.insert("end", f"[历史对话 {state.get('timestamp','')}]\n", "divider")
        self._chat_text.configure(state="disabled")
        self._chat_image_refs.clear()
        self._last_image_bytes = None

        turns = state.get("turns", [])
        # 兼容旧格式（单张图片，无 turns）
        if not turns:
            prompt = state.get("prompt", "")
            img_path = state.get("image_path")
            if prompt:
                turns = [{"role": "user", "text": prompt}]
                if img_path and Path(img_path).exists():
                    turns.append({"role": "ai", "text": None, "image_file": str(Path(img_path).name)})

        for turn in turns:
            if turn["role"] == "user":
                self._append_user_msg(turn.get("text") or "")
            else:
                img_bytes = None
                img_file = turn.get("image_file")
                if img_file:
                    img_path = SESSIONS_DIR / img_file
                    if img_path.exists():
                        with open(img_path, "rb") as f:
                            img_bytes = f.read()
                        self._last_image_bytes = img_bytes
                self._append_ai_response(turn.get("text"), img_bytes)

    def _restore_last_session(self):
        sessions = list_sessions()
        if sessions:
            self._restore_session(sessions[0])
            self._log(f"已恢复上次会话 ({sessions[0].get('timestamp', '')})", "ok")

    def _open_history(self):
        dlg = _HistoryDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self._restore_session(dlg.result)
            self._log(f"已加载历史会话 ({dlg.result.get('timestamp', '')})", "ok")

    def _log(self, msg: str, level: str = "info"):
        """向日志面板写一条带时间戳的记录，level: info / ok / warn / error"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"[{ts}] ", "time")
        self._log_text.insert("end", msg + "\n", level)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _status(self, msg: str):
        self._status_var.set(msg)

    def _on_close(self):
        if self._current_turns:
            try:
                meta = self._capture_state()
                meta["timestamp"] = self._session_ts
                save_session(self._current_turns, meta)
            except Exception:
                pass
        self.destroy()


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
