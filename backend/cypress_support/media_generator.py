"""
Media Generator for Cypress Tests

Generates test images and videos with metadata embedded.
Reference: backend/manga_viewer/test/init_test_data.py
"""

import os
from pathlib import Path
from typing import List, Tuple

# Check for PIL/Pillow
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️  PIL/Pillow not found. Install with: pip install Pillow")

# Check for opencv (video generation)
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("⚠️  opencv-python not found. Install with: pip install opencv-python")


class MediaGenerator:
    """Generate test images and videos with detailed metadata"""

    @staticmethod
    def create_test_image(
        filepath: str,
        metadata: dict,
        size: Tuple[int, int] = (1080, 1920)
    ) -> bool:
        """
        Create test image with metadata embedded

        Args:
            filepath: Full path where image should be created
            metadata: Dict with keys: filename, file_index, total_files, test_name
            size: Image size (width, height)

        Returns:
            True if successful, False otherwise
        """
        try:
            if HAS_PIL:
                img = Image.new('RGB', size, color=(255, 255, 255))
                draw = ImageDraw.Draw(img)

                # Load fonts (cross-platform)
                try:
                    if os.path.exists('/System/Library/Fonts/Helvetica.ttc'):  # macOS
                        font_huge = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 120)
                        font_title = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 48)
                        font_normal = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 32)
                        font_small = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 24)
                    elif os.path.exists('C:\\Windows\\Fonts\\arial.ttf'):  # Windows
                        font_huge = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 120)
                        font_title = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 48)
                        font_normal = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 32)
                        font_small = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 24)
                    elif os.path.exists('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):  # Linux
                        font_huge = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 120)
                        font_title = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 48)
                        font_normal = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 32)
                        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
                    else:
                        raise Exception("No system fonts found")
                except:
                    font_huge = ImageFont.load_default()
                    font_title = ImageFont.load_default()
                    font_normal = ImageFont.load_default()
                    font_small = ImageFont.load_default()

                # Draw metadata
                y_pos = 100

                # Test name
                draw.text((40, y_pos), "Test:", fill=(0, 0, 0), font=font_small)
                y_pos += 50
                draw.text((40, y_pos), metadata.get('test_name', 'Unknown'), fill=(0, 0, 0), font=font_normal)
                y_pos += 80

                # Filename
                draw.text((40, y_pos), "Filename:", fill=(0, 0, 0), font=font_small)
                y_pos += 50
                draw.text((40, y_pos), metadata.get('filename', 'Unknown'), fill=(0, 0, 0), font=font_title)
                y_pos += 80

                # File order
                file_index = metadata.get('file_index', 0)
                total_files = metadata.get('total_files', 0)
                order_text = f"File {file_index} of {total_files}"
                draw.text((40, y_pos), order_text, fill=(0, 0, 0), font=font_normal)
                y_pos += 150

                # Large centered number
                order_num = f"#{file_index}"
                bbox = draw.textbbox((0, 0), order_num, font=font_huge)
                text_width = bbox[2] - bbox[0]
                draw.text(((size[0] - text_width) // 2, size[1] // 2 - 60), order_num, fill=(0, 0, 0), font=font_huge)

                # Media type badge
                media_type = "IMAGE"
                draw.text((40, size[1] - 100), f"Type: {media_type}", fill=(0, 100, 0), font=font_normal)

                # Draw border
                draw.rectangle([20, 20, size[0]-20, size[1]-20], outline=(0, 0, 0), width=6)

                img.save(filepath, 'JPEG')
                return True
            else:
                # Fallback: Create minimal valid PNG
                png_data = bytes([
                    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
                    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
                    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
                    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
                    0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
                    0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
                    0x00, 0x00, 0x03, 0x00, 0x01, 0x68, 0x9A, 0x0E,
                    0x8B, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
                    0x44, 0xAE, 0x42, 0x60, 0x82
                ])
                with open(filepath, 'wb') as f:
                    f.write(png_data)
                return True
        except Exception as e:
            print(f"Error creating image: {e}")
            return False

    @staticmethod
    def create_test_video(
        filepath: str,
        metadata: dict,
        duration: int = 3,
        size: Tuple[int, int] = (1280, 720)
    ) -> bool:
        """
        Create test video with metadata embedded

        Args:
            filepath: Full path where video should be created
            metadata: Dict with keys: filename, file_index, total_files, test_name
            duration: Video duration in seconds
            size: Video size (width, height)

        Returns:
            True if successful, False otherwise
        """
        try:
            if HAS_CV2:
                width, height = size
                fps = 30
                total_frames = fps * duration

                # Try different codecs for browser compatibility
                temp_filepath = filepath + '.temp.mp4'
                fourcc_options = ['avc1', 'h264', 'X264', 'mp4v']

                out = None
                for codec in fourcc_options:
                    try:
                        fourcc = cv2.VideoWriter_fourcc(*codec)
                        out = cv2.VideoWriter(temp_filepath, fourcc, fps, (width, height))
                        if out.isOpened():
                            print(f"   Using codec: {codec} for {metadata.get('filename', 'video')}")
                            break
                        out.release()
                        out = None
                    except:
                        continue

                if out is None or not out.isOpened():
                    print(f"   Failed to create video writer")
                    MediaGenerator._create_placeholder_video(filepath)
                    return False

                # Generate frames
                for frame_num in range(total_frames):
                    frame = np.ones((height, width, 3), dtype=np.uint8) * 255

                    # Draw border
                    cv2.rectangle(frame, (20, 20), (width-20, height-20), (0, 0, 0), 3)

                    font = cv2.FONT_HERSHEY_SIMPLEX

                    # Title
                    cv2.putText(frame, "Test Video", (width//2-150, 100), font, 2, (0, 0, 0), 3)

                    # Test name
                    test_name = metadata.get('test_name', 'Unknown')
                    cv2.putText(frame, f"Test: {test_name}", (50, 200), font, 0.6, (0, 0, 0), 2)

                    # Filename
                    filename = metadata.get('filename', 'Unknown')
                    cv2.putText(frame, f"File: {filename}", (50, 260), font, 0.8, (0, 0, 0), 2)

                    # File order
                    file_index = metadata.get('file_index', 0)
                    total_files = metadata.get('total_files', 0)
                    cv2.putText(frame, f"File {file_index} of {total_files}", (50, 320), font, 0.7, (0, 0, 0), 2)

                    # Large order number
                    cv2.putText(frame, f"#{file_index}", (width//2-80, height//2+50), font, 4, (0, 0, 0), 5)

                    # Frame counter
                    cv2.putText(frame, f"Frame {frame_num+1}/{total_frames}", (50, height-50), font, 0.6, (100, 100, 100), 2)

                    # Media type
                    cv2.putText(frame, "Type: VIDEO", (50, height-100), font, 0.7, (0, 100, 0), 2)

                    out.write(frame)

                out.release()

                # Move temp to final
                import shutil
                shutil.move(temp_filepath, filepath)
                print(f"   Created video: {metadata.get('filename', 'video')}")
                return True

            else:
                print(f"   opencv not installed, creating placeholder")
                MediaGenerator._create_placeholder_video(filepath)
                return True

        except Exception as e:
            print(f"Error creating video: {e}")
            import traceback
            traceback.print_exc()
            MediaGenerator._create_placeholder_video(filepath)
            return False

    @staticmethod
    def _create_placeholder_video(filepath: str):
        """Create minimal valid MP4 placeholder"""
        mp4_data = bytes([
            0x00, 0x00, 0x00, 0x20, 0x66, 0x74, 0x79, 0x70,
            0x69, 0x73, 0x6F, 0x6D, 0x00, 0x00, 0x02, 0x00,
            0x69, 0x73, 0x6F, 0x6D, 0x69, 0x73, 0x6F, 0x32,
            0x6D, 0x70, 0x34, 0x31, 0x00, 0x00, 0x00, 0x08,
            0x66, 0x72, 0x65, 0x65
        ])
        with open(filepath, 'wb') as f:
            f.write(mp4_data)
