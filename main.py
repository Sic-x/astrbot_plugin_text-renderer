import asyncio
import os
from pathlib import Path
from PIL import ImageFont
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star, StarTools, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .config import constants
import datetime
import time
from .utils.image_utils import (
    _parse_text_to_render_units,
    _calculate_layout,
    _draw_image_content,
    apply_effects,
)

THEMES = {
    "default": {"bg": (255, 255, 255), "text": (0, 0, 0)},
    "light": {"bg": (253, 246, 227), "text": (101, 123, 131)},
    "dark": {"bg": (40, 44, 52), "text": (171, 178, 191)},
    "light-gradient": {"bg": ((240, 240, 250), (210, 220, 235)), "text": (80, 80, 100)},
    "dark-gradient": {"bg": ((43, 48, 59), (20, 22, 28)), "text": (200, 200, 210)},
}


# --- 核心文本转图片函数 ---
def text_to_image(
    text_content: str,
    output_path: Path,
    font_path: Path,
    font_path_bold: Path,
    font_size: int,
    padding: int,
    theme: str,
    use_frame: bool,
    corner_radius: int,
    width: int,
    text_line_spacing: int,
    divider_margin: int,
    **kwargs,
):
    """
    将给定的文本内容转换为图片。

    该函数处理文本解析、自动换行、Markdown粗体、分隔符、空行、
    多种主题、圆角、边框和阴影效果。

    Args:
        text_content (str): 要渲染的原始文本。
        output_path (Path): 输出图片的保存路径。
        font_path (Path): 常规字体的路径。
        font_path_bold (Path): 粗体字体的路径。
        font_size (int): 字体大小。
        padding (int): 图片内容区域的内边距。
        theme (str): 颜色主题 ('default', 'light', 'dark', 'light-gradient', 'dark-gradient')。
        use_frame (bool): 是否使用带阴影的边框。
        corner_radius (int): 圆角半径。
        width (int): 图片的总宽度。
        text_line_spacing (int): 文本行之间的额外间距。
        divider_margin (int): 分隔符上下的外边距。
    """
    # 1. 主题和字体设置
    selected_theme = THEMES.get(theme, THEMES["default"])

    try:
        font_regular = (
            ImageFont.truetype(str(font_path), font_size)
            if font_path and Path(font_path).exists()
            else ImageFont.load_default()
        )
    except (IOError, TypeError):
        logger.error(f"常规字体 '{font_path}' 加载失败，使用默认字体。")
        font_regular = ImageFont.load_default()

    try:
        font_bold = (
            ImageFont.truetype(str(font_path_bold), font_size)
            if font_path_bold and Path(font_path_bold).exists()
            else font_regular
        )
    except (IOError, TypeError):
        logger.error(f"粗体字体 '{font_path_bold}' 加载失败，退回使用常规字体。")
        font_bold = font_regular

    fonts = {"normal": font_regular, "bold": font_bold}

    # 2. 文本解析
    render_units = _parse_text_to_render_units(text_content)

    # 3. 计算布局
    max_content_width = width - (2 * padding)
    processed_lines, total_height = _calculate_layout(
        render_units, max_content_width, fonts, text_line_spacing, divider_margin
    )
    img_height = total_height + (2 * padding)

    # 4. 绘制图像
    content_image = _draw_image_content(
        processed_lines, width, img_height, padding, fonts, selected_theme, text_line_spacing, divider_margin
    )

    # 5. 应用最终效果并保存
    final_image = apply_effects(content_image, use_frame, corner_radius)
    if final_image.mode == "RGBA" and not output_path.suffix.lower() == ".png":
        output_path = output_path.with_suffix(".png")
    final_image.save(output_path)
    logger.info(f"图片已成功保存到: {output_path.resolve()}")


# --- AstrBot 插件主类 ---
@register(constants.PLUGIN_NAME, constants.PLUGIN_AUTHOR, constants.PLUGIN_DESCRIPTION, constants.PLUGIN_VERSION)
class TextToImage(Star):
    """
    TextToImage 插件的主类。
    负责加载配置、初始化路径、注册命令以及处理命令的调用。
    """

    def __init__(self, context, config: AstrBotConfig) -> None:
        """初始化插件实例，加载配置和路径。"""
        super().__init__(context=context)
        self.config = config
        self._load_config()
        self._initialize_paths()

    def _load_config(self):
        """从 AstrBot 配置中加载并设置插件所需的参数。"""
        self.text_file_path_template = self.config.get("text_file_path")
        self.font_path = self.config.get("font_path")
        self.font_path_bold = self.config.get("font_path_bold")
        self.font_size = self.config.get("font_size", 24)
        self.theme = self.config.get("theme", "dark-gradient")
        self.width = self.config.get("width", 1080)
        self.padding = self.config.get("padding", 40)
        self.use_frame = self.config.get("use_frame", True)
        self.corner_radius = self.config.get("corner_radius", 15)
        self.text_line_spacing = self.config.get("text_line_spacing", 5)
        self.divider_margin = self.config.get("divider_margin", 10)

    def _initialize_paths(self):
        """初始化插件所需的数据和输出目录。"""
        self.base_dir = StarTools.get_data_dir(constants.PLUGIN_NAME)
        self.output_dir = self.base_dir / constants.OUTPUT_DIR_NAME
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_dynamic_path(self, path_template: str) -> Path | None:
        """
        解析可能包含动态占位符的路径模板。
        - `${today_prefix}`: 替换为当天的日期 (YYYYMMDD)。
        - `*` 或 `?`: 解析为glob模式，并返回最新修改的文件。
        - `~`: 替换为用户主目录。
        - 相对路径: 解析为相对于 AstrBot 数据目录的路径。
        """
        today_prefix = datetime.date.today().strftime("%Y%m%d")
        resolved_path_str = path_template.replace("${today_prefix}", today_prefix)

        if resolved_path_str.startswith("~"):
            resolved_path_str = str(Path.home()) + resolved_path_str[1:]

        path_obj = Path(resolved_path_str)

        # 如果路径不是绝对路径，则相对于 AstrBot 的数据目录
        base_path = Path(get_astrbot_data_path())
        if not path_obj.is_absolute():
            path_obj = base_path / path_obj

        # 处理通配符，查找最新文件
        if "*" in path_obj.name or "?" in path_obj.name:
            start_time = time.time()
            file_list = list(path_obj.parent.glob(path_obj.name))
            if not file_list:
                logger.warning(f"找不到匹配 '{path_obj}' 的文件。")
                return None

            latest_file = max(file_list, key=lambda p: p.stat().st_mtime)
            duration = time.time() - start_time
            logger.info(
                f"动态路径 '{path_template}' 在 {duration:.4f} 秒内解析为最新文件: {latest_file} (已检查 {len(file_list)} 个文件)"
            )
            return latest_file
        else:
            return path_obj

    @filter.command_group("daily")
    def daily(self):
        """'daily' 命令组。"""
        pass

    @daily.command("dev", "发送每日开发日报")
    async def daily_dev(self, event: AstrMessageEvent):
        """
        处理 'daily dev' 命令。
        从指定的文本文件生成日报图片并发送到频道。
        如果文件大小超过10KB，则会裁剪成多张图片发送。
        """
        if not event.is_admin():
            yield event.plain_result("抱歉，只有管理员才能使用此命令。")
            return

        if not self.text_file_path_template:
            logger.warning("文本文件路径模板未在配置中设置，'daily dev' 命令已跳过。")
            return

        text_file = self._resolve_dynamic_path(self.text_file_path_template)

        if not text_file or not text_file.exists():
            err_msg = f"错误：文件未找到 '{text_file}' (由模板 '{self.text_file_path_template}' 解析得到)"
            logger.error(err_msg)
            yield event.plain_result(err_msg)
            return

        try:
            file_size = os.path.getsize(text_file)
            content = text_file.read_text(encoding="utf-8")
            loop = asyncio.get_running_loop()
            MAX_CHUNK_SIZE = 10 * 1024  # 10KB

            if file_size <= MAX_CHUNK_SIZE:
                # 文件较小，直接生成单张图片
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = self.output_dir / f"daily_dev_{timestamp}.png"
                await loop.run_in_executor(
                    None,
                    text_to_image,
                    content,
                    output_filename,
                    self.font_path,
                    self.font_path_bold,
                    self.font_size,
                    self.padding,
                    self.theme,
                    self.use_frame,
                    self.corner_radius,
                    self.width,
                    self.text_line_spacing,
                    self.divider_margin,
                )
                yield event.image_result(str(output_filename))
            else:
                # 文件较大，分块处理
                lines = content.split('\n')
                chunks = []
                current_chunk_lines = []
                current_chunk_size = 0

                for line in lines:
                    line_bytes = line.encode('utf-8')
                    if current_chunk_size + len(line_bytes) + 1 > MAX_CHUNK_SIZE and current_chunk_lines:
                        chunks.append("\n".join(current_chunk_lines))
                        current_chunk_lines = [line]
                        current_chunk_size = len(line_bytes)
                    else:
                        current_chunk_lines.append(line)
                        current_chunk_size += len(line_bytes) + 1
                
                if current_chunk_lines:
                    chunks.append("\n".join(current_chunk_lines))

                for i, chunk_content in enumerate(chunks):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = self.output_dir / f"daily_dev_{timestamp}_part_{i+1}.png"
                    
                    await loop.run_in_executor(
                        None,
                        text_to_image,
                        chunk_content,
                        output_filename,
                        self.font_path,
                        self.font_path_bold,
                        self.font_size,
                        self.padding,
                        self.theme,
                        self.use_frame,
                        self.corner_radius,
                        self.width,
                        self.text_line_spacing,
                        self.divider_margin,
                    )
                    yield event.image_result(str(output_filename))
                    await asyncio.sleep(1) # 防止发送过于频繁

        except Exception as e:
            logger.error(f"处理 'daily dev' 命令时发生未知错误: {e}", exc_info=True)
            yield event.plain_result(f"生成日报时出错: {str(e)}")

    async def terminate(self):
        """插件终止时调用的清理函数。"""
        logger.info("TextToImage 插件已终止。")
