import asyncio
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star, StarTools, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .config import constants
import datetime
import re


# --- 图像效果函数 ---
def create_gradient_image(width, height, color1, color2):
    """创建一个从 color1 到 color2 的垂直渐变图像。"""
    c1 = np.array(color1, dtype=np.uint8)
    c2 = np.array(color2, dtype=np.uint8)
    gradient = np.linspace(c1, c2, height, dtype=np.uint8)
    image_array = np.tile(gradient, (width, 1, 1)).transpose(1, 0, 2)
    return Image.fromarray(image_array)


def apply_effects(image: Image, use_frame: bool, corner_radius: int):
    """为图像应用圆角和可选的带阴影的边框。"""
    if not use_frame and corner_radius == 0:
        return image

    image = image.convert("RGBA")
    # 应用圆角
    if corner_radius > 0:
        mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, image.width, image.height), radius=corner_radius, fill=255)
        image.putalpha(mask)

    if not use_frame:
        return image

    # 应用带阴影的边框
    frame_padding = 20
    shadow_offset = 10
    blur_radius = 15
    shadow_color = (0, 0, 0, 50)

    frame_with_shadow = Image.new(
        "RGBA",
        (image.width + 2 * frame_padding + shadow_offset, image.height + 2 * frame_padding + shadow_offset),
        (0, 0, 0, 0),
    )

    shadow = Image.new("RGBA", frame_with_shadow.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_box = (frame_padding, frame_padding, frame_padding + image.width, frame_padding + image.height)
    shadow_draw.rounded_rectangle(shadow_box, radius=corner_radius, fill=shadow_color)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

    frame_with_shadow.paste(shadow, (shadow_offset, shadow_offset), shadow)
    frame_with_shadow.paste(image, (frame_padding, frame_padding), image)

    return frame_with_shadow


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
    themes = {
        "default": {"bg": (255, 255, 255), "text": (0, 0, 0)},
        "light": {"bg": (253, 246, 227), "text": (101, 123, 131)},
        "dark": {"bg": (40, 44, 52), "text": (171, 178, 191)},
        "light-gradient": {"bg": ((240, 240, 250), (210, 220, 235)), "text": (80, 80, 100)},
        "dark-gradient": {"bg": ((43, 48, 59), (20, 22, 28)), "text": (200, 200, 210)},
    }
    selected_theme = themes.get(theme, themes["default"])
    background_config = selected_theme["bg"]
    text_color = selected_theme["text"]
    is_gradient = isinstance(background_config, tuple) and isinstance(background_config[0], tuple)

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

    # 2. 文本预处理
    img_width = width
    max_content_width = img_width - (2 * padding)
    divider_placeholder = [{"type": "divider"}]
    empty_line_placeholder = [{"type": "empty"}]
    no_start_chars = {
        ",",
        ".",
        "!",
        "?",
        ";",
        ":",
        "}",
        "]",
        ")",
        ">",
        "》",
        "】",
        "』",
        "，",
        "。",
        "！",
        "？",
        "；",
        "：",
        "”",
        "’",
        "）",
        "』",
        "】",
        "〉",
        "》",
        "、",
    }

    def parse_line_to_runs(line_text):
        runs = []
        parts = re.split(r"(\*\*.*?\*\*)", line_text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                runs.append({"text": part[2:-2], "style": "bold"})
            elif part:
                runs.append({"text": part, "style": "normal"})
        return [r for r in runs if r["text"]]

    def get_run_width(run):
        return fonts[run["style"]].getbbox(run["text"])[2]

    def wrap_line(runs):
        lines = []
        current_line = []
        current_width = 0

        # 合并相邻的同一样式的 run
        merged_runs = []
        if runs:
            merged_runs.append(runs[0])
            for i in range(1, len(runs)):
                if runs[i]["style"] == merged_runs[-1]["style"]:
                    merged_runs[-1]["text"] += runs[i]["text"]
                else:
                    merged_runs.append(runs[i])

        for run in merged_runs:
            font = fonts[run["style"]]
            text = run["text"]

            i = 0
            while i < len(text):
                char = text[i]
                char_width = font.getbbox(char)[2]

                if current_width + char_width > max_content_width:
                    # 禁则处理
                    if char in no_start_chars and current_line:
                        # 找到当前行最后一个 run 和最后一个字符
                        last_run_index = len(current_line) - 1
                        while last_run_index >= 0 and not current_line[last_run_index]["text"]:
                            last_run_index -= 1

                        if last_run_index >= 0:
                            last_run = current_line[last_run_index]
                            last_char = last_run["text"][-1]

                            # 从当前行移除最后一个字符
                            last_run["text"] = last_run["text"][:-1]

                            # 将当前行添加到结果中
                            lines.append(current_line)

                            # 将被移除的字符作为新行的第一个 run
                            current_line = [{"text": last_char, "style": last_run["style"]}]
                            current_width = get_run_width(current_line[0])

                            # 重新处理当前字符
                            continue

                    lines.append(current_line)
                    current_line = []
                    current_width = 0

                if not current_line or current_line[-1]["style"] != run["style"]:
                    current_line.append({"text": char, "style": run["style"]})
                else:
                    current_line[-1]["text"] += char
                current_width += char_width
                i += 1

        if current_line:
            lines.append(current_line)
        return lines

    original_lines = text_content.split("\n")
    processed_lines = []
    for original_line in original_lines:
        if not original_line.strip() and original_line == "":
            processed_lines.append(empty_line_placeholder)
            continue
        if len(original_line.strip()) >= 3 and set(original_line.strip()) <= {"-", "—"}:
            processed_lines.append(divider_placeholder)
            continue

        runs = parse_line_to_runs(original_line)
        wrapped_lines = wrap_line(runs)
        processed_lines.extend(wrapped_lines)

    # 3. 计算总高度
    def get_line_height(line_runs):
        max_h = 0
        for run in line_runs:
            font = fonts[run.get("style", "normal")]
            bbox = font.getbbox(run["text"])
            h = bbox[3] - bbox[1]
            if h > max_h:
                max_h = h
        return max_h

    total_height = 0
    for i, line in enumerate(processed_lines):
        is_last_line = i == len(processed_lines) - 1

        if line and "type" in line[0] and line[0]["type"] == "divider":
            if i > 0 and "type" in processed_lines[i - 1][0] and processed_lines[i - 1][0]["type"] != "empty":
                total_height -= text_line_spacing
            total_height += get_line_height([{"text": "─", "style": "normal"}]) + (2 * divider_margin)
        elif line and "type" in line[0] and line[0]["type"] == "empty":
            total_height += get_line_height([{"text": " ", "style": "normal"}])
        else:
            total_height += get_line_height(line)

        if not is_last_line:
            total_height += text_line_spacing

    img_height = total_height + (2 * padding)

    # 4. 创建画布并绘制
    if is_gradient:
        content_image = create_gradient_image(
            int(img_width), int(img_height), background_config[0], background_config[1]
        )
    else:
        content_image = Image.new("RGB", (int(img_width), int(img_height)), background_config)
    draw = ImageDraw.Draw(content_image)

    divider_char = "─"
    char_width = font_regular.getbbox(divider_char)[2]
    divider_line_text = divider_char * int(max_content_width / char_width) if char_width > 0 else ""

    current_y = padding
    for i, line in enumerate(processed_lines):
        is_last_line = i == len(processed_lines) - 1

        if line and "type" in line[0] and line[0]["type"] == "divider":
            line_height = get_line_height([{"text": "─", "style": "normal"}])
            if i > 0 and "type" in processed_lines[i - 1][0] and processed_lines[i - 1][0]["type"] != "empty":
                current_y -= text_line_spacing
            current_y += divider_margin
            draw.text((padding, current_y), divider_line_text, font=font_regular, fill=text_color)
            current_y += line_height + divider_margin
        elif line and "type" in line[0] and line[0]["type"] == "empty":
            line_height = get_line_height([{"text": " ", "style": "normal"}])
            current_y += line_height
        else:
            line_height = get_line_height(line)
            current_x = padding
            for run in line:
                font = fonts[run["style"]]
                draw.text((current_x, current_y), run["text"], font=font, fill=text_color)
                current_x += get_run_width(run)
            current_y += line_height

        if not is_last_line:
            current_y += text_line_spacing

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
            file_list = list(path_obj.parent.glob(path_obj.name))
            if not file_list:
                logger.warning(f"找不到匹配 '{path_obj}' 的文件。")
                return None

            latest_file = max(file_list, key=lambda p: p.stat().st_mtime)
            logger.info(f"动态路径 '{path_template}' 解析为最新文件: {latest_file}")
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
        """
        if not event.is_admin():
            yield event.plain_result("抱歉，只有管理员才能使用此命令。")
            return

        if not self.text_file_path_template:
            logger.warning("文本文件路径模板未在配置中设置，'daily dev' 命令已跳过。")
            return

        # 解析源文件路径
        text_file = self._resolve_dynamic_path(self.text_file_path_template)

        if not text_file or not text_file.exists():
            err_msg = f"错误：文件未找到 '{text_file}' (由模板 '{self.text_file_path_template}' 解析得到)"
            logger.error(err_msg)
            yield event.plain_result(err_msg)
            return

        try:
            # 读取内容并生成带时间戳的输出文件名
            content = text_file.read_text(encoding="utf-8")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = self.output_dir / f"daily_dev_{timestamp}.png"

            # 在线程池中执行图像生成，避免阻塞事件循环
            loop = asyncio.get_event_loop()
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
            # 发送生成的图片
            yield event.image_result(str(output_filename))
        except Exception as e:
            logger.error(f"生成日报时出错: {str(e)}")
            yield event.plain_result(f"生成日报时出错: {str(e)}")
            logger.error(f"处理 'daily dev' 命令时发生未知错误: {e}", exc_info=True)
            yield event.plain_result(f"处理命令时发生内部错误: {e}")

    async def terminate(self):
        """插件终止时调用的清理函数。"""
        logger.info("TextToImage 插件已终止。")
