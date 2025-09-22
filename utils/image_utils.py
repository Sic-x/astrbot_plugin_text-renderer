import re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

NO_START_CHARS = {
    ",", ".", "!", "?", ";", ":", "}", "]", ")", ">",
    "》", "】", "』", "，", "。", "！", "？", "；", "：",
    "”", "’", "）", "』", "】", "〉", "》", "、",
}


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
    shadow_draw = ImageДraw.Draw(shadow)
    shadow_box = (frame_padding, frame_padding, frame_padding + image.width, frame_padding + image.height)
    shadow_draw.rounded_rectangle(shadow_box, radius=corner_radius, fill=shadow_color)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

    frame_with_shadow.paste(shadow, (shadow_offset, shadow_offset), shadow)
    frame_with_shadow.paste(image, (frame_padding, frame_padding), image)

    return frame_with_shadow


def _parse_text_to_render_units(text_content: str):
    """将原始文本解析成一个渲染单元的结构化列表。"""
    
    def parse_line_to_runs(line_text):
        runs = []
        parts = re.split(r"(\*\*.*?\*\*)", line_text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                runs.append({"text": part[2:-2], "style": "bold"})
            elif part:
                runs.append({"text": part, "style": "normal"})
        return [r for r in runs if r["text"]]

    render_units = []
    original_lines = text_content.split("\n")
    for original_line in original_lines:
        if not original_line.strip() and original_line == "":
            render_units.append([{"type": "empty"}])
            continue
        if len(original_line.strip()) >= 3 and set(original_line.strip()) <= {"-", "—"}:
            render_units.append([{"type": "divider"}])
            continue
        
        runs = parse_line_to_runs(original_line)
        render_units.append(runs)
        
    return render_units


def _calculate_layout(render_units, max_width, fonts, text_line_spacing, divider_margin):
    """计算换行和每个元素的位置，并返回最终的图像尺寸。"""
    
    def get_run_width(run):
        return fonts[run["style"]].getbbox(run["text"])[2]

    processed_lines = []
    for runs in render_units:
        if "type" in runs[0]:
            processed_lines.append(runs)
            continue

        lines = []
        current_line = []
        current_width = 0

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
            start = 0
            while start < len(text):
                # Find the maximum number of characters that fit on the current line
                end = start
                slice_width = 0
                while end < len(text):
                    char_width = font.getbbox(text[end])[2]
                    # Break if char doesn't fit, but always include at least one char
                    if current_width + slice_width + char_width > max_width and end > start:
                        break
                    slice_width += char_width
                    end += 1

                # If the character that would start the new line is a forbidden character,
                # wrap one character earlier to keep it with the previous text.
                if end < len(text) and text[end] in NO_START_CHARS:
                    if end > start:
                        end -= 1

                chunk = text[start:end]
                
                # Add the resulting chunk to the current line
                if chunk:
                    if current_line and current_line[-1]["style"] == run["style"]:
                        current_line[-1]["text"] += chunk
                    else:
                        current_line.append({"text": chunk, "style": run["style"]})
                    current_width += font.getbbox(chunk)[2]

                # If the run was broken, finalize the current line and start a new one
                if end < len(text):
                    lines.append(current_line)
                    current_line = []
                    current_width = 0
                
                start = end

        if current_line:
            lines.append(current_line)
        processed_lines.extend(lines)

    def get_line_height(line_runs):
        max_h = 0
        for run in line_runs:
            font = fonts[run.get("style", "normal")]
            bbox = font.getbbox(run["text"])
            h = bbox[3] - bbox[1]
            if h > max_h:
                max_h = h
        return max_h

    def is_divider(line):
        return line and "type" in line[0] and line[0]["type"] == "divider"

    def is_empty_line(line):
        return line and "type" in line[0] and line[0]["type"] == "empty"

    total_height = 0
    for i, line in enumerate(processed_lines):
        is_last_line = i == len(processed_lines) - 1

        if is_divider(line):
            if i > 0 and not is_empty_line(processed_lines[i - 1]):
                total_height -= text_line_spacing
            total_height += get_line_height([{"text": "─", "style": "normal"}]) + (2 * divider_margin)
        elif is_empty_line(line):
            total_height += get_line_height([{"text": " ", "style": "normal"}])
        else:
            total_height += get_line_height(line)

        if not is_last_line:
            total_height += text_line_spacing
            
    return processed_lines, total_height


def _draw_image_content(processed_lines, width, height, padding, fonts, theme, text_line_spacing, divider_margin):
    """在图像上进行实际的绘制操作。"""
    
    selected_theme = theme
    background_config = selected_theme["bg"]
    text_color = selected_theme["text"]
    is_gradient = isinstance(background_config, tuple) and isinstance(background_config[0], tuple)

    if is_gradient:
        content_image = create_gradient_image(
            int(width), int(height), background_config[0], background_config[1]
        )
    else:
        content_image = Image.new("RGB", (int(width), int(height)), background_config)
    draw = ImageDraw.Draw(content_image)

    def get_line_height(line_runs):
        max_h = 0
        for run in line_runs:
            font = fonts[run.get("style", "normal")]
            bbox = font.getbbox(run["text"])
            h = bbox[3] - bbox[1]
            if h > max_h:
                max_h = h
        return max_h

    def is_divider(line):
        return line and "type" in line[0] and line[0]["type"] == "divider"

    def is_empty_line(line):
        return line and "type" in line[0] and line[0]["type"] == "empty"

    divider_char = "─"
    char_width = fonts["normal"].getbbox(divider_char)[2]
    divider_line_text = divider_char * int((width - 2 * padding) / char_width) if char_width > 0 else ""

    current_y = padding
    for i, line in enumerate(processed_lines):
        is_last_line = i == len(processed_lines) - 1

        if is_divider(line):
            line_height = get_line_height([{"text": "─", "style": "normal"}])
            if i > 0 and not is_empty_line(processed_lines[i - 1]):
                current_y -= text_line_spacing
            current_y += divider_margin
            draw.text((padding, current_y), divider_line_text, font=fonts["normal"], fill=text_color)
            current_y += line_height + divider_margin
        elif is_empty_line(line):
            line_height = get_line_height([{"text": " ", "style": "normal"}])
            current_y += line_height
        else:
            line_height = get_line_height(line)
            current_x = padding
            for run in line:
                font = fonts[run["style"]]
                draw.text((current_x, current_y), run["text"], font=font, fill=text_color)
                current_x += fonts[run["style"]].getbbox(run["text"])[2]
            current_y += line_height

        if not is_last_line:
            current_y += text_line_spacing
            
    return content_image