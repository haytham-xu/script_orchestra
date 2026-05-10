#!/usr/bin/env python3
"""
Manga Viewer Test Data Initialization Script

Features:
1. Clean up previous test resources
2. Create new test folder structure
3. Generate test images
4. Initialize index file
5. Reset settings to defaults

Usage:
    python backend/manga_viewer/test/init_test_data.py
"""

import os
import sys
import json
import shutil
import uuid
from pathlib import Path

# Check for PIL/Pillow
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️  PIL/Pillow not found. Will create placeholder files instead of images.")
    print("   Install with: pip install Pillow")

# Check for reportlab (PDF generation)
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.utils import ImageReader
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    print("⚠️  reportlab not found. Will create placeholder files instead of PDFs.")
    print("   Install with: pip install reportlab")

# Check for moviepy (video generation)
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("⚠️  opencv-python not found. Will create placeholder files instead of videos.")
    print("   Install with: pip install opencv-python")

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(script_dir, '../../..')
sys.path.insert(0, backend_dir)

try:
    import config
    from manga_viewer.model.manga_index import MangaIndex
    from manga_viewer.model.folder import Folder
    from manga_viewer.model.tag import Tag
    from manga_viewer.model.metadata import Metadata
    from manga_viewer.settings_manager import SettingsManager
    HAS_MODELS = True
except ImportError as e:
    print(f"⚠️  Could not import backend modules: {e}")
    print("   Running in standalone mode (will not import from config)")
    HAS_MODELS = False


class TestDataInitializer:
    """Test data initializer"""

    def __init__(self):
        self.test_root = os.path.join(os.path.dirname(__file__), 'test_data')
        self.index_path = os.path.join(self.test_root, 'index', 'manga_index.json')
        self.settings_path = os.path.join(os.path.dirname(__file__), '..', 'manga_viewer_settings.json')

        # Test folder structure - expanded to 20 folders with videos
        self.test_folders = [
            {
                'name': '[Artist1]Manga Title 1',
                'files': ['page_001.jpg', 'page_002.jpg', 'page_003.jpg', 'manga.pdf'],
                'tags': {'auth': ['Artist1'], 'name': ['Manga Title 1'], 'custom': ['test'], 'others': [], 'category_main': 'bou', 'category_sub': 'hf', 'mosaic': 'false'}
            },
            {
                'name': '[Artist2]Manga Title 2',
                'files': ['img_01.png', 'img_02.png', 'img_03.png', 'img_04.png', 'comic.pdf'],
                'tags': {'auth': ['Artist2'], 'name': ['Manga Title 2'], 'custom': [], 'others': ['tag1', 'tag2'], 'category_main': 'arch', 'category_sub': 'ntr', 'mosaic': 'true'}
            },
            {
                'name': '(Artist3) Work Title 3',
                'files': ['001.jpg', '002.jpg', 'book.pdf'],
                'tags': {'auth': ['Artist3'], 'name': ['Work Title 3'], 'custom': ['special'], 'others': [], 'category_main': 'bou', 'category_sub': '3d', 'mosaic': 'false'}
            },
            {
                'name': 'Untagged Folder',
                'files': ['image1.jpg', 'image2.jpg', 'image3.jpg'],
                'tags': {'auth': [], 'name': [], 'custom': [], 'others': [], 'category_main': '', 'category_sub': '', 'mosaic': ''}
            },
            {
                'name': '[Artist1]Another Work',
                'files': ['pic_a.jpg', 'pic_b.jpg', 'pic_c.jpg', 'pic_d.jpg', 'pic_e.jpg', 'collection.pdf'],
                'tags': {'auth': ['Artist1'], 'name': ['Another Work'], 'custom': ['favorite'], 'others': [], 'category_main': 'bou', 'category_sub': 'hm', 'mosaic': 'false'}
            },
            {
                'name': '[PDFArtist]PDF Collection',
                'files': ['volume1.pdf', 'volume2.pdf', 'volume3.pdf'],
                'tags': {'auth': ['PDFArtist'], 'name': ['PDF Collection'], 'custom': ['pdf-only'], 'others': [], 'category_main': 'bou', 'category_sub': 'hf', 'mosaic': 'false'}
            },
            {
                'name': '[VideoArtist]Video Works',
                'files': ['preview.jpg', 'main.mp4', 'behind.jpg'],
                'tags': {'auth': ['VideoArtist'], 'name': ['Video Works'], 'custom': ['video'], 'others': [], 'category_main': 'bou', 'category_sub': 'hf', 'mosaic': 'false'}
            },
            {
                'name': '[Artist4]Mixed Media 1',
                'files': ['cover.jpg', 'page1.jpg', 'animation.mp4', 'doc.pdf'],
                'tags': {'auth': ['Artist4'], 'name': ['Mixed Media 1'], 'custom': ['mixed'], 'others': [], 'category_main': 'arch', 'category_sub': '3d', 'mosaic': 'false'}
            },
            {
                'name': '[Artist5]Gallery Set 1',
                'files': ['img1.jpg', 'img2.jpg', 'img3.jpg', 'img4.jpg', 'img5.jpg'],
                'tags': {'auth': ['Artist5'], 'name': ['Gallery Set 1'], 'custom': [], 'others': ['gallery'], 'category_main': 'bou', 'category_sub': 'hf', 'mosaic': 'true'}
            },
            {
                'name': '[Artist6]Special Edition',
                'files': ['front.jpg', 'content.pdf', 'trailer.mp4'],
                'tags': {'auth': ['Artist6'], 'name': ['Special Edition'], 'custom': ['special'], 'others': [], 'category_main': 'bou', 'category_sub': 'ntr', 'mosaic': 'false'}
            },
            {
                'name': '[Artist7]Collection Alpha',
                'files': ['a1.jpg', 'a2.jpg', 'a3.jpg', 'a4.jpg'],
                'tags': {'auth': ['Artist7'], 'name': ['Collection Alpha'], 'custom': [], 'others': [], 'category_main': 'arch', 'category_sub': 'hm', 'mosaic': 'false'}
            },
            {
                'name': '[Artist8]Series Beta',
                'files': ['beta_01.jpg', 'beta_02.jpg', 'beta_full.pdf'],
                'tags': {'auth': ['Artist8'], 'name': ['Series Beta'], 'custom': ['series'], 'others': [], 'category_main': 'bou', 'category_sub': 'q', 'mosaic': 'true'}
            },
            {
                'name': '[VideoArtist]Animation Pack',
                'files': ['thumb.jpg', 'video1.mp4', 'video2.mp4'],
                'tags': {'auth': ['VideoArtist'], 'name': ['Animation Pack'], 'custom': ['video', 'pack'], 'others': [], 'category_main': 'bou', 'category_sub': 'm', 'mosaic': 'false'}
            },
            {
                'name': '[Artist9]Premium Set',
                'files': ['preview.jpg', 'main_content.pdf', 'bonus.jpg'],
                'tags': {'auth': ['Artist9'], 'name': ['Premium Set'], 'custom': ['premium'], 'others': [], 'category_main': 'arch', 'category_sub': 'll', 'mosaic': 'false'}
            },
            {
                'name': '[Artist10]Digital Art',
                'files': ['art1.jpg', 'art2.jpg', 'art3.jpg', 'making.mp4'],
                'tags': {'auth': ['Artist10'], 'name': ['Digital Art'], 'custom': ['digital'], 'others': [], 'category_main': 'bou', 'category_sub': 'lo', 'mosaic': 'true'}
            },
            {
                'name': '[Artist11]Photo Book',
                'files': ['photo_book.pdf', 'cover.jpg'],
                'tags': {'auth': ['Artist11'], 'name': ['Photo Book'], 'custom': ['photobook'], 'others': [], 'category_main': 'arch', 'category_sub': 'xz', 'mosaic': 'false'}
            },
            {
                'name': '[Artist12]Video Tutorial',
                'files': ['intro.jpg', 'tutorial.mp4', 'resources.pdf'],
                'tags': {'auth': ['Artist12'], 'name': ['Video Tutorial'], 'custom': ['tutorial'], 'others': [], 'category_main': 'bou', 'category_sub': 'zr', 'mosaic': 'false'}
            },
            {
                'name': '[Artist13]Illustration Pack',
                'files': ['ill1.jpg', 'ill2.jpg', 'ill3.jpg', 'ill4.jpg', 'ill5.jpg', 'ill6.jpg'],
                'tags': {'auth': ['Artist13'], 'name': ['Illustration Pack'], 'custom': ['illustration'], 'others': [], 'category_main': 'bou', 'category_sub': 'sp', 'mosaic': 'true'}
            },
            {
                'name': '[Artist14]Anime Style',
                'files': ['scene1.jpg', 'scene2.jpg', 'animation.mp4', 'storyboard.pdf'],
                'tags': {'auth': ['Artist14'], 'name': ['Anime Style'], 'custom': ['anime'], 'others': [], 'category_main': 'arch', 'category_sub': 'tr', 'mosaic': 'false'}
            },
            {
                'name': '[Artist15]Final Collection',
                'files': ['final_1.jpg', 'final_2.jpg', 'final_3.jpg', 'summary.pdf', 'review.mp4'],
                'tags': {'auth': ['Artist15'], 'name': ['Final Collection'], 'custom': ['final'], 'others': [], 'category_main': 'bou', 'category_sub': 'hf', 'mosaic': 'false'}
            },
        ]

    def clean_test_data(self):
        """Clean up old test data"""
        print("🗑️  Cleaning old test data...")
        if os.path.exists(self.test_root):
            shutil.rmtree(self.test_root)
            print(f"   ✓ Removed {self.test_root}")

        # Note: We do NOT delete settings file or index file as they contain user configurations

    def create_test_image(self, filepath, folder_name, filename, file_index, total_files, size=(1080, 1920)):
        """Create test image with folder and file info at 1080x1920"""
        if HAS_PIL:
            img = Image.new('RGB', size, color=(255, 255, 255))
            draw = ImageDraw.Draw(img)

            # Try system fonts, otherwise use default
            # Try to load fonts (cross-platform)
            try:
                # Try macOS fonts first
                if os.path.exists('/System/Library/Fonts/Helvetica.ttc'):
                    font_huge = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 120)
                    font_title = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 48)
                    font_normal = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 32)
                    font_small = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 24)
                # Try Windows fonts
                elif os.path.exists('C:\\Windows\\Fonts\\arial.ttf'):
                    font_huge = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 120)
                    font_title = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 48)
                    font_normal = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 32)
                    font_small = ImageFont.truetype('C:\\Windows\\Fonts\\arial.ttf', 24)
                # Try Linux fonts
                elif os.path.exists('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
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

            # Get relative path from filepath
            try:
                rel_path = os.path.relpath(filepath, self.test_root)
            except:
                rel_path = filepath

            # Get file extension
            file_ext = os.path.splitext(filename)[1].upper()

            # Draw text with detailed info
            y_pos = 100

            # Relative path
            draw.text((40, y_pos), "Path:", fill=(0, 0, 0), font=font_small)
            y_pos += 50
            # Wrap long paths
            path_lines = self._wrap_text(rel_path, 30)
            for line in path_lines:
                draw.text((40, y_pos), line, fill=(0, 0, 0), font=font_normal)
                y_pos += 50
            y_pos += 30

            # File name
            draw.text((40, y_pos), "Filename:", fill=(0, 0, 0), font=font_small)
            y_pos += 50
            draw.text((40, y_pos), filename, fill=(0, 0, 0), font=font_title)
            y_pos += 80

            # File format
            draw.text((40, y_pos), "Format:", fill=(0, 0, 0), font=font_small)
            y_pos += 50
            draw.text((40, y_pos), file_ext, fill=(0, 0, 0), font=font_normal)
            y_pos += 80

            # File order
            order_text = f"File {file_index} of {total_files}"
            draw.text((40, y_pos), order_text, fill=(0, 0, 0), font=font_normal)
            y_pos += 150

            # Large centered number showing order
            order_num = f"#{file_index}"
            bbox = draw.textbbox((0, 0), order_num, font=font_huge)
            text_width = bbox[2] - bbox[0]
            draw.text(((size[0] - text_width) // 2, size[1] // 2 - 60), order_num, fill=(0, 0, 0), font=font_huge)

            # Draw border
            draw.rectangle([20, 20, size[0]-20, size[1]-20], outline=(0, 0, 0), width=6)

            img.save(filepath)
        else:
            # If no PIL, create a minimal valid PNG
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

    def _wrap_text(self, text, max_length):
        """Wrap text to multiple lines"""
        words = text.replace('\\', '/').split('/')
        lines = []
        current_line = ""
        for word in words:
            if len(current_line + word) <= max_length:
                current_line += word + "/"
            else:
                if current_line:
                    lines.append(current_line.rstrip('/'))
                current_line = word + "/"
        if current_line:
            lines.append(current_line.rstrip('/'))
        return lines

    def create_test_pdf(self, filepath, folder_name, filename, file_index, total_files, num_pages=5):
        """Create test PDF with folder and file info (minimum 5 pages)"""
        if HAS_REPORTLAB:
            c = canvas.Canvas(filepath, pagesize=A4)
            width, height = A4

            # Get relative path
            try:
                rel_path = os.path.relpath(filepath, self.test_root)
            except:
                rel_path = filepath

            # Get file extension
            file_ext = os.path.splitext(filename)[1].upper()

            for page_num in range(1, num_pages + 1):
                # Title
                c.setFont("Helvetica-Bold", 24)
                c.drawCentredString(width / 2, height - 80, "Test PDF Document")

                # Path info
                c.setFont("Helvetica", 10)
                c.drawString(60, height - 140, f"Path: {rel_path}")

                # Filename
                c.setFont("Helvetica-Bold", 14)
                c.drawString(60, height - 180, f"Filename: {filename}")

                # Format
                c.setFont("Helvetica", 12)
                c.drawString(60, height - 210, f"Format: {file_ext}")

                # File order
                c.drawString(60, height - 240, f"File Order: {file_index} of {total_files}")

                # Page number
                c.drawString(60, height - 270, f"Page: {page_num} of {num_pages}")

                # Large centered order number
                c.setFont("Helvetica-Bold", 72)
                order_text = f"#{file_index}"
                text_width = c.stringWidth(order_text, "Helvetica-Bold", 72)
                c.drawString((width - text_width) / 2, height / 2 + 50, order_text)

                # Page number below
                c.setFont("Helvetica-Bold", 48)
                page_text = f"Page {page_num}"
                text_width2 = c.stringWidth(page_text, "Helvetica-Bold", 48)
                c.drawString((width - text_width2) / 2, height / 2 - 50, page_text)

                # Draw border
                c.rect(40, 40, width - 80, height - 80, stroke=1, fill=0)

                # Add test pattern
                c.setFont("Helvetica", 10)
                c.setFillColorRGB(0.9, 0.9, 0.95)
                for i in range(5):
                    y_pos = 250 - i * 35
                    c.rect(80, y_pos, 400, 25, stroke=0, fill=1)
                    c.setFillColorRGB(0.3, 0.3, 0.3)
                    c.drawString(90, y_pos + 8, f"Test content line {i + 1} on page {page_num}")
                    c.setFillColorRGB(0.9, 0.9, 0.95)

                if page_num < num_pages:
                    c.showPage()

            c.save()
        else:
            # If no reportlab, create a minimal valid PDF with 3 pages
            pdf_data = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >> endobj
4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 7 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >> endobj
5 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 8 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >> endobj
6 0 obj << /Length 50 >> stream
BT /F1 12 Tf 100 700 Td (Test PDF - Page 1) Tj ET
endstream endobj
7 0 obj << /Length 50 >> stream
BT /F1 12 Tf 100 700 Td (Test PDF - Page 2) Tj ET
endstream endobj
8 0 obj << /Length 50 >> stream
BT /F1 12 Tf 100 700 Td (Test PDF - Page 3) Tj ET
endstream endobj
xref
0 9
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000131 00000 n
0000000325 00000 n
0000000519 00000 n
0000000713 00000 n
0000000812 00000 n
0000000911 00000 n
trailer << /Size 9 /Root 1 0 R >>
startxref
1010
%%EOF
"""
            with open(filepath, 'wb') as f:
                f.write(pdf_data)

    def create_test_video(self, filepath, folder_name, filename, file_index, total_files, duration=3):
        """Create test video with folder and file info (3 seconds)"""
        if HAS_CV2:
            try:
                import cv2
                import numpy as np

                # Video parameters
                width, height = 1280, 720
                fps = 30
                total_frames = fps * duration

                # Use H.264 codec for better browser compatibility
                # Try different codecs in order of preference
                temp_filepath = filepath + '.temp.mp4'
                fourcc_options = [
                    'avc1',  # H.264 (best browser support)
                    'h264',  # H.264 alternative
                    'X264',  # x264 codec
                    'mp4v',  # MPEG-4 fallback
                ]

                out = None
                for codec in fourcc_options:
                    try:
                        fourcc = cv2.VideoWriter_fourcc(*codec)
                        out = cv2.VideoWriter(temp_filepath, fourcc, fps, (width, height))
                        if out.isOpened():
                            print(f"   ℹ️ Using codec: {codec} for {filename}")
                            break
                        out.release()
                        out = None
                    except:
                        continue

                if out is None or not out.isOpened():
                    print(f"   ⚠️ Could not create video writer for {filename}")
                    self._create_placeholder_video(filepath)
                    return

                # Get relative path
                try:
                    rel_path = os.path.relpath(filepath, self.test_root)
                except:
                    rel_path = filepath

                # Generate frames
                for frame_num in range(total_frames):
                    # Create white background
                    frame = np.ones((height, width, 3), dtype=np.uint8) * 255

                    # Draw border
                    cv2.rectangle(frame, (20, 20), (width-20, height-20), (0, 0, 0), 3)

                    # Add text
                    font = cv2.FONT_HERSHEY_SIMPLEX

                    # Title
                    cv2.putText(frame, "Test Video", (width//2-150, 100), font, 2, (0, 0, 0), 3)

                    # Path (wrap if too long)
                    path_text = f"Path: {rel_path}"
                    if len(path_text) > 60:
                        path_text = path_text[:60] + "..."
                    cv2.putText(frame, path_text, (50, 200), font, 0.6, (0, 0, 0), 2)

                    # Filename
                    cv2.putText(frame, f"Filename: {filename}", (50, 260), font, 0.8, (0, 0, 0), 2)

                    # File order
                    cv2.putText(frame, f"File {file_index} of {total_files}", (50, 320), font, 0.7, (0, 0, 0), 2)

                    # Large order number
                    cv2.putText(frame, f"#{file_index}", (width//2-80, height//2+50), font, 4, (0, 0, 0), 5)

                    # Frame counter
                    cv2.putText(frame, f"Frame {frame_num+1}/{total_frames}", (50, height-50), font, 0.6, (100, 100, 100), 2)

                    # Write frame
                    out.write(frame)

                out.release()

                # Move temp file to final destination
                import shutil
                shutil.move(temp_filepath, filepath)
                print(f"   ✓ Created video: {filename}")

            except Exception as e:
                print(f"   ⚠️ Failed to create video with opencv: {e}")
                import traceback
                traceback.print_exc()
                # Clean up temp file if exists
                try:
                    if os.path.exists(temp_filepath):
                        os.remove(temp_filepath)
                except:
                    pass
                # Fallback to placeholder
                self._create_placeholder_video(filepath)
        else:
            print(f"   ℹ️ Creating placeholder video: {filename} (opencv not installed)")
            self._create_placeholder_video(filepath)

    def _create_placeholder_video(self, filepath):
        """Create a minimal valid MP4 placeholder"""
        # Create a minimal valid MP4 file (very basic structure)
        # This is a 1-frame black video that most players can recognize
        mp4_data = bytes([
            0x00, 0x00, 0x00, 0x20, 0x66, 0x74, 0x79, 0x70,
            0x69, 0x73, 0x6F, 0x6D, 0x00, 0x00, 0x02, 0x00,
            0x69, 0x73, 0x6F, 0x6D, 0x69, 0x73, 0x6F, 0x32,
            0x6D, 0x70, 0x34, 0x31, 0x00, 0x00, 0x00, 0x08,
            0x66, 0x72, 0x65, 0x65
        ])
        with open(filepath, 'wb') as f:
            f.write(mp4_data)

    def create_folder_structure(self):
        """Create test folder structure and files"""
        print("\n📁 Creating test folder structure...")

        scan_folder = os.path.join(self.test_root, 'scan')
        os.makedirs(scan_folder, exist_ok=True)

        for folder_info in self.test_folders:
            folder_path = os.path.join(scan_folder, folder_info['name'])
            os.makedirs(folder_path, exist_ok=True)

            # Create test files with order information
            total_files = len(folder_info['files'])
            for file_index, filename in enumerate(folder_info['files'], start=1):
                filepath = os.path.join(folder_path, filename)

                # Create different file types based on extension
                if filename.lower().endswith('.pdf'):
                    self.create_test_pdf(
                        filepath,
                        folder_info['name'],
                        filename,
                        file_index,
                        total_files,
                        num_pages=5
                    )
                elif filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                    self.create_test_video(
                        filepath,
                        folder_info['name'],
                        filename,
                        file_index,
                        total_files,
                        duration=3
                    )
                else:
                    self.create_test_image(
                        filepath,
                        folder_info['name'],
                        filename,
                        file_index,
                        total_files
                    )

            print(f"   ✓ Created {folder_info['name']} with {len(folder_info['files'])} files")


    def create_manga_index(self):
        """Create manga index file"""
        print("\n📋 Creating manga index...")

        if not HAS_MODELS:
            print("   ⚠️  Skipping index creation (models not available)")
            print("   📝 Creating simple JSON structure instead...")

            folders = {}
            scan_folder = os.path.join(self.test_root, 'scan')

            for folder_info in self.test_folders:
                folder_path = os.path.join(scan_folder, folder_info['name'])
                folder_id = str(uuid.uuid4())

                # Calculate size and file count
                total_size = 0
                total_files = 0
                for filename in folder_info['files']:
                    filepath = os.path.join(folder_path, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
                        total_files += 1

                folders[folder_id] = {
                    'id': folder_id,
                    'name': folder_info['name'],
                    'path': folder_path,
                    'files': [],
                    'size': total_size,
                    'number': total_files,
                    'initialized': len(folder_info['tags']['auth']) > 0,
                    'tags': folder_info['tags']
                }

            # Generate metadata
            auth_set, cat_main_set, cat_sub_set = set(), set(), set()
            for folder in folders.values():
                auth_set.update(folder['tags']['auth'])
                if folder['tags']['category_main']:
                    cat_main_set.add(folder['tags']['category_main'])
                if folder['tags']['category_sub']:
                    cat_sub_set.add(folder['tags']['category_sub'])

            manga_index = {
                'folders': folders,
                'metadata': {
                    'auth': sorted(list(auth_set)),
                    'category_main': sorted(list(cat_main_set)),
                    'category_sub': sorted(list(cat_sub_set))
                }
            }
        else:
            manga_index_obj = MangaIndex()
            scan_folder = os.path.join(self.test_root, 'scan')

            for folder_info in self.test_folders:
                folder_path = os.path.join(scan_folder, folder_info['name'])
                folder_id = str(uuid.uuid4())

                # Calculate size and file count
                total_size = 0
                total_files = 0
                for filename in folder_info['files']:
                    filepath = os.path.join(folder_path, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
                        total_files += 1

                # Create Tag object
                tag = Tag(
                    auth=folder_info['tags']['auth'],
                    name=folder_info['tags']['name'],
                    custom=folder_info['tags']['custom'],
                    others=folder_info['tags']['others'],
                    category_main=folder_info['tags']['category_main'],
                    category_sub=folder_info['tags']['category_sub'],
                    mosaic=folder_info['tags']['mosaic']
                )

                # Create Folder object
                folder = Folder(
                    id_=folder_id,
                    name=folder_info['name'],
                    path=folder_path,
                    file_list=[],  # Leave empty, will be loaded dynamically
                    size=total_size,
                    number=total_files,
                    initialized=(len(folder_info['tags']['auth']) > 0),
                    tags=tag
                )

                manga_index_obj.folders[folder_id] = folder

            # Generate metadata
            auth_set, cat_main_set, cat_sub_set = set(), set(), set()
            for folder in manga_index_obj.folders.values():
                auth_set.update(folder.tags.auth)
                if folder.tags.category_main:
                    cat_main_set.add(folder.tags.category_main)
                if folder.tags.category_sub:
                    cat_sub_set.add(folder.tags.category_sub)

            manga_index_obj.metadata = Metadata(
                auth=sorted(list(auth_set)),
                category_main=sorted(list(cat_main_set)),
                category_sub=sorted(list(cat_sub_set))
            )

            manga_index = manga_index_obj.to_dict()

        # Save index file
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(manga_index, f, ensure_ascii=False, indent=2)

        print(f"   ✓ Created index at {self.index_path}")
        print(f"   ✓ Total folders: {len(manga_index['folders'])}")
        if 'metadata' in manga_index and 'auth' in manga_index['metadata']:
            print(f"   ✓ Authors: {', '.join(manga_index['metadata']['auth'])}")

    def reset_settings(self):
        """Reset settings to defaults"""
        print("\n⚙️  Resetting settings to defaults...")

        # Load default config from default_settings.json
        default_settings_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'default_settings.json'
        )

        try:
            with open(default_settings_file, 'r', encoding='utf-8') as f:
                default_settings = json.load(f)
        except Exception as e:
            print(f"   ⚠️ Failed to load default_settings.json: {e}")
            if HAS_MODELS:
                settings_manager = SettingsManager()
                default_settings = settings_manager._get_default_settings()
            else:
                print("   ⚠️ Cannot load default settings, skipping...")
                return

        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, 'w', encoding='utf-8') as f:
            json.dump(default_settings, f, ensure_ascii=False, indent=2)

        print(f"   ✓ Reset settings at {self.settings_path}")

    def create_config_example(self):
        """Create config example file"""
        print("\n📝 Creating config example...")

        config_example = f"""
# Add the following config to backend/config_local.py to use test data

# Manga Viewer Test Configuration
MANGA_VIEWER_ROOT_PATH = '{self.test_root}'
MANGA_VIEWER_INDEX_PATH = '{os.path.join(self.test_root, 'index')}'
MANGA_VIEWER_SCAN_FOLDER = ['{os.path.join(self.test_root, 'scan')}']
MANGA_VIEWER_IGNORE_SCAN_FOLDER = []
"""

        example_path = os.path.join(self.test_root, 'config_example.txt')
        with open(example_path, 'w', encoding='utf-8') as f:
            f.write(config_example)

        print(f"   ✓ Created config example at {example_path}")
        print("\n" + "="*60)
        print("📌 Please add the following to backend/config_local.py:")
        print("="*60)
        print(config_example)
        print("="*60)

    def print_summary(self):
        """Print summary info"""
        print("\n" + "="*60)
        print("✅ Test data initialization completed!")
        print("="*60)
        print(f"\n📂 Test data location: {self.test_root}")
        print(f"📋 Index file: {self.index_path}")
        print(f"⚙️  Settings file: {self.settings_path}")
        print(f"\n📊 Statistics:")
        print(f"   - Total folders: {len(self.test_folders)}")
        print(f"   - Total images: {sum(len(f['files']) for f in self.test_folders)}")
        print("\n🚀 Next steps:")
        print("   1. Update backend/config_local.py with the test paths")
        print("   2. Start the Flask backend: python backend/app.py")
        print("   3. Test the manga viewer at http://127.0.0.1:5001/manga-viewer")

    def run(self):
        """Run complete initialization process"""
        print("="*60)
        print("🎬 Manga Viewer Test Data Initializer")
        print("="*60)

        self.clean_test_data()
        self.create_folder_structure()
        self.create_manga_index()
        # Note: We do NOT reset settings as they contain user configurations
        self.create_config_example()
        self.print_summary()


if __name__ == '__main__':
    initializer = TestDataInitializer()
    initializer.run()
