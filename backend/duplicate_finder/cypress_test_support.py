"""
Duplicate Finder - Cypress Test Support
为Cypress测试提供测试数据准备功能
"""

import os
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random


class TestImageGenerator:
    """测试图片生成器"""

    @staticmethod
    def generate_solid_color_image(filepath: str, width=100, height=100, color=(255, 0, 0)):
        """
        生成纯色图片

        Args:
            filepath: 保存路径
            width: 宽度
            height: 高度
            color: RGB颜色元组
        """
        img = Image.new('RGB', (width, height), color=color)
        img.save(filepath)
        return filepath

    @staticmethod
    def generate_random_image(filepath: str, width=100, height=100, seed=None):
        """
        生成随机噪声图片

        Args:
            filepath: 保存路径
            width: 宽度
            height: 高度
            seed: 随机种子（相同种子生成相同图片）
        """
        if seed is not None:
            random.seed(seed)

        pixels = []
        for _ in range(width * height):
            pixels.append((
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255)
            ))

        img = Image.new('RGB', (width, height))
        img.putdata(pixels)
        img.save(filepath)
        return filepath

    @staticmethod
    def generate_gradient_image(filepath: str, width=100, height=100,
                                direction='horizontal', start_color=(255, 0, 0),
                                end_color=(0, 0, 255)):
        """
        生成渐变图片

        Args:
            filepath: 保存路径
            width: 宽度
            height: 高度
            direction: 'horizontal' 或 'vertical'
            start_color: 起始颜色
            end_color: 结束颜色
        """
        img = Image.new('RGB', (width, height))
        pixels = []

        for y in range(height):
            for x in range(width):
                if direction == 'horizontal':
                    ratio = x / width
                else:  # vertical
                    ratio = y / height

                r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
                g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
                b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
                pixels.append((r, g, b))

        img.putdata(pixels)
        img.save(filepath)
        return filepath

    @staticmethod
    def generate_labeled_image(filepath: str, group_label: str, file_label: str,
                              width=300, height=200, bg_color=None, text_color=(255, 255, 255)):
        """
        生成带文字标注的图片，便于测试时识别

        Args:
            filepath: 保存路径
            group_label: 组标签（如 "Group A", "Group 1"）
            file_label: 文件标签（如 "a_001.jpg", "Master"）
            width: 宽度
            height: 高度
            bg_color: 背景颜色（如果为None，自动根据group_label生成）
            text_color: 文字颜色
        """
        # 如果没有指定背景色，根据组标签生成不同的颜色
        if bg_color is None:
            # 使用hash生成稳定的颜色
            hash_val = hash(group_label) % 1000
            hue = (hash_val * 137) % 360  # Golden angle for good color distribution

            # HSV to RGB conversion (simplified)
            import colorsys
            r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.6, 0.8)
            bg_color = (int(r * 255), int(g * 255), int(b * 255))

        # 创建图片
        img = Image.new('RGB', (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # 尝试使用系统字体，如果失败则使用默认字体
        try:
            # macOS 系统字体
            font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        except:
            try:
                # Linux 系统字体
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            except:
                # 使用默认字体
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

        # 绘制组标签（大字）
        bbox1 = draw.textbbox((0, 0), group_label, font=font_large)
        text_width1 = bbox1[2] - bbox1[0]
        text_height1 = bbox1[3] - bbox1[1]
        x1 = (width - text_width1) // 2
        y1 = height // 3 - text_height1 // 2
        draw.text((x1, y1), group_label, fill=text_color, font=font_large)

        # 绘制文件标签（小字）
        bbox2 = draw.textbbox((0, 0), file_label, font=font_small)
        text_width2 = bbox2[2] - bbox2[0]
        text_height2 = bbox2[3] - bbox2[1]
        x2 = (width - text_width2) // 2
        y2 = height * 2 // 3 - text_height2 // 2
        draw.text((x2, y2), file_label, fill=text_color, font=font_small)

        img.save(filepath)
        return filepath

    @staticmethod
    def generate_similar_images(base_filepath: str, output_dir: str, count=3,
                               similarity='high'):
        """
        生成相似图片组

        Args:
            base_filepath: 基础图片路径
            output_dir: 输出目录
            count: 生成数量
            similarity: 'identical', 'high', 'medium', 'low'

        Returns:
            生成的图片路径列表
        """
        base_img = Image.open(base_filepath)
        width, height = base_img.size
        generated = []

        for i in range(count):
            output_path = os.path.join(output_dir, f"similar_{i+1}.jpg")

            if similarity == 'identical':
                # 完全相同
                base_img.save(output_path)

            elif similarity == 'high':
                # 高相似度：微小调整亮度
                img = base_img.copy()
                # 调整亮度 ±5%
                from PIL import ImageEnhance
                enhancer = ImageEnhance.Brightness(img)
                factor = 1.0 + (random.random() * 0.1 - 0.05)  # 0.95-1.05
                img = enhancer.enhance(factor)
                img.save(output_path)

            elif similarity == 'medium':
                # 中等相似度：调整亮度和对比度
                img = base_img.copy()
                from PIL import ImageEnhance
                # 调整亮度 ±15%
                enhancer = ImageEnhance.Brightness(img)
                factor = 1.0 + (random.random() * 0.3 - 0.15)  # 0.85-1.15
                img = enhancer.enhance(factor)
                # 调整对比度
                enhancer = ImageEnhance.Contrast(img)
                factor = 1.0 + (random.random() * 0.2 - 0.1)  # 0.9-1.1
                img = enhancer.enhance(factor)
                img.save(output_path)

            elif similarity == 'low':
                # 低相似度：显著调整
                img = base_img.copy()
                from PIL import ImageEnhance
                # 调整亮度 ±30%
                enhancer = ImageEnhance.Brightness(img)
                factor = 1.0 + (random.random() * 0.6 - 0.3)  # 0.7-1.3
                img = enhancer.enhance(factor)
                # 调整对比度
                enhancer = ImageEnhance.Contrast(img)
                factor = 1.0 + (random.random() * 0.4 - 0.2)  # 0.8-1.2
                img = enhancer.enhance(factor)
                # 添加轻微噪声
                img.save(output_path)

            generated.append(output_path)

        return generated


class TestDataSetup:
    """测试数据集设置"""

    @staticmethod
    def create_minimal_test_set(base_dir: str):
        """
        创建最小测试集（用于基础功能测试）

        结构：
        - 3个identical重复组（每组3张）
        - 2个high similarity组（每组3张）
        - 5个unique图片
        总计：23张图片
        """
        base_path = Path(base_dir)
        base_path.mkdir(parents=True, exist_ok=True)

        gen = TestImageGenerator()
        result = {
            'total': 0,
            'groups': [],
            'unique': []
        }

        # Identical组1
        group1_base = str(base_path / "base_red.jpg")
        gen.generate_solid_color_image(group1_base, color=(255, 0, 0))
        group1 = [
            str(base_path / f"identical_1_{i}.jpg")
            for i in range(1, 4)
        ]
        for path in group1:
            shutil.copy(group1_base, path)
        result['groups'].append({
            'type': 'identical',
            'files': group1,
            'expected_similarity': 100
        })

        # Identical组2
        group2_base = str(base_path / "base_blue.jpg")
        gen.generate_solid_color_image(group2_base, color=(0, 0, 255))
        group2 = [
            str(base_path / f"identical_2_{i}.jpg")
            for i in range(1, 4)
        ]
        for path in group2:
            shutil.copy(group2_base, path)
        result['groups'].append({
            'type': 'identical',
            'files': group2,
            'expected_similarity': 100
        })

        # Identical组3
        group3_base = str(base_path / "base_green.jpg")
        gen.generate_solid_color_image(group3_base, color=(0, 255, 0))
        group3 = [
            str(base_path / f"identical_3_{i}.jpg")
            for i in range(1, 4)
        ]
        for path in group3:
            shutil.copy(group3_base, path)
        result['groups'].append({
            'type': 'identical',
            'files': group3,
            'expected_similarity': 100
        })

        # High similarity组1
        group4_base = str(base_path / "base_gradient1.jpg")
        gen.generate_gradient_image(group4_base, direction='horizontal')
        group4 = gen.generate_similar_images(
            group4_base,
            str(base_path),
            count=3,
            similarity='high'
        )
        result['groups'].append({
            'type': 'high_similarity',
            'files': group4,
            'expected_similarity': 95
        })

        # High similarity组2
        group5_base = str(base_path / "base_gradient2.jpg")
        gen.generate_gradient_image(group5_base, direction='vertical')
        group5 = gen.generate_similar_images(
            group5_base,
            str(base_path),
            count=3,
            similarity='high'
        )
        result['groups'].append({
            'type': 'high_similarity',
            'files': group5,
            'expected_similarity': 95
        })

        # Unique图片
        for i in range(5):
            unique_path = str(base_path / f"unique_{i+1}.jpg")
            gen.generate_random_image(unique_path, seed=1000+i)
            result['unique'].append(unique_path)

        result['total'] = sum(len(g['files']) for g in result['groups']) + len(result['unique'])

        # 清理临时基础图片
        os.remove(group1_base)
        os.remove(group2_base)
        os.remove(group3_base)
        os.remove(group4_base)
        os.remove(group5_base)

        return result

    @staticmethod
    def create_performance_test_set(base_dir: str, count=50):
        """
        创建性能测试集（用count张图片模拟大量文件）

        Args:
            base_dir: 基础目录
            count: 图片数量（建议50-100，配合test mode的delay）
        """
        base_path = Path(base_dir)
        base_path.mkdir(parents=True, exist_ok=True)

        gen = TestImageGenerator()
        result = {
            'total': count,
            'files': []
        }

        # 生成随机图片
        for i in range(count):
            filepath = str(base_path / f"perf_test_{i+1:04d}.jpg")
            gen.generate_random_image(filepath, seed=2000+i)
            result['files'].append(filepath)

        return result

    @staticmethod
    def cleanup_test_data(base_dir: str):
        """清理测试数据"""
        if os.path.exists(base_dir):
            shutil.rmtree(base_dir)
            print(f"[CLEANUP] Removed test directory: {base_dir}")


if __name__ == '__main__':
    # 测试代码示例
    import tempfile

    # 创建临时测试目录
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Creating test data in: {tmpdir}")

        # 创建最小测试集
        result = TestDataSetup.create_minimal_test_set(tmpdir)
        print(f"Created {result['total']} images")
        print(f"Groups: {len(result['groups'])}")
        print(f"Unique: {len(result['unique'])}")

        print("\nTest data created successfully!")
