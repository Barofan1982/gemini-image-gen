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
from pathlib import Path
from datetime import datetime
from PIL import Image

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QSplitter,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QTreeWidget, QTreeWidgetItem,
    QScrollArea, QFrame, QProgressBar, QMenuBar, QMenu, QStatusBar,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QSizePolicy, QHeaderView,
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QUrl, QThread, QSize
from PySide6.QtGui import (
    QPixmap, QImage, QFont, QColor, QTextCursor, QTextCharFormat,
    QTextBlockFormat, QTextImageFormat, QTextDocument, QAction,
    QPainter, QPalette, QKeySequence, QCursor, QShortcut,
)

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

# ─────────────────────────────────────────────
# 分辨率 / 比例（按模型分开）
# ─────────────────────────────────────────────
# Nano Banana 2 支持 512；Nano Banana Pro 不支持 512
RESOLUTIONS_FLASH = ["512", "1K", "2K", "4K"]
RESOLUTIONS_PRO   = ["1K", "2K", "4K"]

_RATIOS_COMMON = [
    "auto",
    "1:1  正方形",
    "16:9  横屏宽屏",
    "9:16  竖屏",
    "4:3  标准横",
    "3:4  标准竖",
    "3:2  摄影横",
    "2:3  摄影竖",
    "21:9  超宽屏",
    "4:5",
    "5:4",
]
# Nano Banana 2（与 Pro 相同，极端比例 4:1/1:4/8:1/1:8 Gemini native API 不支持）
ASPECT_RATIOS_FLASH = _RATIOS_COMMON[:]
# Nano Banana Pro 不支持 4:1 / 1:4 / 8:1 / 1:8
ASPECT_RATIOS_PRO = _RATIOS_COMMON[:]

# 按模型键映射
MODEL_RESOLUTIONS = {
    "Nano Banana 2 (快速)":   RESOLUTIONS_FLASH,
    "Nano Banana Pro (高质)":  RESOLUTIONS_PRO,
}
MODEL_RATIOS = {
    "Nano Banana 2 (快速)":  ASPECT_RATIOS_FLASH,
    "Nano Banana Pro (高质)": ASPECT_RATIOS_PRO,
}
# 全集（用于历史记录恢复校验）
ASPECT_RATIOS = list(dict.fromkeys(ASPECT_RATIOS_FLASH + ASPECT_RATIOS_PRO))

OUTPUT_FORMATS = ["PNG", "JPEG", "WebP"]

# ─────────────────────────────────────────────
# 风格预设库
# ─────────────────────────────────────────────
STYLE_PRESETS = {

    # ── 3D 手办 ──────────────────────────────
    "3D｜手办（无底座）": (
        "高品质PVC手办风格，无底座，白色或浅灰渐变工作室背景，"
        "45度旋转台视角，三点式柔光灯光，"
        "光滑哑光涂装质感，精细面部彩绘，"
        "关节分明的身体结构，正版商业手办摄影级别，"
        "无底座悬浮展示，产品级精细渲染"
    ),

    # ── 2D 游戏动漫卡通 ─────────────────────
    "2D｜游戏动漫卡通": (
        "2D游戏动漫卡通插画风格，干净有力的黑色勾线，"
        "赛璐璐平涂着色，鲜艳饱和色彩，"
        "角色设计感强烈，大眼睛圆脸萌系比例，"
        "简洁明快背景，手游or社交游戏UI美术品质，"
        "活泼生动的表情与姿势"
    ),

    # ── 2D 剪纸立体画 ────────────────────────
    "2D｜剪纸立体画": (
        "多层次剪纸立体艺术风格，层层叠叠的纸质图层，"
        "每层之间有明显阴影产生立体纵深感，"
        "纸张纹理清晰可见，色彩以柔和马卡龙色或饱和撞色为主，"
        "手工剪纸工艺美感，光线从上方照射产生精致阴影，"
        "平面摄影构图，像是精心陈列的纸艺装置"
    ),

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
# QSS Stylesheet
# ─────────────────────────────────────────────
APP_QSS = """
QMainWindow, QDialog, QWidget { background:#f5f5f7; color:#1d1d1f; font-family:"Segoe UI"; font-size:10pt; }
QWidget#sidebar { background:#f2f2f7; border-right:1px solid #d1d1d6; }
QWidget#content_area { background:#ffffff; }
QLabel#section_hd { color:#1d1d1f; font-weight:700; font-size:10pt; }
QLabel#sub_label { color:#8e8e93; font-size:9pt; }
QPushButton { background:#e8e8ed; color:#1d1d1f; border:none; border-radius:8px; padding:6px 14px; min-height:28px; }
QPushButton:hover { background:#d1d1d6; }
QPushButton:pressed { background:#c7c7cc; }
QPushButton:disabled { color:#aeaeb2; }
QPushButton#primary_btn { background:#007aff; color:white; font-weight:600; }
QPushButton#primary_btn:hover { background:#0062cc; }
QPushButton#primary_btn:pressed { background:#0055b3; }
QPushButton#danger_btn { background:#fff0f0; color:#ff3b30; }
QPushButton#danger_btn:hover { background:#ffe0df; }
QPushButton#ghost_btn { background:#f2f2f7; color:#007aff; }
QPushButton#ghost_btn:hover { background:#dde6f5; }
QPushButton#send_btn { background:#007aff; color:white; border-radius:18px; min-width:36px; max-width:36px; min-height:36px; max-height:36px; font-size:16pt; font-weight:700; padding:0; }
QPushButton#send_btn:hover { background:#0062cc; }
QPushButton#send_btn:disabled { background:#b0b8c4; }
QPushButton#icon_btn { background:#e8e8ed; border-radius:15px; min-width:30px; max-width:30px; min-height:30px; max-height:30px; padding:0; font-size:11pt; }
QPushButton#icon_btn:hover { background:#d1d1d6; }
QComboBox { background:#ffffff; color:#1d1d1f; border:1px solid #d1d1d6; border-radius:7px; padding:4px 10px; min-height:28px; }
QComboBox:focus { border-color:#007aff; }
QComboBox::drop-down { border:none; width:24px; }
QComboBox::down-arrow { border-left:5px solid transparent; border-right:5px solid transparent; border-top:6px solid #8e8e93; margin-right:8px; }
QComboBox QAbstractItemView { background:#ffffff; border:1px solid #d1d1d6; selection-background-color:#e8f0fe; selection-color:#007aff; outline:none; }
QComboBox QAbstractItemView::item { min-height:28px; padding-left:8px; }
QTreeWidget { background:#ffffff; border:1px solid #e5e5ea; border-radius:8px; outline:none; }
QTreeWidget::item { height:30px; border:none; }
QTreeWidget::item:selected { background:#e8f0fe; color:#007aff; }
QHeaderView::section { background:#f2f2f7; color:#6e6e73; font-weight:600; font-size:9pt; border:none; border-bottom:1px solid #e5e5ea; padding:4px 8px; }
QTextEdit { background:#ffffff; border:none; font-family:"Segoe UI"; font-size:10pt; }
QTextEdit#input_text { background:#f2f2f7; }
QScrollBar:vertical { background:transparent; width:6px; margin:2px; }
QScrollBar::handle:vertical { background:#c7c7cc; border-radius:3px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#aeaeb2; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; height:0; }
QScrollBar:horizontal { height:6px; background:transparent; margin:2px; }
QScrollBar::handle:horizontal { background:#c7c7cc; border-radius:3px; min-width:30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
QProgressBar { background:transparent; border:none; max-height:3px; text-align:center; }
QProgressBar::chunk { background:#007aff; border-radius:1px; }
QMenuBar { background:#f5f5f7; border-bottom:1px solid #e5e5ea; padding:2px 4px; }
QMenuBar::item { background:transparent; padding:4px 10px; border-radius:5px; }
QMenuBar::item:selected, QMenuBar::item:pressed { background:#e8e8ed; }
QMenu { background:#ffffff; border:1px solid #d1d1d6; border-radius:8px; padding:4px; }
QMenu::item { padding:6px 20px; border-radius:5px; }
QMenu::item:selected { background:#e8f0fe; color:#007aff; }
QMenu::separator { height:1px; background:#e5e5ea; margin:4px 10px; }
QStatusBar { background:#1c1c1e; color:#8e8e93; font-size:9pt; }
QSplitter::handle:horizontal { background:#d1d1d6; width:1px; }
QLineEdit { background:#ffffff; border:1px solid #d1d1d6; border-radius:7px; padding:6px 10px; min-height:28px; }
QLineEdit:focus { border-color:#007aff; }
QDialog { background:#f5f5f7; }
QListWidget { background:#ffffff; border:1px solid #e5e5ea; border-radius:8px; outline:none; }
QListWidget::item { border-bottom:1px solid #f2f2f7; padding:6px; }
QListWidget::item:selected { background:#e8f0fe; color:#007aff; }
QListWidget::item:hover:!selected { background:#f2f2f7; }
QTextEdit#log_text { background:#161b22; color:#c9d1d9; font-family:"Cascadia Code","Consolas"; font-size:10pt; border:none; }
"""

# ─────────────────────────────────────────────
# GUI：登录 / 设置 API Key
# ─────────────────────────────────────────────

class AuthDialog(QDialog):
    """首次设置 API Key 对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("首次设置 API Key")
        self.setFixedWidth(460)
        self.result_key: str | None = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("Gemini API Key："), 0, 0, Qt.AlignRight)
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setPlaceholderText("AIza...")
        grid.addWidget(self._key_edit, 0, 1)

        # Show/hide button
        self._show_key_btn = QPushButton("显示")
        self._show_key_btn.setFixedWidth(52)
        self._show_key_btn.clicked.connect(self._toggle_key_visibility)
        grid.addWidget(self._show_key_btn, 0, 2)

        grid.addWidget(QLabel("设置密码（用于查看 Key）："), 1, 0, Qt.AlignRight)
        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.Password)
        grid.addWidget(self._pw_edit, 1, 1, 1, 2)

        grid.addWidget(QLabel("确认密码："), 2, 0, Qt.AlignRight)
        self._pw2_edit = QLineEdit()
        self._pw2_edit.setEchoMode(QLineEdit.Password)
        grid.addWidget(self._pw2_edit, 2, 1, 1, 2)

        layout.addLayout(grid)

        hint = QLabel("密码仅在查看/修改 Key 时需要，\n日常使用自动解锁。")
        hint.setObjectName("sub_label")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("退出")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_btn = QPushButton("确认")
        confirm_btn.setObjectName("primary_btn")
        confirm_btn.clicked.connect(self._confirm)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

    def _toggle_key_visibility(self):
        if self._key_edit.echoMode() == QLineEdit.Password:
            self._key_edit.setEchoMode(QLineEdit.Normal)
            self._show_key_btn.setText("隐藏")
        else:
            self._key_edit.setEchoMode(QLineEdit.Password)
            self._show_key_btn.setText("显示")

    def _confirm(self):
        key = self._key_edit.text().strip()
        pw  = self._pw_edit.text().strip()
        pw2 = self._pw2_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "提示", "API Key 不能为空")
            return
        if not key.startswith("AIza"):
            QMessageBox.warning(self, "提示", "API Key 格式不正确，应以 AIza 开头")
            return
        if not pw:
            QMessageBox.warning(self, "提示", "密码不能为空")
            return
        if pw != pw2:
            QMessageBox.warning(self, "提示", "两次密码不一致")
            return
        save_api_key(key, pw)
        self.result_key = key
        self.accept()


# ─────────────────────────────────────────────
# GUI：主界面
# ─────────────────────────────────────────────

class _PasswordDialog(QDialog):
    """输入密码以验证身份"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("验证密码")
        self.setFixedWidth(340)
        self.result_password: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.addWidget(QLabel("请输入密码以查看 API Key："))
        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self._pw_edit)
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("确认")
        ok_btn.setObjectName("primary_btn")
        ok_btn.clicked.connect(self._ok)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _ok(self):
        pw = self._pw_edit.text().strip()
        if pw:
            self.result_password = pw
        self.accept()


class _EditKeyDialog(QDialog):
    """显示并修改 API Key（密码验证通过后才打开）"""
    def __init__(self, parent=None, current_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("查看 / 修改 API Key")
        self.setFixedWidth(500)
        self.result: tuple | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.addWidget(QLabel("API Key："), 0, 0, Qt.AlignRight)
        self._key_edit = QLineEdit(current_key)
        grid.addWidget(self._key_edit, 0, 1)

        grid.addWidget(QLabel("新密码（留空则保持原密码不变）："), 1, 0, Qt.AlignRight)
        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.Password)
        grid.addWidget(self._pw_edit, 1, 1)

        grid.addWidget(QLabel("确认新密码："), 2, 0, Qt.AlignRight)
        self._pw2_edit = QLineEdit()
        self._pw2_edit.setEchoMode(QLineEdit.Password)
        grid.addWidget(self._pw2_edit, 2, 1)

        layout.addLayout(grid)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        key = self._key_edit.text().strip()
        pw  = self._pw_edit.text().strip()
        pw2 = self._pw2_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "提示", "API Key 不能为空")
            return
        if pw and pw != pw2:
            QMessageBox.warning(self, "提示", "两次密码不一致")
            return
        self.result = (key, pw)
        self.accept()


class _HistoryDialog(QDialog):
    """历史会话浏览器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.resize(720, 480)
        self.result: dict | None = None
        self._sessions = list_sessions()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        # Left: session list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        count_lbl = QLabel(f"共 {len(self._sessions)} 条记录")
        left_layout.addWidget(count_lbl)

        self._list = QListWidget()
        for s in self._sessions:
            ts = s.get("timestamp", "")
            turns = s.get("turns", [])
            first_user = next((t for t in turns if t.get("role") == "user"), None)
            subj = (first_user.get("text") if first_user else None) \
                   or s.get("prompt") or s.get("style_key") or "（无标题）"
            img_count = sum(1 for t in turns if t.get("image_file"))
            label = f"{ts}  {subj[:30]}  [{img_count}图]" if img_count else f"{ts}  {subj[:40]}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, s["_json_path"])
            self._list.addItem(item)
        self._list.currentItemChanged.connect(self._on_select)
        left_layout.addWidget(self._list)
        splitter.addWidget(left_widget)

        # Right: preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(4)

        self._preview_lbl = QLabel("选择一条记录预览")
        self._preview_lbl.setAlignment(Qt.AlignCenter)
        self._preview_lbl.setMinimumHeight(200)
        self._preview_lbl.setStyleSheet("background:#f2f2f7; border-radius:6px;")
        right_layout.addWidget(self._preview_lbl, 1)

        self._preview_info = QTextEdit()
        self._preview_info.setReadOnly(True)
        self._preview_info.setMaximumHeight(100)
        self._preview_info.setStyleSheet("font-family:'Consolas'; font-size:9pt;")
        right_layout.addWidget(self._preview_info)
        splitter.addWidget(right_widget)

        splitter.setSizes([360, 340])

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        load_btn = QPushButton("加载选中")
        load_btn.setObjectName("primary_btn")
        load_btn.clicked.connect(self._load)
        btn_row.addWidget(load_btn)
        layout.addLayout(btn_row)

    def _on_select(self, current, previous):
        if not current:
            return
        json_path = current.data(Qt.UserRole)
        s = next((x for x in self._sessions if x["_json_path"] == json_path), None)
        if not s:
            return
        img_path = s.get("image_path")
        if img_path and Path(img_path).exists():
            pix = QPixmap(img_path).scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._preview_lbl.setPixmap(pix)
            self._preview_lbl.setText("")
        else:
            self._preview_lbl.clear()
            self._preview_lbl.setText("无图片")

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
        self._preview_info.setPlainText(info)

    def _load(self):
        current = self._list.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        json_path = current.data(Qt.UserRole)
        s = next((x for x in self._sessions if x["_json_path"] == json_path), None)
        if s:
            self.result = s
        self.accept()


class _RefTypeDialog(QDialog):
    """选择参考图类型的小对话框"""
    def __init__(self, parent=None, types: list[str] = None):
        super().__init__(parent)
        self.setWindowTitle("选择参考类型")
        self.setFixedWidth(260)
        self.result: str | None = None
        types = types or []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(QLabel("这批图片的参考用途："))
        for t in types:
            btn = QPushButton(t)
            btn.clicked.connect(lambda checked, val=t: self._pick(val))
            layout.addWidget(btn)

    def _pick(self, val: str):
        self.result = val
        self.accept()


class _LogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("运行日志")
        self.resize(540, 300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setObjectName("log_text")
        layout.addWidget(self._text)

    def append(self, ts: str, msg: str, level: str):
        colors = {"info": "#79c0ff", "ok": "#56d364", "warn": "#e3b341", "error": "#f85149", "time": "#484f58"}
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        # time part
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#484f58"))
        cursor.insertText(f"[{ts}] ", fmt)
        # message part
        fmt2 = QTextCharFormat()
        fmt2.setForeground(QColor(colors.get(level, "#c9d1d9")))
        cursor.insertText(msg + "\n", fmt2)
        self._text.ensureCursorVisible()


class _ChatView(QTextEdit):
    """QTextEdit with image click/right-click support."""
    image_left_click  = Signal(str)          # img_key
    image_right_click = Signal(str, object)  # img_key, QPoint

    def _img_key_at(self, pos) -> str:
        """返回点击位置的图片 key，未命中则返回空字符串。"""
        cursor = self.cursorForPosition(pos)
        # 图片占一个字符宽度，试探当前位置及前后各一格
        for delta in (0, 1, -1):
            c = QTextCursor(cursor)
            if delta > 0:
                c.movePosition(QTextCursor.Right)
            elif delta < 0:
                c.movePosition(QTextCursor.Left)
            fmt = c.charFormat()
            # 优先检查 anchor href
            if fmt.isAnchor():
                href = fmt.anchorHref()
                if href.startswith("img_"):
                    return href
            # 其次检查 image format 的 name
            if fmt.isImageFormat():
                name = fmt.toImageFormat().name()
                if name.startswith("img_"):
                    return name
        return ""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            key = self._img_key_at(event.pos())
            if key:
                self.image_left_click.emit(key)
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """图片区域显示自定义菜单；文字区域显示默认菜单。"""
        key = self._img_key_at(event.pos())
        if key:
            self.image_right_click.emit(key, event.globalPos())
        else:
            super().contextMenuEvent(event)


class App(QMainWindow):
    _sig_image  = Signal(bytes, str, str, str, int, int, bool)
    _sig_log    = Signal(str, str)
    _sig_status = Signal(str)

    MAX_REF_IMAGES = 14
    REF_EXTS = "图片文件 (*.png *.jpg *.jpeg *.webp *.heic *.heif)"
    EXT_MIME = { ".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".webp":"image/webp", ".heic":"image/heic", ".heif":"image/heif" }
    REF_TYPES = ["主体 / 角色一致性", "风格参考", "场景 / 环境参考", "通用参考"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini 图像生成工具")
        self.resize(1040, 720)
        self.setMinimumSize(800, 580)

        # State
        self._api_key = None
        self._ref_images = []
        self._last_image_bytes = None
        self._chat_session = None
        self._genai_client = None
        self._session_cfg = ()
        self._current_turns = []
        self._session_ts = ""
        self._prompt_history = []
        self._history_idx = -1
        self._saved_input = ""
        self._chat_image_store = {}   # key -> bytes, for image preview/save

        # Connect signals
        self._sig_image.connect(self._on_one_image)
        self._sig_log.connect(self._log)
        self._sig_status.connect(self._status)

        self._build()
        QTimer.singleShot(100, self._authenticate)

    def _build(self):
        self._build_menu()

        # Central splitter
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Progress bar at very top
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setTextVisible(False)
        self._progress.setMaximumHeight(3)
        self._progress.hide()
        main_layout.addWidget(self._progress)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        main_layout.addWidget(splitter, 1)

        # Left sidebar
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(320)
        splitter.addWidget(sidebar)
        self._build_left(sidebar)

        # Right content
        content = QWidget()
        content.setObjectName("content_area")
        splitter.addWidget(content)
        self._build_right(content)

        splitter.setSizes([280, 760])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")

        # Log dialog
        self._log_dialog = _LogDialog(self)

    def _build_menu(self):
        menubar = self.menuBar()
        setting_menu = menubar.addMenu("设置")
        change_key_action = QAction("修改 API Key", self)
        change_key_action.triggered.connect(self._change_key)
        setting_menu.addAction(change_key_action)
        history_action = QAction("历史记录", self)
        history_action.triggered.connect(self._open_history)
        menubar.addAction(history_action)

    def _build_left(self, sidebar):
        outer_layout = QVBoxLayout(sidebar)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer_layout.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("sidebar")
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 区块：参考图片 ──────────────────────
        hd1 = QLabel("参考图片")
        hd1.setObjectName("section_hd")
        hd1.setContentsMargins(16, 20, 16, 8)
        layout.addWidget(hd1)

        ref_wrap = QWidget()
        ref_wrap.setObjectName("sidebar")
        ref_layout = QVBoxLayout(ref_wrap)
        ref_layout.setContentsMargins(16, 0, 16, 0)
        ref_layout.setSpacing(4)

        self._ref_tree = QTreeWidget()
        self._ref_tree.setColumnCount(2)
        self._ref_tree.setHeaderLabels(["参考类型", "文件名"])
        self._ref_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._ref_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self._ref_tree.setMaximumHeight(120)
        self._ref_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        ref_layout.addWidget(self._ref_tree)

        ref_btns_widget = QWidget()
        ref_btns_widget.setObjectName("sidebar")
        ref_btns_layout = QHBoxLayout(ref_btns_widget)
        ref_btns_layout.setContentsMargins(0, 0, 0, 0)
        ref_btns_layout.setSpacing(4)

        self._ref_count_label = QLabel(f"0 / {self.MAX_REF_IMAGES}")
        self._ref_count_label.setObjectName("sub_label")
        ref_btns_layout.addWidget(self._ref_count_label)
        ref_btns_layout.addStretch()

        add_btn = QPushButton("＋ 添加")
        add_btn.setObjectName("ghost_btn")
        add_btn.clicked.connect(self._add_ref_image)
        ref_btns_layout.addWidget(add_btn)

        del_btn = QPushButton("删除")
        del_btn.setObjectName("danger_btn")
        del_btn.clicked.connect(self._remove_ref_image)
        ref_btns_layout.addWidget(del_btn)

        clr_btn = QPushButton("清空")
        clr_btn.setObjectName("danger_btn")
        clr_btn.clicked.connect(self._clear_ref)
        ref_btns_layout.addWidget(clr_btn)

        ref_layout.addWidget(ref_btns_widget)
        layout.addWidget(ref_wrap)

        # ── 分隔 ────────────────────────────────
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color:#e5e5ea; margin:0 12px;")
        sep1.setContentsMargins(12, 20, 12, 0)
        layout.addWidget(sep1)

        # ── 区块：画面风格 ──────────────────────
        hd2 = QLabel("画面风格")
        hd2.setObjectName("section_hd")
        hd2.setContentsMargins(16, 16, 16, 8)
        layout.addWidget(hd2)

        style_wrap = QWidget()
        style_wrap.setObjectName("sidebar")
        style_layout = QVBoxLayout(style_wrap)
        style_layout.setContentsMargins(16, 0, 16, 0)
        style_layout.setSpacing(4)

        style_values = ["(无风格)"] + list(STYLE_PRESETS.keys())
        self._style_combo = QComboBox()
        self._style_combo.addItems(style_values)
        self._style_combo.setCurrentIndex(0)
        style_layout.addWidget(self._style_combo)

        self._style_label = QLabel("不附加任何风格提示词")
        self._style_label.setObjectName("sub_label")
        self._style_label.setWordWrap(True)
        self._style_label.setContentsMargins(0, 4, 0, 0)
        style_layout.addWidget(self._style_label)

        self._style_combo.currentTextChanged.connect(self._on_style_change)
        layout.addWidget(style_wrap)

        # ── 分隔 ────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#e5e5ea; margin:0 12px;")
        sep2.setContentsMargins(12, 20, 12, 0)
        layout.addWidget(sep2)

        # ── 区块：生成参数 ──────────────────────
        hd3 = QLabel("生成参数")
        hd3.setObjectName("section_hd")
        hd3.setContentsMargins(16, 16, 16, 8)
        layout.addWidget(hd3)

        param_wrap = QWidget()
        param_wrap.setObjectName("sidebar")
        param_layout = QGridLayout(param_wrap)
        param_layout.setContentsMargins(16, 0, 16, 8)
        param_layout.setSpacing(6)

        params = [
            ("模型",   list(MODELS.keys())),
            ("分辨率", RESOLUTIONS_FLASH),
            ("比例",   ASPECT_RATIOS_FLASH),
            ("格式",   OUTPUT_FORMATS),
            ("数量",   ["1 张", "2 张", "3 张", "4 张"]),
        ]
        combo_attrs = ["_model_combo", "_res_combo", "_ratio_combo", "_format_combo", "_count_combo"]
        for i, ((label, values), attr) in enumerate(zip(params, combo_attrs)):
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            param_layout.addWidget(lbl, i, 0)
            cb = QComboBox()
            cb.addItems(values)
            param_layout.addWidget(cb, i, 1)
            setattr(self, attr, cb)
        param_layout.setColumnStretch(1, 1)

        self._model_combo.currentTextChanged.connect(self._on_model_change)
        layout.addWidget(param_wrap)

        # ── 底部：日志按钮 ──────────────────────
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("color:#e5e5ea; margin:0 12px;")
        layout.addWidget(sep3)

        log_row = QWidget()
        log_row.setObjectName("sidebar")
        log_row_layout = QHBoxLayout(log_row)
        log_row_layout.setContentsMargins(16, 8, 16, 16)
        log_row_layout.setAlignment(Qt.AlignVCenter)

        log_btn = QPushButton("📋  日志")
        log_btn.setFixedSize(100, 36)
        log_btn.setStyleSheet("""
            QPushButton { background-color:#e8e8ed; color:#1d1d1f; border-radius:8px;
                          font-size:10pt; font-weight:500; border:none; }
            QPushButton:hover   { background-color:#d1d1d6; }
            QPushButton:pressed { background-color:#c7c7cc; }
        """)
        log_btn.clicked.connect(self._toggle_log)
        log_row_layout.addWidget(log_btn)
        log_row_layout.addStretch()
        layout.addWidget(log_row)

        layout.addStretch()

    def _build_right(self, content):
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat view fills space
        self._chat_view = _ChatView()
        self._chat_view.setReadOnly(True)
        self._chat_view.setObjectName("chat_view")
        self._chat_view.setStyleSheet(
            "QTextEdit { background:#ffffff; border:none; padding:12px 16px; }"
        )
        self._chat_view.image_left_click.connect(self._preview_image)
        self._chat_view.image_right_click.connect(self._show_img_menu)
        layout.addWidget(self._chat_view, 1)

        # Bottom input area
        bottom_wrapper = QWidget()
        bottom_wrapper.setStyleSheet("background:#ffffff;")
        bottom_layout = QVBoxLayout(bottom_wrapper)
        bottom_layout.setContentsMargins(16, 4, 16, 16)
        bottom_layout.setSpacing(0)

        input_container = QFrame()
        input_container.setStyleSheet(
            "QFrame { background:#f2f2f7; border:1px solid #d1d1d6; border-radius:14px; }"
        )
        input_inner_layout = QHBoxLayout(input_container)
        input_inner_layout.setContentsMargins(8, 8, 8, 8)
        input_inner_layout.setSpacing(4)

        # Left icon buttons
        left_btns = QWidget()
        left_btns.setStyleSheet("background:transparent;")
        left_btns_layout = QVBoxLayout(left_btns)
        left_btns_layout.setContentsMargins(0, 0, 0, 0)
        left_btns_layout.setSpacing(4)

        _PILL_BTN_SS = """
            QPushButton { background-color:#e8e8ed; color:#1d1d1f; border-radius:10px;
                          font-size:9pt; font-weight:500; border:none; padding:2px 10px; }
            QPushButton:hover   { background-color:#d1d1d6; }
            QPushButton:pressed { background-color:#c7c7cc; }
        """
        new_chat_btn = QPushButton("新对话")
        new_chat_btn.setFixedHeight(26)
        new_chat_btn.setMinimumWidth(62)
        new_chat_btn.setStyleSheet(_PILL_BTN_SS)
        new_chat_btn.clicked.connect(self._new_chat)
        left_btns_layout.addWidget(new_chat_btn)

        save_btn = QPushButton("保存图片")
        save_btn.setFixedHeight(26)
        save_btn.setMinimumWidth(62)
        save_btn.setStyleSheet(_PILL_BTN_SS)
        save_btn.clicked.connect(self._save_image)
        left_btns_layout.addWidget(save_btn)

        input_inner_layout.addWidget(left_btns)

        # Input text（背景透明，父容器提供颜色）
        self._input_text = QTextEdit()
        self._input_text.setObjectName("input_text")
        self._input_text.setPlaceholderText("输入提示词，Enter 发送，Shift+Enter 换行...")
        self._input_text.setFixedHeight(72)
        self._input_text.setStyleSheet(
            "QTextEdit { background:transparent; border:none; "
            "font-family:'Segoe UI'; font-size:10pt; padding:4px; }"
        )
        self._input_text.installEventFilter(self)
        input_inner_layout.addWidget(self._input_text, 1)

        # 圆角方形提交按钮 — 用 inline stylesheet 防止父级白色背景级联覆盖
        self._send_btn = QPushButton("提交")
        self._send_btn.setFixedSize(52, 36)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff; color: white;
                border-radius: 10px; border: none;
                font-size: 10pt; font-weight: 600; padding: 0;
            }
            QPushButton:hover    { background-color: #0062cc; }
            QPushButton:pressed  { background-color: #0055b3; }
            QPushButton:disabled { background-color: #b0b8c4; }
        """)
        self._send_btn.clicked.connect(self._send_message)
        input_inner_layout.addWidget(self._send_btn)

        bottom_layout.addWidget(input_container)
        layout.addWidget(bottom_wrapper)

    def eventFilter(self, obj, event):
        if obj is self._input_text and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
                self._send_message()
                return True
            if event.key() == Qt.Key_Up:
                cursor = self._input_text.textCursor()
                if cursor.blockNumber() == 0:
                    self._on_history_up()
                    return True
            if event.key() == Qt.Key_Down:
                cursor = self._input_text.textCursor()
                block_count = self._input_text.document().blockCount()
                if cursor.blockNumber() == block_count - 1:
                    self._on_history_down()
                    return True
        return super().eventFilter(obj, event)

    # ── 认证流程 ──────────────────────────────
    def _authenticate(self):
        if has_saved_key():
            key = load_api_key_auto()
            if key:
                self._api_key = key
                self._log("API Key 已自动加载，就绪", "ok")
                self._status("就绪")
                self._restore_last_session()
                return
            self._log("DPAPI 自动解密失败，请重新输入 API Key", "warn")
        dlg = AuthDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._api_key = dlg.result_key
            self._status("已设置，可以开始生成图片")
            self._log("API Key 设置成功，就绪", "ok")
            self._restore_last_session()
        else:
            QApplication.quit()

    # ── 事件处理 ──────────────────────────────
    def _on_model_change(self, model_name):
        # 更新分辨率
        resolutions = MODEL_RESOLUTIONS.get(model_name, RESOLUTIONS_FLASH)
        cur_res = self._res_combo.currentText()
        self._res_combo.clear()
        self._res_combo.addItems(resolutions)
        if cur_res in resolutions:
            self._res_combo.setCurrentText(cur_res)
        else:
            self._res_combo.setCurrentIndex(0)
        # 更新比例
        ratios = MODEL_RATIOS.get(model_name, ASPECT_RATIOS_FLASH)
        current = self._ratio_combo.currentText()
        self._ratio_combo.clear()
        self._ratio_combo.addItems(ratios)
        if current in ratios:
            self._ratio_combo.setCurrentText(current)
        else:
            self._ratio_combo.setCurrentIndex(0)

    def _on_style_change(self, key):
        if key and key != "(无风格)":
            preview = STYLE_PRESETS.get(key, "")
            self._style_label.setText(preview[:80] + ("..." if len(preview) > 80 else ""))
        else:
            self._style_label.setText("不附加任何风格提示词")

    def _on_history_up(self):
        if not self._prompt_history:
            return
        if self._history_idx == -1:
            self._saved_input = self._input_text.toPlainText()
            self._history_idx = len(self._prompt_history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        self._input_text.setPlainText(self._prompt_history[self._history_idx])
        cursor = self._input_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._input_text.setTextCursor(cursor)

    def _on_history_down(self):
        if self._history_idx == -1:
            return
        self._history_idx += 1
        if self._history_idx >= len(self._prompt_history):
            self._history_idx = -1
            self._input_text.setPlainText(self._saved_input)
        else:
            self._input_text.setPlainText(self._prompt_history[self._history_idx])
        cursor = self._input_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._input_text.setTextCursor(cursor)

    def _send_message(self):
        if not self._api_key:
            QMessageBox.warning(self, "未解锁", "请先完成 API Key 设置")
            return
        user_text = self._input_text.toPlainText().strip()
        if not user_text:
            return
        self._input_text.clear()

        # 存入历史（去重：与最后一条相同则跳过）
        if not self._prompt_history or self._prompt_history[-1] != user_text:
            self._prompt_history.append(user_text)
        self._history_idx = -1
        self._saved_input = ""

        # 风格预设附加到 prompt；NO_TEXT 已移除，不再强制禁文字
        style_key = self._style_combo.currentText()
        if style_key == "(无风格)":
            style_key = ""
        style_desc = STYLE_PRESETS.get(style_key, "") if style_key else ""
        full_prompt = user_text
        if style_desc:
            full_prompt += f"\n\n风格要求：{style_desc}"
        ratio_text = self._ratio_combo.currentText().split()[0]   # "auto" / "16:9" 等
        res_text   = self._res_combo.currentText().split()[0]     # "1K" "2K" "4K"

        model_key  = self._model_combo.currentText()
        model_name = MODELS[model_key]
        count      = int(self._count_combo.currentText().split()[0])

        # 初始化会话时间戳
        if not self._session_ts:
            self._session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 记录用户轮次
        self._current_turns.append({"role": "user", "text": user_text,
                                    "img_bytes": None})

        self._append_user_msg(user_text)
        self._send_btn.setEnabled(False)
        self._progress.show()
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
        if self._current_turns:
            try:
                meta = self._capture_state()
                meta["timestamp"] = self._session_ts
                save_session(self._current_turns, meta)
                self._log("对话已自动保存", "ok")
            except Exception as e:
                self._log(f"自动保存失败: {e}", "warn")

        self._chat_session = None
        self._genai_client = None
        self._session_cfg  = ()
        self._chat_image_store.clear()
        self._current_turns.clear()
        self._session_ts = ""
        self._last_image_bytes = None
        self._chat_view.clear()
        self._log("已开始新对话", "info")
        self._status("新对话已开始")

    def _append_user_msg(self, text: str):
        cursor = self._chat_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        name_fmt = QTextCharFormat()
        name_fmt.setForeground(QColor("#007aff"))
        name_fmt.setFontWeight(QFont.Bold)
        name_fmt.setFontPointSize(9)
        cursor.insertText("你：\n", name_fmt)
        msg_fmt = QTextCharFormat()
        msg_fmt.setForeground(QColor("#1d1d1f"))
        msg_fmt.setBackground(QColor("#e8f0fe"))
        block_fmt = QTextBlockFormat()
        block_fmt.setLeftMargin(20)
        cursor.setBlockFormat(block_fmt)
        cursor.insertText(text + "\n\n", msg_fmt)
        cursor.setBlockFormat(QTextBlockFormat())
        self._chat_view.setTextCursor(cursor)
        self._chat_view.ensureCursorVisible()

    def _append_ai_response(self, text, img_bytes):
        cursor = self._chat_view.textCursor()
        cursor.movePosition(QTextCursor.End)

        # AI name
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#059669"))
        fmt.setFontWeight(QFont.Bold)
        cursor.insertText("Gemini：\n", fmt)

        if text:
            txt_fmt = QTextCharFormat()
            txt_fmt.setForeground(QColor("#1d1d1f"))
            txt_fmt.setBackground(QColor("#f2f2f7"))
            block_fmt = QTextBlockFormat()
            block_fmt.setLeftMargin(20)
            cursor.setBlockFormat(block_fmt)
            cursor.insertText(text + "\n", txt_fmt)

        if img_bytes:
            img_key = f"img_{len(self._chat_image_store)}"
            self._chat_image_store[img_key] = img_bytes

            qimg = QImage.fromData(img_bytes)
            pix = QPixmap.fromImage(qimg).scaled(480, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            doc = self._chat_view.document()
            doc.addResource(QTextDocument.ImageResource, QUrl(img_key), pix)

            # 直接在 QTextImageFormat 上设置锚点，确保 charFormat 能读到 href
            img_fmt = QTextImageFormat()
            img_fmt.setName(img_key)
            img_fmt.setAnchor(True)
            img_fmt.setAnchorHref(img_key)
            cursor.insertImage(img_fmt)

            cursor.setCharFormat(QTextCharFormat())
            hint_fmt = QTextCharFormat()
            hint_fmt.setForeground(QColor("#8e8e93"))
            hint_fmt.setFontPointSize(8)
            cursor.insertText("  单击预览，右键菜单\n", hint_fmt)

        div_fmt = QTextCharFormat()
        div_fmt.setForeground(QColor("#e5e5ea"))
        cursor.insertText("─" * 40 + "\n", div_fmt)

        self._chat_view.setTextCursor(cursor)
        self._chat_view.ensureCursorVisible()

    def _run_chat(self, full_prompt: str, model_name: str,
                 ref_images: list, user_text: str, count: int = 1,
                 ratio_text: str = "1:1", res_text: str = "1K"):
        def log(msg, level="info"):
            self._sig_log.emit(msg, level)
        try:
            log("已发送请求，等待模型响应...", "warn")

            # 新 SDK：构建 image_config（原生分辨率 + 比例）
            # 4K API 不支持，用 2K 生成后 _on_one_image 再放大；其余直接传原生值
            api_size = {"512": "512", "1K": "1K", "2K": "2K", "4K": "2K"}.get(res_text, "1K")
            # auto 不传 aspect_ratio，让模型自行决定
            img_cfg = genai_types.ImageConfig(
                image_size=api_size,
                **({} if ratio_text == "auto" else {"aspect_ratio": ratio_text}),
            )
            gen_cfg = genai_types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=img_cfg,
            )

            new_cfg_key = (model_name, api_size, ratio_text)
            if self._chat_session is None or self._session_cfg != new_cfg_key:
                self._genai_client = genai.Client(api_key=self._api_key)
                self._chat_session = self._genai_client.chats.create(
                    model=model_name, config=gen_cfg)
                self._session_cfg = new_cfg_key

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
                    follow = "请再生成一张，风格主题与上面相同。"
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
                self._sig_image.emit(img_bytes or b'', response_text or '', '', user_text, idx+1, count, is_last)

        except Exception as e:
            self._sig_image.emit(b'', '', str(e), user_text, -1, count, True)

    def _on_one_image(self, img_bytes: bytes, text: str, error: str, user_text: str,
                      index: int, total: int, is_last: bool):
        if not img_bytes:
            img_bytes = None
        if not text:
            text = None
        if not error:
            error = None

        if is_last or error:
            self._progress.hide()
            self._send_btn.setEnabled(True)

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
            # 仅在 API 未能原生返回目标尺寸时做兜底缩放
            target_long = {"512": 512, "1K": 1024, "2K": 2048, "4K": 3840}.get(self._res_combo.currentText(), 0)
            long_side = max(img.width, img.height)
            if target_long > 0 and long_side != target_long:
                scale = target_long / long_side
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
                action = "缩小" if target_long < long_side else "放大"
                self._log(f"已将图像{action}：{long_side}px → {target_long}px（长边，{self._res_combo.currentText()}）")
            self._last_image_bytes = img_bytes
            # 记录 AI 轮次（仅 img_bytes，text 可为 None）
            self._current_turns.append({"role": "ai", "text": text, "img_bytes": img_bytes})
            tag = f"[{index}/{total}] " if total > 1 else ""
            self._log(f"{tag}图像生成成功，尺寸: {img.width}×{img.height}，大小: {len(img_bytes)//1024} KB", "ok")

            # 自动保存到 exe/脚本同目录下的 output 子目录
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fmt = self._format_combo.currentText()
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
        self._autosave_session()

    def _do_save_image(self, img_bytes: bytes):
        if not img_bytes:
            return
        fmt = self._format_combo.currentText()
        ext_map = {"PNG": ".png", "JPEG": ".jpg", "WebP": ".webp"}
        ext = ext_map.get(fmt, ".png")
        path, _ = QFileDialog.getSaveFileName(self, "保存图片", f"output{ext}", f"{fmt} (*{ext});;所有文件 (*.*)")
        if not path:
            return
        img = Image.open(io.BytesIO(img_bytes))
        if fmt == "JPEG":
            img = img.convert("RGB")
        img.save(path, format=fmt)
        self._status(f"已保存：{path}")

    def _save_image(self):
        if not self._last_image_bytes:
            QMessageBox.information(self, "提示", "还没有生成图片")
            return
        self._do_save_image(self._last_image_bytes)

    def _preview_image(self, img_key_or_bytes):
        if isinstance(img_key_or_bytes, str):
            img_bytes = self._chat_image_store.get(img_key_or_bytes)
        else:
            img_bytes = img_key_or_bytes
        if not img_bytes:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("图片预览")
        dlg.setStyleSheet("background:#000;")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        qimg = QImage.fromData(img_bytes)
        pix = QPixmap.fromImage(qimg)
        screen = QApplication.primaryScreen().geometry()
        max_w = int(screen.width() * 0.9)
        max_h = int(screen.height() * 0.85)
        pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lbl.setPixmap(pix)
        lbl.setCursor(QCursor(Qt.PointingHandCursor))
        lbl.mousePressEvent = lambda e: dlg.accept()
        layout.addWidget(lbl)

        orig_qimg = QImage.fromData(img_bytes)
        info = QLabel(f"{orig_qimg.width()}×{orig_qimg.height()}  {len(img_bytes)//1024} KB  —  点击图片或按 Esc 关闭")
        info.setStyleSheet("background:#111; color:#aaa; font-size:9pt; padding:4px 8px;")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        QShortcut(QKeySequence("Escape"), dlg, dlg.accept)
        dlg.exec()

    def _show_img_menu(self, img_key, pos):
        menu = QMenu(self)
        menu.addAction("预览图片", lambda: self._preview_image(img_key))
        menu.addAction("另存为…", lambda: self._do_save_image(self._chat_image_store.get(img_key, b'')))
        menu.addSeparator()
        menu.addAction("复制图片到剪贴板", lambda: self._copy_image_to_clipboard(self._chat_image_store.get(img_key, b'')))
        menu.exec(pos)

    def _copy_image_to_clipboard(self, img_bytes: bytes):
        if not img_bytes:
            return
        try:
            import win32clipboard
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="BMP")
            dib = buf.getvalue()[14:]
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
            win32clipboard.CloseClipboard()
            self._status("图片已复制到剪贴板")
        except ImportError:
            QMessageBox.information(self, "提示", "需要安装 pywin32 才能使用剪贴板功能\n运行：pip install pywin32")
        except Exception as e:
            self._log(f"复制剪贴板失败: {e}", "error")

    def _change_key(self):
        pw_dlg = _PasswordDialog(self)
        if pw_dlg.exec() != QDialog.Accepted or not pw_dlg.result_password:
            return
        current_key = load_api_key_with_password(pw_dlg.result_password)
        if current_key is None:
            QMessageBox.critical(self, "密码错误", "密码不正确，无法查看 API Key")
            return
        dlg = _EditKeyDialog(self, current_key)
        if dlg.exec() == QDialog.Accepted and dlg.result:
            new_key, new_pw = dlg.result
            final_pw = new_pw if new_pw else pw_dlg.result_password
            save_api_key(new_key, final_pw)
            self._api_key = new_key
            self._log("API Key 已更新", "ok")
            self._status("API Key 已更新")

    # ── 会话 ──────────────────────────────────
    def _capture_state(self, prompt: str = "") -> dict:
        return {
            "prompt":     prompt,
            "style_key":  self._style_combo.currentText(),
            "model":      self._model_combo.currentText(),
            "resolution": self._res_combo.currentText(),
            "ratio":      self._ratio_combo.currentText(),
            "fmt":        self._format_combo.currentText(),
            "ref_images": list(self._ref_images),
        }

    def _restore_session(self, state: dict):
        """从历史数据恢复会话（仅显示，不恢复 ChatSession 上下文）；
        加载后若用户继续生成，将作为新对话保存（新时间戳），不覆盖原历史文件。"""
        style_key = state.get("style_key", "")
        if style_key in ["(无风格)", ""] or style_key in list(STYLE_PRESETS.keys()):
            idx = self._style_combo.findText(style_key if style_key else "(无风格)")
            if idx >= 0:
                self._style_combo.setCurrentIndex(idx)

        if state.get("model") in list(MODELS.keys()):
            self._model_combo.setCurrentText(state["model"])
        if state.get("resolution") in (RESOLUTIONS_FLASH + RESOLUTIONS_PRO):
            self._res_combo.setCurrentText(state["resolution"])
        if state.get("ratio") in ASPECT_RATIOS:
            self._ratio_combo.setCurrentText(state["ratio"])
        if state.get("fmt") in OUTPUT_FORMATS:
            self._format_combo.setCurrentText(state["fmt"])

        self._clear_ref()
        for r in state.get("ref_images", []):
            if Path(r["path"]).exists():
                self._ref_images.append(r)
                item = QTreeWidgetItem([r["type"], Path(r["path"]).name])
                self._ref_tree.addTopLevelItem(item)
        self._ref_count_label.setText(f"{len(self._ref_images)} / {self.MAX_REF_IMAGES}")

        # 重置对话状态（加载历史后若继续生成，分配新时间戳，不覆盖历史文件）
        self._chat_session = None
        self._genai_client = None
        self._session_cfg  = ()
        self._current_turns.clear()
        self._session_ts = ""
        self._last_image_bytes = None
        self._chat_image_store.clear()

        # 清空聊天窗口，重放历史轮次
        self._chat_view.clear()
        cursor = self._chat_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        div_fmt = QTextCharFormat()
        div_fmt.setForeground(QColor("#8e8e93"))
        div_fmt.setFontPointSize(8)
        cursor.insertText(f"[历史对话 {state.get('timestamp','')}]\n", div_fmt)
        self._chat_view.setTextCursor(cursor)

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
        # 启动时风格始终重置为无风格
        self._style_combo.setCurrentIndex(0)

    def _open_history(self):
        dlg = _HistoryDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        if not dlg.result:
            return
        self._autosave_session()
        if self._current_turns:
            reply = QMessageBox.question(self, "切换对话",
                "加载历史对话将清空当前聊天视图。\n\n当前对话已自动保存，可在历史记录中重新找到。\n\n是否继续加载？",
                QMessageBox.Ok | QMessageBox.Cancel)
            if reply != QMessageBox.Ok:
                return
        self._restore_session(dlg.result)
        self._log(f"已加载历史会话 ({dlg.result.get('timestamp', '')})", "ok")

    def _add_ref_image(self):
        if len(self._ref_images) >= self.MAX_REF_IMAGES:
            QMessageBox.warning(self, "已达上限", f"最多只能添加 {self.MAX_REF_IMAGES} 张参考图")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择参考图片（可多选）", "", self.REF_EXTS)
        if not paths:
            return
        type_dlg = _RefTypeDialog(self, self.REF_TYPES)
        if type_dlg.exec() != QDialog.Accepted or not type_dlg.result:
            return
        ref_type = type_dlg.result
        added = 0
        for path in paths:
            if len(self._ref_images) >= self.MAX_REF_IMAGES:
                QMessageBox.warning(self, "已达上限", f"已添加至上限 {self.MAX_REF_IMAGES} 张")
                break
            self._ref_images.append({"path": path, "type": ref_type})
            item = QTreeWidgetItem([ref_type, Path(path).name])
            self._ref_tree.addTopLevelItem(item)
            added += 1
        self._ref_count_label.setText(f"{len(self._ref_images)} / {self.MAX_REF_IMAGES}")
        self._log(f"已添加 {added} 张参考图（{ref_type}）", "info")

    def _remove_ref_image(self):
        selected = self._ref_tree.selectedItems()
        if not selected:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"是否删除选中的 {len(selected)} 张参考图？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for item in selected:
            idx = self._ref_tree.indexOfTopLevelItem(item)
            self._ref_tree.takeTopLevelItem(idx)
            if idx < len(self._ref_images):
                self._ref_images.pop(idx)
        self._ref_count_label.setText(f"{len(self._ref_images)} / {self.MAX_REF_IMAGES}")

    def _clear_ref(self):
        if not self._ref_images:
            return
        reply = QMessageBox.question(
            self, "确认清空",
            f"是否清空全部 {len(self._ref_images)} 张参考图？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._ref_tree.clear()
        self._ref_images.clear()
        self._ref_count_label.setText(f"0 / {self.MAX_REF_IMAGES}")

    def _toggle_log(self):
        if self._log_dialog.isVisible():
            self._log_dialog.hide()
        else:
            geo = self.geometry()
            self._log_dialog.move(geo.x() + geo.width() - 556, geo.y() + geo.height() - 316)
            self._log_dialog.show()
            self._log_dialog.raise_()

    def _log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_dialog.append(ts, msg, level)

    def _status(self, msg: str):
        self._status_bar.showMessage(msg)

    def _autosave_session(self):
        """每次对话有新内容时立即更新 session 文件（覆盖同一时间戳的文件）"""
        if not self._current_turns:
            return
        try:
            meta = self._capture_state()
            if not self._session_ts:
                self._session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            meta["timestamp"] = self._session_ts
            save_session(self._current_turns, meta)
        except Exception as e:
            self._log(f"实时保存失败: {e}", "warn")

    def closeEvent(self, event):
        if self._current_turns:
            try:
                meta = self._capture_state()
                meta["timestamp"] = self._session_ts
                save_session(self._current_turns, meta)
            except Exception:
                pass
        event.accept()


# ─────────────────────────────────────────────
if __name__ == "__main__":
    # Qt6 默认已开启高 DPI 支持，无需手动设置
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    window = App()
    window.show()
    sys.exit(app.exec())
